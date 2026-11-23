#!/usr/bin/env python3
"""Regenerate every generated number and table row of the SoSyM manuscript from the
evidence in this package, check the hand-maintained numbers against their records,
and compare everything with ../main.tex.

    python3 docs/paper/SoSyM/replication-package/verify.py            # checks, ~10 s
    python3 docs/paper/SoSyM/replication-package/verify.py --rerun    # + re-executes sim/impact/sweep, ~1 min

Needs Python 3.10+ and scipy (only for the two Wilcoxon p-value exponents; without
scipy those two macros are reported as SKIPPED and every other check still runs).
Nothing is re-run: no model is called, TLC and TLAPS are not invoked. The script
re-reads the recorded runs under evidence/ and executes the repository's own
generator (experiments/sosym/summarize.py) on them in a temporary tree. The
regenerated macros, table blocks and summary are written to generated/, and every
number is listed in claims.csv.

Exit code 0 means that all checks passed.
"""
from collections import Counter
from pathlib import Path
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PAPER = HERE.parent / "main.tex"
EVIDENCE = HERE / "evidence"
OUT = HERE / "generated"
MACRO = re.compile(r"\\newcommand\{\\(\w+)\}\{(.*)\}\s*$")
BLOCK = re.compile(r"%% BEGIN GENERATED (\S+)\n(.*?)%% END GENERATED \1\n", re.S)

failures, notes = [], []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def macros(text):
    return {m.group(1): m.group(2) for line in text.splitlines() if (m := MACRO.match(line.strip()))}


