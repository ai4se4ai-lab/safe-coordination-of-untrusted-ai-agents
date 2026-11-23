"""Scaling campaign for the SoSyM article: larger instances of the TLA+ coordination
model (more jobs, budget 2, two environmental changes), a topology that mirrors the
model-driven case study, and the guard mutants on the larger topologies.

    python scripts/run_models_sosym.py [--workers 18] [--timeout 10800]

Reuses the configuration generator of run_models_extended.py. Writes
models/sosym/*.cfg, models/Model_s_*.tla and results/processed/sosym/tlc-scaling.json.
Runs that exceed the timeout are recorded as 'timeout' with the last progress report.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, time, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_models_extended import config, MUTANTS, BASE  # noqa: E402

JAR = ROOT / ".tools/tla2tools.jar"
# Parent sets per topology (jobs are 1..n, parents have smaller indices).
TOPOLOGIES = {
    "s_chain4": {1: [], 2: [1], 3: [2], 4: [3]},
    "s_chain5": {1: [], 2: [1], 3: [2], 4: [3], 5: [4]},
    "s_chain6": {1: [], 2: [1], 3: [2], 4: [3], 5: [4], 6: [5]},
    "s_fanout4": {1: [], 2: [1], 3: [1], 4: [1]},
    "s_fanin4": {1: [], 2: [], 3: [], 4: [1, 2, 3]},
    "s_diamond4": {1: [], 2: [1], 3: [1], 4: [2, 3]},
    # Abstraction of the model-driven case study: 1 domain model, 2 OCL constraints,
    # 3 state machine, 4 generated service code, 5 acceptance tests.
    "s_mde5": {1: [], 2: [1], 3: [1], 4: [1, 2, 3], 5: [3, 4]},
}


def module(topo):
    parents = TOPOLOGIES[topo]
    cases = " [] ".join("%d = j -> {%s}" % (j, ",".join(map(str, ps))) for j, ps in parents.items())
    text = "---- MODULE Model_%s ----\nEXTENDS Refinement\nModelParent == [j \\in Jobs |-> CASE %s]\n====\n" % (topo, cases)
    (ROOT / "models" / ("Model_%s.tla" % topo)).write_text(text)


def run(name, topo, cfg_text, workers, timeout, heap):
    cfg = ROOT / "models/sosym" / (name + ".cfg")
    cfg.write_text(cfg_text)
    meta = ROOT / "tmp/tlc-sosym" / name
    started = time.monotonic()
    cmd = ["java", "-XX:+UseParallelGC", "-Xmx%dg" % heap, "-cp", str(JAR),
           "-DTLA-Library=" + str(ROOT / "specification"), "tlc2.TLC", "-workers", str(workers),
           "-cleanup", "-noGenerateSpecTE", "-metadir", str(meta), "-config", str(cfg),
           str(ROOT / "models" / ("Model_%s.tla" % topo))]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        log, status = p.stdout + p.stderr, None
    except subprocess.TimeoutExpired as e:
        out = e.stdout
        log = out.decode() if isinstance(out, bytes) else (out or "")
        status = "timeout"
    counts = re.findall(r"([\d,]+) states generated, ([\d,]+) distinct states found", log)
    generated, distinct = [int(x.replace(",", "")) for x in counts[-1]] if counts else (None, None)
    violated = re.search(r"Invariant (\w+) is violated", log)
    temporal = re.search(r"Temporal properties were violated|Action property .* is violated|"
                         r"The following behavior constitutes a counter-example", log)
    depth = len(re.findall(r"^State \d+:", log, re.M))
    diameter = re.findall(r"depth of the complete state graph search is (\d+)", log)
    if status is None:
        status = ("counterexample" if violated or temporal else
                  "passed" if "Model checking completed. No error has been found." in log else "error")
    return {"id": name, "status": status, "violated": violated.group(1) if violated else
            ("refinement" if temporal else None), "distinct_states": distinct, "generated_states": generated,
            "diameter": int(diameter[-1]) if diameter else None,
            "trace_states": depth or None, "seconds": round(time.monotonic() - started, 1),
            "log_tail": log[-800:] if status in ("error", "timeout") else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=18)
    ap.add_argument("--heap", type=int, default=90)
    ap.add_argument("--timeout", type=int, default=10800)
    ap.add_argument("--only", default=None)
    ap.add_argument("--out", default="results/processed/sosym/tlc-scaling.json")
    a = ap.parse_args()
    for t in TOPOLOGIES:
        module(t)
    plan = []
    baselines = [("s_mde5", 1, 1), ("s_mde5", 1, 2), ("s_mde5", 2, 1), ("s_fanin4", 1, 2), ("s_fanout4", 1, 2),
                 ("s_chain6", 1, 1), ("s_chain5", 1, 2), ("s_chain4", 2, 1), ("s_diamond4", 2, 2),
                 ("s_chain4", 2, 2), ("s_mde5", 2, 2)]
    for topo, k, m in baselines:
        plan.append(("base-%s-k%d-m%d" % (topo, k, m), topo, k, m, BASE, ["Safety"], ["AtomicRefinement"],
                     "passed", None))
    for mid, (over, inv) in MUTANTS.items():
        flags = dict(BASE, **over)
        plan.append(("mut-%s-s_mde5" % mid, "s_mde5", 1, 1, flags, [inv] if inv else ["Safety"], [],
                     "counterexample" if inv else "passed", inv))
    plan.append(("refine-obsolete-both-s_mde5", "s_mde5", 1, 1, dict(BASE, CancelObsolete=False, RecheckCurrent=False),
                 [], ["AtomicRefinement"], "counterexample", "refinement"))
    path = ROOT / a.out
    results = []
    if path.exists():
        results = [r for r in json.loads(path.read_text())["results"] if r["status"] != "error"]
    done = {r["id"] for r in results}
    for name, topo, k, m, flags, invs, props, expected, target in plan:
        if name in done or (a.only and a.only not in name):
            continue
        r = run(name, topo, config(len(TOPOLOGIES[topo]), k, m, flags, invs, props), a.workers, a.timeout, a.heap)
        r.update({"topology": topo, "jobs": len(TOPOLOGIES[topo]), "k": k, "m": m, "expected": expected,
                  "target": target, "invariants": invs, "properties": props})
        r["expectation_met"] = r["status"] == expected and (expected == "passed" or r["violated"] == target)
        results.append(r)
        print(name, r["status"], r["violated"] or "", r["distinct_states"], "%.0fs" % r["seconds"], flush=True)
        version = subprocess.run(["java", "-cp", str(JAR), "tlc2.TLC", "-version"], capture_output=True, text=True)
        out = {"results": results, "all_met": all(x["expectation_met"] for x in results),
               "tla2tools_sha256": hashlib.sha256(JAR.read_bytes()).hexdigest(),
               "tlc_version": (version.stdout + version.stderr).strip().splitlines()[0],
               "workers": a.workers, "heap_gb": a.heap, "timeout_s": a.timeout,
               "host_cpus": __import__("os").cpu_count()}
        path.write_text(json.dumps(out, indent=1) + "\n")
    print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
