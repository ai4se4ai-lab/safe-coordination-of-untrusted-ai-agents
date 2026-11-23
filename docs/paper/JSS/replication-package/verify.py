#!/usr/bin/env python3
"""Regenerate every number, table row and figure cell of the JSS manuscript from the
evidence in this package, then compare the result with ../main.tex.

    python docs/paper/JSS/replication-package/verify.py

Needs only the Python standard library (3.10+). Nothing is re-run: the script re-reads the
recorded logs under evidence/ and executes the repository's own generators
(experiments/tse_paper.py and experiments/revision_paper.py) on them. The regenerated
TeX fragments and their provenance hashes are written to generated/.

Exit code 0 means that all checks passed.
"""
from collections import defaultdict
from pathlib import Path
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PAPER = HERE.parent / "main.tex"
EVIDENCE = HERE / "evidence"
OUT = HERE / "generated"
MACRO = re.compile(r"\\newcommand\{\\(\w+)\}\{(.*)\}\s*$")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def macros(text):
    return {m.group(1): m.group(2) for line in text.splitlines() if (m := MACRO.match(line.strip()))}


def build_root(tmp):
    """A repository-shaped tree: recorded evidence (copied) + the repository's code (linked)."""
    root = Path(tmp)
    shutil.copytree(EVIDENCE / "results", root / "results")
    shutil.copytree(EVIDENCE / "hpc-fetched", root / "hpc" / "fetched")
    for code in ("experiments", "src", "specification"):
        (root / code).symlink_to(REPO / code, target_is_directory=True)
    return root