def load(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fmt(n):
    return "{:,}".format(n)


def module(name, path, **patch):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in patch.items():
        setattr(mod, k, v)
    return mod


# ---------------------------------------------------------------- 1. generated blocks
def regenerate(tex):
    """Run summarize.py on a repository-shaped copy of the evidence; return the regenerated main.tex."""
    have_scipy = importlib.util.find_spec("scipy") is not None
    if not have_scipy:            # only the Wilcoxon p-values need scipy
        stub = types.ModuleType("scipy.stats")
        stub.wilcoxon = lambda a, b: types.SimpleNamespace(pvalue=float("nan"))
        sys.modules["scipy"] = types.ModuleType("scipy")
        sys.modules["scipy.stats"] = stub
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copytree(EVIDENCE / "results", root / "results")
        (root / "docs/paper/SoSyM").mkdir(parents=True)
        (root / "docs/paper/SoSyM/main.tex").write_text(tex)
        gen = module("summarize", REPO / "experiments/sosym/summarize.py",
                     ROOT=root, TEX=root / "docs/paper/SoSyM/main.tex", OUT=root / "results/processed/sosym")
        with contextlib.redirect_stdout(io.StringIO()):
            gen.main()
        OUT.mkdir(exist_ok=True)
        shutil.copy(root / "results/processed/sosym/summary.json", OUT / "summary.json")
        return (root / "docs/paper/SoSyM/main.tex").read_text(), have_scipy


# ---------------------------------------------------------------- 2. hand-maintained macros
def manual_macros():
    """Recompute the macros above '%% BEGIN GENERATED macros' (first TLC campaign, proofs,
    trace validation, differential test, code size) from their records, using the same
    formulas as experiments/tse_paper.py and experiments/revision_paper.py."""
    d = load(EVIDENCE / "results/processed/document-service-v1/detailed-results.json")
    t = load(EVIDENCE / "results/processed/tse/tlc-extended.json")
    g = load(EVIDENCE / "results/processed/tse/graph.json")
    rev = module("revision_paper", REPO / "experiments/revision_paper.py")
    tlc, _ = rev.tlc_fragment(t)
    runs = g["differential"]["runs"]
    tla = sum(sum(1 for l in (REPO / "specification" / f).read_text().splitlines()
                  if l.strip() and not l.strip().startswith("\\*"))
              for f in ("Core.tla", "AsyncController.tla", "AtomicController.tla", "Refinement.tla"))
    m = {k: tlc[k] for k in ("TLCExtBaselines", "TLCExtMaxJobs", "TLCExtMaxStates", "TLCExtMaxGenerated",
                             "TLCExtMutants", "TLCExtMutantsCaught", "TLCExtRuns", "TLCExtSeconds")}
    m["TLCExtVersion"] = tlc["TLCExtVersion"].replace("(rev: ", "(rev.\\ ")
    m.update({"ProvedObligations": sum(r["proved_obligations"] for r in d["proofs"]["lemmas"]),
              "PolicyTables": fmt(d["policy_metrics"]["policy_tables_enumerated"]),
              "EventWords": fmt(d["policy_metrics"]["policy_event_words"]),
              "Scenarios": len(d["scenarios"]), "Corruptions": len(d["conformance"]["corruptions"]),
              "RegressionTests": len(d["tests"]), "DiffRuns": fmt(len(runs)),
              "DiffChanges": fmt(sum(r["changes"] for r in runs)), "TLALines": tla,
              "GraphLines": rev.code_lines("src/vgc/graph.py")})
    return {k: str(v) for k, v in m.items()}, d, t


# ---------------------------------------------------------------- 3. numbers in prose and appendix
def prose_checks(tex, d, t):
    flat = re.sub(r"\s+", " ", tex)
    # Appendix B (Table tab:tlc): rows typed by hand from tlc-extended.json
    by = {r["id"]: r for r in t["results"]}
    for rid, label in (("base-x_one-k2-m2", "One job & 1 & 2 & 2"), ("base-x_chain2-k1-m2", "Chain & 2 & 1 & 2"),
                       ("base-x_chain3-k2-m2", "Chain & 3 & 2 & 2"), ("base-x_chain4-k1-m2", "Chain & 4 & 1 & 2"),
                       ("base-x_chain5-k1-m1", "Chain & 5 & 1 & 1"), ("base-x_fanout3-k1-m2", "Fan-out & 3 & 1 & 2"),
                       ("base-x_diamond4-k2-m1", "Diamond & 4 & 2 & 1"), ("base-x_diamond4-k1-m2", "Diamond & 4 & 1 & 2")):
        r = by[rid]
        row = "%s & %s & %s & pass" % (label, fmt(r["distinct_states"]), fmt(r["generated_states"]))
        check(row in flat and r["status"] == "passed", "App. B baseline row: " + row)
    shown = {"base-x_one-k2-m2", "base-x_chain2-k1-m2", "base-x_chain3-k2-m2", "base-x_chain4-k1-m2",
             "base-x_chain5-k1-m1", "base-x_fanout3-k1-m2", "base-x_diamond4-k2-m1", "base-x_diamond4-k1-m2"}
    rest = sorted(r["distinct_states"] for r in t["results"] if r["id"].startswith("base-") and r["id"] not in shown)
    check(len(rest) == 6 and all(r["status"] == "passed" for r in t["results"] if r["id"].startswith("base-"))
          and "six further baselines (%s--%s distinct states)" % (fmt(rest[0]), fmt(rest[-1])) in flat,
          "App. B: six omitted baselines pass, %s--%s distinct states" % (fmt(rest[0]), fmt(rest[-1])))
    mut_names = {"no-cancel": "Cancellation removed", "no-recheck": "Recheck removed",
                 "obsolete-both": "Both obsolete-reply defenses removed", "budget-reset": "Exhausted budget reset",
                 "publish-suspended": "Suspension ignored in $\\Pub$", "revoked-authority": "Authority ignored",
                 "stale-publication": "Revision check removed", "contract-omitted": "Contract omitted from key",
                 "membership-omitted": "Selected context omitted from key"}
    for mid, name in mut_names.items():
        rs = [by["mut-%s-x_%s" % (mid, top)] for top in ("chain2", "chain3", "diamond4")]
        states = " / ".join(fmt(r["distinct_states"]) for r in rs)
        if all(r["status"] == "passed" for r in rs):
            res = "survives"
        else:
            res = "violated (%s)" % "/".join(str(r["trace_states"]) for r in rs)
        row = "%s & \\multicolumn{5}{r}{%s} & %s" % (name, states, res)
        check(row in flat, "App. B mutant row: %s -> %s, %s" % (name, states, res))
    # One-job campaign: 23 runs, 49 s; five witnesses reached within two actions
    core = d["models"] + d["mutations"] + d["witnesses"]
    secs = sum(r["elapsed_seconds"] for r in core)
    check(len(core) == 23 and "(23 runs, %.0f\\,s)" % secs in flat, "one-job campaign: %d runs, %.0f s" % (len(core), secs))
    check(len(d["witnesses"]) == 5 and all(r["status"] == "counterexample" and r["shortest_actions"] <= 2
                                           for r in d["witnesses"]),
          "five reachability witnesses, each reached within two actions")
    # Per-module TLAPS obligations quoted in Sec. 6.3
    ob = {r["module"]: r["proved_obligations"] for r in d["proofs"]["lemmas"]}
    for mod in ("Budget", "ControllerSafety", "StructuralKernelProofs", "DocumentPolicyProofs"):
        check(re.search(r"\\texttt\{%s\} \(%d[ )]" % (mod, ob[mod]), flat) is not None and all(
            r["status"] == "passed" for r in d["proofs"]["lemmas"]), "TLAPS %s: %d obligations, passed" % (mod, ob[mod]))
    # Trace validation: all scenarios admitted, all corruptions rejected
    check(all(s["status"] == "passed" for s in d["scenarios"]), "all %d scenarios pass" % len(d["scenarios"]))
    check(all(c["rejected"] for c in d["conformance"]["corruptions"]),
          "all %d corrupted traces rejected" % len(d["conformance"]["corruptions"]))
    check(all(x["status"] == "ok" for x in d["tests"]), "all %d regression tests ok" % len(d["tests"]))
    # RQ2 caption: 200 runs, feedback epoch in 193 of them
    imp = load(EVIDENCE / "results/raw/sosym/impact/runs.json")["runs"]
    ex = [r for r in imp if r["strategy"] == "exact"]
    fb = sum(any(v["edit"] == "FB" for v in r["revisions"]) for r in ex)
    check(len(ex) == 200 and "(200 runs per discipline" in flat and "in the %d runs whose initial" % fb in flat,
          "Table impact caption: %d runs, feedback epoch in %d" % (len(ex), fb))
    # 13 views at four ranks; three owners
    sys.path.insert(0, str(REPO / "experiments/sosym"))
    case = module("mde_case", REPO / "experiments/sosym/mde_case.py")
    jobs = case.make_jobs(case.initial_state())
    check(len(jobs) == 13 and len({j.rank for j in jobs}) == 4, "workflow model: %d jobs at %d ranks"
          % (len(jobs), len({j.rank for j in jobs})))
    # LLM calls: distinct calls of the 8 tabulated models; excluded model has 14
    calls = {p.parent.name: sum(1 for _ in p.open()) for p in (EVIDENCE / "results/raw/sosym/llm").glob("*/cache.jsonl")}
    tab = sum(n for m, n in calls.items() if m != "deepseek-coder-v2_16b")
    check(fmt(tab) == macros(tex)["LlmCalls"], "LLM cache lines of the eight models = \\LlmCalls (%s)" % fmt(tab))


# ---------------------------------------------------------------- 4. LLM replay
def replay_check():
    keys = ("strategy", "rep", "releases", "wrong_releases", "final_released", "final_wrong", "violations")
    for p in sorted((EVIDENCE / "results/raw/sosym/llm-replay").glob("*/runs.json")):
        orig = EVIDENCE / "results/raw/sosym/llm" / p.parent.name / "runs.json"
        a, b = load(orig)["runs"], load(p)["runs"]
        same = len(a) == len(b) and all({k: x.get(k) for k in keys} == {k: y.get(k) for k in keys}
                                        and x["metrics"]["dispatched"] == y["metrics"]["dispatched"]
                                        for x, y in zip(a, b))
        miss = load(p)["manifest"].get("cache_misses", sum(r.get("cache_misses", 0) for r in b))
        check(same and not miss, "LLM replay with current code identical to recorded runs: %s (cache misses %s)"
              % (p.parent.name, miss))


# ---------------------------------------------------------------- 5. source hashes
def source_hashes():
    files = {"kernel.py", "mde_case.py", "run_case.py", "summarize.py"}
    now = {f: sha256(REPO / "experiments/sosym" / f) for f in files}
    rows = []
    for p in sorted((EVIDENCE / "results/raw/sosym").glob("**/runs.json")):
        man = load(p)["manifest"]
        diff = sorted(f for f, h in man.get("sources", {}).items() if f != "summarize.py" and now.get(f) != h)
        rows.append((str(p.relative_to(EVIDENCE)), man.get("host", "?"), diff))
    for path, host, diff in rows:
        print("  info  %-48s %-16s %s" % (path, host, "matches checkout" if not diff else "differs: " + ", ".join(diff)))
    core = sum(not [f for f in d if f != "run_case.py"] for _, _, d in rows)
    notes.append("source hashes: kernel.py and mde_case.py match the checkout in %d of %d raw files; run_case.py "
                 "(driver) matches in %d; see README section 7" % (core, len(rows), sum(not d for _, _, d in rows)))


# ---------------------------------------------------------------- 6. optional re-execution
def rerun():
    """Re-execute the deterministic simulated campaigns with the current code and compare
    them run for run with the recorded raw files (about one minute on one core)."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        for cmd, n in (("sim", 500), ("impact", 200), ("sweep", 100)):
            subprocess.run([sys.executable, str(REPO / "experiments/sosym/run_case.py"), cmd, "--runs", str(n),
                            "--out", tmp], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            a = load(EVIDENCE / "results/raw/sosym" / cmd / "runs.json")["runs"]
            b = load(Path(tmp) / cmd / "runs.json")["runs"]
            check(a == b, "re-run `run_case.py %s --runs %d` identical to the recorded file (%d discipline runs)" % (cmd, n, len(a)))


# ---------------------------------------------------------------- main
def main():
    tex = PAPER.read_text()
    print("1. Generated blocks of main.tex (experiments/sosym/summarize.py on evidence/)")
    new, have_scipy = regenerate(tex)
    old_m, new_m = macros(tex), macros(new)
    old_b, new_b = dict(BLOCK.findall(tex)), dict(BLOCK.findall(new))
    gen_names = sorted(macros(old_b["macros"]))
    pexp = {"SimFullPexp", "SimUngatedPexp"}
    for k in gen_names:
        if k in pexp and not have_scipy:
            print("  SKIP  \\%s (needs scipy)" % k)
            continue
        check(old_m[k] == new_m.get(k), "\\%s = %s" % (k, old_m[k]) + ("" if old_m[k] == new_m.get(k)
                                                                    else "   regenerated: %s" % new_m.get(k)))
    for name in sorted(old_b):
        if name == "macros":
            continue
        rows = [l for l in old_b[name].splitlines() if l.strip()]
        ok = old_b[name] == new_b.get(name)
        check(ok, "table block %-16s %2d rows identical" % (name, len(rows)))
        (OUT / ("tab-%s.tex" % name.replace("tab-", ""))).write_text(new_b.get(name, ""))
    (OUT / "macros.tex").write_text(new_b["macros"])

    print("\n2. Hand-maintained macros (first TLC campaign, proofs, trace validation, code size)")
    man, d, t = manual_macros()
    for k, v in man.items():
        check(old_m.get(k) == v, "\\%s = %s" % (k, old_m.get(k)) + ("" if old_m.get(k) == v else "   recomputed: " + v))
    (OUT / "macros-manual.tex").write_text("".join("\\newcommand{\\%s}{%s}\n" % kv for kv in man.items()))

    print("\n3. Numbers typed in the prose, captions and Appendix B")
    prose_checks(tex, d, t)

    print("\n4. LLM campaign replayed from the cached calls with the current code")
    replay_check()

    print("\n5. Recorded source hashes vs. this checkout (report only)")
    source_hashes()

    if "--rerun" in sys.argv:
        print("\n6. Simulated campaigns re-executed with the current code (--rerun)")
        rerun()

    # claims.csv: every macro, where it is used, and its value
    body = tex.split("\\begin{document}", 1)[1]
    sections = [(m.start(), m.group(1)) for m in re.finditer(r"\\section\*?\{([^}]*)\}", body)]
    src = {**{k: ("summarize.py", "results/raw/sosym, results/processed/sosym") for k in gen_names},
           **{k: ("revision_paper.py: tlc_fragment", "results/processed/tse/tlc-extended.json")
              for k in man if k.startswith("TLCExt")},
           **{k: ("tse_paper.py formulas", "results/processed/document-service-v1/detailed-results.json")
              for k in ("ProvedObligations", "PolicyTables", "EventWords", "Scenarios", "Corruptions", "RegressionTests")},
           "DiffRuns": ("revision_paper.py: graph_fragments", "results/processed/tse/graph.json"),
           "DiffChanges": ("revision_paper.py: graph_fragments", "results/processed/tse/graph.json"),
           "TLALines": ("revision_paper.py: effort", "specification/{Core,AsyncController,AtomicController,Refinement}.tla"),
           "GraphLines": ("revision_paper.py: effort", "src/vgc/graph.py")}
    with open(HERE / "claims.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["macro", "value", "used_in_sections", "evidence", "generator"])
        for k in list(man) + sorted(gen_names):
            used = sorted({next((s for p, s in reversed(sections) if p <= m.start()), "Abstract")
                           for m in re.finditer(r"\\%s(?![A-Za-z])" % k, body)})
            gen, ev = src.get(k, ("--", "--"))
            w.writerow([k, old_m[k], "; ".join(used) or "(not used in text)", ev, gen])

    print()
    for n in notes:
        print("  note  " + n)
    if failures:
        print("\n%d CHECK(S) FAILED" % len(failures))
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
