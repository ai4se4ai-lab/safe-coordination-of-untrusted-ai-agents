"""Extended bounded TLC campaign (revision): larger multi-job instances with
environmental changes, every mutant on multi-job topologies, and a TLC-checked
refinement mapping from AsyncController to AtomicController (Theorem 4).

    python scripts/run_models_extended.py [--quick] [--workers 16]

Writes models/extended/*.cfg and results/processed/tse/tlc-extended.json.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / ".tools/tla2tools.jar"
FLAGS = ["CancelObsolete", "RecheckCurrent", "ResetBudget", "IgnoreContract", "IgnoreContext",
         "IgnoreSuspension", "IgnoreAuthority", "StalePublication"]
BASE = {"CancelObsolete": True, "RecheckCurrent": True}
MUTANTS = {  # id: (flag overrides, invariant expected to be violated)
    "no-cancel": ({"CancelObsolete": False}, None),
    "no-recheck": ({"RecheckCurrent": False}, None),
    "obsolete-both": ({"CancelObsolete": False, "RecheckCurrent": False}, "CurrentCommit"),
    "budget-reset": ({"ResetBudget": True}, "BudgetSafety"),
    "publish-suspended": ({"IgnoreSuspension": True}, "SuspensionPublication"),
    "revoked-authority": ({"IgnoreAuthority": True}, "AuthorityCommit"),
    "stale-publication": ({"StalePublication": True}, "RevisionPublication"),
    "contract-omitted": ({"IgnoreContract": True}, "ContractCommit"),
    "membership-omitted": ({"IgnoreContext": True}, "ContextCommit"),
}
TOPOLOGIES = {"x_chain5": 5, "x_one": 1, "x_chain2": 2, "x_chain3": 3, "x_fanout3": 3, "x_diamond4": 4, "x_chain4": 4}


def config(jobs, k, m, flags, invariants, properties=()):
    lines = ["SPECIFICATION Spec"] + ["INVARIANT " + i for i in invariants] + \
            ["PROPERTY " + p for p in properties] + ["CONSTANTS",
             "Jobs = {%s}" % ",".join(str(i) for i in range(1, jobs + 1)), "Values = {0,1}", "K = %d" % k,
             "MaxChanges = %d" % m, "None = none", "Parent <- ModelParent"]
    lines += ["%s = %s" % (f, "TRUE" if flags.get(f, False) else "FALSE") for f in FLAGS]
    return "\n".join(lines) + "\n"


def run(name, module, cfg_text, workers, timeout):
    cfg = ROOT / "models/extended" / (name + ".cfg")
    cfg.write_text(cfg_text)
    meta = ROOT / "tmp/tlc-ext" / name
    started = time.monotonic()
    try:
        p = subprocess.run(["java", "-XX:+UseParallelGC", "-Xmx24g", "-cp", str(JAR),
                            "-DTLA-Library=" + str(ROOT / "specification"), "tlc2.TLC", "-workers", str(workers),
                            "-cleanup", "-noGenerateSpecTE", "-metadir", str(meta), "-config", str(cfg),
                            str(ROOT / "models" / ("Model_%s.tla" % module))],
                           capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        log, status = p.stdout + p.stderr, None
    except subprocess.TimeoutExpired as e:
        log, status = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    counts = re.findall(r"([\d,]+) states generated, ([\d,]+) distinct states found", log)
    generated, distinct = [int(x.replace(",", "")) for x in counts[-1]] if counts else (None, None)
    violated = re.search(r"Invariant (\w+) is violated", log)
    temporal = re.search(r"Temporal properties were violated|Action property .* is violated|"
                         r"The following behavior constitutes a counter-example", log)
    depth = len(re.findall(r"^State \d+:", log, re.M))
    if status is None:
        status = ("counterexample" if violated or temporal else
                  "passed" if "Model checking completed. No error has been found." in log else "error")
    return {"id": name, "status": status, "violated": violated.group(1) if violated else
            ("refinement" if temporal else None), "distinct_states": distinct, "generated_states": generated,
            "trace_states": depth or None, "seconds": round(time.monotonic() - started, 1),
            "log_tail": log[-600:] if status == "error" else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--timeout", type=int, default=5400)
    a = ap.parse_args()
    (ROOT / "models/extended").mkdir(exist_ok=True)
    plan = []
    baselines = ([("x_chain2", 1, 1)] if a.quick else
                 [("x_one", 2, 2), ("x_chain2", 2, 1), ("x_chain2", 1, 2), ("x_chain3", 1, 1), ("x_chain3", 2, 1),
                  ("x_fanout3", 1, 1), ("x_fanout3", 1, 2), ("x_diamond4", 1, 1), ("x_diamond4", 2, 1),
                  ("x_diamond4", 1, 2), ("x_chain4", 1, 1), ("x_chain4", 1, 2), ("x_chain5", 1, 1), ("x_chain3", 2, 2)])
    for topo, k, m in baselines:
        plan.append(("base-%s-k%d-m%d" % (topo, k, m), topo, TOPOLOGIES[topo], k, m, BASE, ["Safety"],
                     ["AtomicRefinement"], "passed", None))
    for mid, (over, inv) in MUTANTS.items():
        for topo, k, m in ([("x_chain2", 1, 1)] if a.quick else [("x_chain2", 1, 1), ("x_chain3", 1, 1), ("x_diamond4", 1, 1)]):
            flags = dict(BASE, **over)
            invariants = [inv] if inv else ["Safety"]
            plan.append(("mut-%s-%s" % (mid, topo), topo, TOPOLOGIES[topo], k, m, flags, invariants, [],
                         "counterexample" if inv else "passed", inv))
    # Nonvacuity of the refinement check itself: without both obsolete defences the
    # projected behaviour must leave the atomic specification.
    for topo in (["x_chain2"] if a.quick else ["x_one", "x_chain2"]):
        plan.append(("refine-obsolete-both-%s" % topo, topo, TOPOLOGIES[topo], 1, 1,
                     dict(BASE, CancelObsolete=False, RecheckCurrent=False), [], ["AtomicRefinement"],
                     "counterexample", "refinement"))
    results = []
    for name, topo, jobs, k, m, flags, invs, props, expected, target in plan:
        r = run(name, topo, config(jobs, k, m, flags, invs, props), a.workers, a.timeout)
        r.update({"topology": topo, "jobs": jobs, "k": k, "m": m, "expected": expected, "target": target,
                  "invariants": invs, "properties": props})
        r["expectation_met"] = r["status"] == expected and (expected == "passed" or r["violated"] == target)
        results.append(r)
        print(name, r["status"], r["violated"] or "", r["distinct_states"], "%.0fs" % r["seconds"], flush=True)
    version = subprocess.run(["java", "-cp", str(JAR), "tlc2.TLC", "-version"], capture_output=True, text=True)
    out = {"results": results, "all_met": all(r["expectation_met"] for r in results),
           "tla2tools_sha256": hashlib.sha256(JAR.read_bytes()).hexdigest(),
           "tlc_version": (version.stdout + version.stderr).strip().splitlines()[0] if version.stdout or
           version.stderr else None, "workers": a.workers}
    path = ROOT / "results/processed/tse" / ("tlc-extended-quick.json" if a.quick else "tlc-extended.json")
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(path.relative_to(ROOT), "all expectations met:", out["all_met"])


if __name__ == "__main__":
    main()