def run_generators(root):
    OUT.mkdir(exist_ok=True)
    for name in ("tse_paper", "revision_paper"):
        spec = importlib.util.spec_from_file_location(name, REPO / "experiments" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.ROOT, mod.OUT = root, OUT
        if hasattr(mod, "DETAIL"):
            mod.DETAIL = root / "results/processed/document-service-v1/detailed-results.json"
        # revision_paper.py opens some paths relative to the working directory, so run inside the tree
        argv, cwd, sys.argv = sys.argv, os.getcwd(), [name]
        os.chdir(root)
        try:
            mod.main()
        finally:
            sys.argv = argv
            os.chdir(cwd)


def check_macros(paper):
    body = paper.split("\\begin{document}", 1)[1]
    stated = {k: v for k, v in macros(paper).items() if k[0].isupper() and not v.startswith("\\")}
    gen = {}
    for f in ("numbers.tex", "numbers-r1.tex"):
        gen.update(macros((OUT / f).read_text()))
    used = {k for k in stated if re.search(r"\\%s(?![A-Za-z])" % k, body)}
    bad = [(k, stated[k], gen.get(k)) for k in sorted(stated) if stated[k] != gen.get(k)]
    print(f"[macros] {len(stated)} number macros in main.tex ({len(used)} used in the text); "
          f"{len(stated) - len(bad)} equal to the regenerated value")
    for k, s, g in bad:
        print(f"   MISMATCH \\{k}: manuscript={s!r} regenerated={g!r}")
    return not bad


# generated fragments that the JSS manuscript inlines (the others belong to the formal companion paper)
JSS_FRAGMENTS = ("fig-ablation", "fig-cost", "tab-coupled", "tab-sched", "tab-llm", "tab-llm-cutoff",
                 "tab-llm-cost", "tab-bench")


def check_fragments(paper):
    text, ok = norm(paper), True
    for name in JSS_FRAGMENTS:
        rows = [norm(l) for l in (OUT / f"{name}.tex").read_text().splitlines()
                if len(l.strip()) > 10 and ("&" in l or "\\fill" in l or "coordinates" in l or "\\node[font=\\tiny" in l)
                # captions, header rows and column layouts were reworded/resized for JSS; data rows were not
                and not l.lstrip().startswith(("\\caption", "\\begin{tabular", "Model &", "$f$ &"))]
        missing = [r for r in rows if r not in text]
        ok &= not missing
        print(f"[{name}] {len(rows) - len(missing)}/{len(rows)} data rows/cells found verbatim in main.tex")
        for r in missing:
            print("   MISSING", r[:160])
    return ok


def prune_generated():
    keep = {f"{n}.tex" for n in JSS_FRAGMENTS} | {"numbers.tex", "numbers-r1.tex", "provenance.json", "provenance-r1.json"}
    for f in OUT.iterdir():
        if f.name not in keep:
            f.unlink()


# macro-name prefix -> (evidence file, generator function, what produced the evidence)
SOURCES = [
    (("PreFix",), "results/processed/tse/prefix-defect.json", "tse_paper.py",
     "experiments/tse_campaign.py run on the pre-fix controller"),
    (("Abl", "Full", "GlobalPublish", "Obsolete", "ContractStale", "ContextStale", "Budget", "Candidate", "Upstream",
      "Authority", "EnabledOnly"), "results/processed/tse/campaign.json [ablation]", "tse_paper.py",
     "experiments/tse_campaign.py"),
    (("Cost", "Ratio", "BytesRatio", "ExactReq", "FullReq", "ExactKB", "WorkspaceKB", "FullKB", "Campaign"),
     "results/processed/tse/campaign.json [cost]", "tse_paper.py", "experiments/tse_campaign.py"),
    (("Coupled", "Sched", "Diff"), "results/processed/tse/graph.json", "revision_paper.py",
     "experiments/graph_experiments.py"),
    (("Llm",), "runs listed in results/processed/tse/llm-runs.json (results.json + calls.jsonl)", "revision_paper.py",
     "experiments/llm_study.py --part all (hpc/slurm/vgc_llm.sbatch on HPC)"),
    (("Bench",), "hpc-fetched/rorqual/outputs/full/benchmark/*/results-*.json", "revision_paper.py",
     "experiments/benchmark_study.py (hpc/slurm/vgc_llm.sbatch on HPC)"),
    (("GraphLines", "SandboxLines", "WorkflowDecl", "WorkflowValidator", "BenchDecl", "TLALines"),
     "source code (src/vgc/graph.py, experiments/llm/*.py, experiments/benchmark_study.py)", "revision_paper.py",
     "non-blank, non-comment line count"),
    (("TLC", "Scenario", "Corruptions", "Proved", "Policy", "EventWords", "Regression", "Python"),
     "results/processed/document-service-v1/detailed-results.json, tse/tlc-extended.json", "tse_paper.py / revision_paper.py",
     "formal companion paper (not cited in the JSS text)"),
]


def write_claims(paper):
    pre, body = paper.split("\\begin{document}", 1)
    stated = {k: v for k, v in macros(pre).items() if k[0].isupper() and not v.startswith("\\")}
    where, sec = defaultdict(list), "Abstract"
    for line in body.splitlines():
        if m := re.search(r"\\(?:sub)?section\*?\{([^}]*)\}", line):
            sec = m.group(1)
        if line.lstrip().startswith("%"):
            continue
        for k in re.findall(r"\\(\w+)", line):
            if k in stated and sec not in where[k]:
                where[k].append(sec)
    import csv
    with open(HERE / "claims.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["macro", "value", "used_in_sections", "evidence", "generator (experiments/)", "evidence produced by"])
        for k in stated:
            src = next((s for s in SOURCES if k.startswith(s[0])), ("", "?", "?", "?"))
            w.writerow(["\\" + k, stated[k], "; ".join(where[k]) or "(not used in the JSS text)", *src[1:]])


def check_rq3_feedback(root):
    """Per-stage counts quoted in the RQ3 prose ('290 jobs ... 212', '153 of 165 designs', ...)."""
    runs = json.loads((root / "results/processed/tse/llm-runs.json").read_text())["runs"]
    tot, rec = defaultdict(int), defaultdict(int)
    for e in runs:
        r = json.loads((root / e).read_text())
        for row in r.get("completion", []):
            for phase in ("outcomes", "epoch_outcomes"):
                by = defaultdict(list)
                for o in row[phase]:
                    by[o["job"]].append(o)
                for job, os_ in by.items():
                    os_.sort(key=lambda o: o["attempt"])
                    if os_ and os_[0]["outcome"] == "rejected":
                        stage = job.split("/")[0]
                        tot[stage] += 1
                        rec[stage] += any(o["outcome"] == "committed" for o in os_)
    expect = {"all": (212, 290), "design": (153, 165), "implementation": (19, 68), "verification": (40, 57)}
    got = {s: (rec[s], tot[s]) for s in tot}
    got["all"] = (sum(rec.values()), sum(tot.values()))
    ok = all(got.get(s) == v for s, v in expect.items())
    print("[rq3-feedback] recovered/rejected-first per stage:",
          ", ".join(f"{s} {got.get(s, ('-', '-'))[0]}/{got.get(s, ('-', '-'))[1]}" for s in expect),
          "OK" if ok else "MISMATCH with the prose of Section RQ3")
    return ok


def report_source_hashes(root):
    """Informational: every result file records SHA-256 hashes of the code that produced it.
    Compare them with the code in this checkout (README, 'Known deviations', explains the differences)."""
    import glob
    import hashlib
    files = ["results/processed/tse/campaign.json", "results/processed/tse/graph.json"]
    files += json.loads((root / "results/processed/tse/llm-runs.json").read_text())["runs"]
    files += sorted(str(Path(f).relative_to(root)) for f in
                    glob.glob(str(root / "hpc/fetched/*/outputs/full/benchmark/*/results-*.json")))
    for f in files:
        recorded = json.loads((root / f).read_text()).get("source_sha256", {})
        differ = [p for p, h in recorded.items()
                  if not (REPO / p).is_file() or hashlib.sha256((REPO / p).read_bytes()).hexdigest() != h]
        label = f.replace("hpc/fetched/", "hpc-fetched/")
        print(f"[source-hash] {label}: {len(recorded) - len(differ)}/{len(recorded)} files identical"
              + (f"; differs: {', '.join(differ)}" if differ else ""))


def main():
    paper = PAPER.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        root = build_root(tmp)
        run_generators(root)
        results = [check_macros(paper), check_fragments(paper), check_rq3_feedback(root)]
        report_source_hashes(root)
    prune_generated()
    write_claims(paper)
    print("ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
