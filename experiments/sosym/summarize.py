"""Aggregate the SoSyM case-study and TLC-scaling results into LaTeX fragments.

    python experiments/sosym/summarize.py

Reads  results/raw/sosym/{sim,impact,sweep}/runs.json, results/raw/sosym/llm/*/{runs.json,cache.jsonl},
       results/processed/sosym/tlc-scaling*.json
Writes results/processed/sosym/summary.json and fills the blocks marked
"%% BEGIN GENERATED <name>" ... "%% END GENERATED <name>" in docs/paper/SoSyM/main.tex,
so that the manuscript is a single self-contained .tex file.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import random
import re
import statistics as st

from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[2]
TEX = ROOT / "docs/paper/SoSyM/main.tex"


class Blocks(dict):
    """Collects generated blocks; .write() splices them into main.tex."""

    def put(self, name, text):
        self[name] = text if text.endswith("\n") else text + "\n"

    def write(self):
        tex = TEX.read_text()
        for name, text in self.items():
            pat = re.compile(r"(%% BEGIN GENERATED " + re.escape(name) + r"\n)(.*?)(%% END GENERATED "
                             + re.escape(name) + r"\n)", re.S)
            if not pat.search(tex):
                raise SystemExit("no block %s in %s" % (name, TEX))
            tex = pat.sub(lambda m: m.group(1) + text + m.group(3), tex)
        TEX.write_text(tex)
OUT = ROOT / "results/processed/sosym"
ORDER = ["exact", "ungated", "datakey", "lww", "full"]
NAMES = {"exact": "Observation-relative (ours)", "ungated": "Exact keys, no gate", "datakey": "Data-only keys (OCC/build)",
         "lww": "Last writer wins", "full": "Full regeneration"}
LABEL = {"S3 current validity": "S3", "S3 upstream currency": "S3 (upstream)",
         "S2/S4 authorised provenance": "S2/S4", "S6 episode budget": "S6", "L1 request currency": "L1"}
EDIT_DESC = {"initial": "initial model", "E1": "reworded requirement", "E2": "new attribute + invariant",
             "E3": "changed lifecycle", "E4": "new OCL contract", "E5": "naming rule in context",
             "E6": "agent revoked, views reassigned", "E7": "new lifecycle event", "FB": "feedback epoch (string ids)"}


def fmt(x):
    return "{:,}".format(x)


def pct(a, b):
    return "%.1f" % (100.0 * a / b) if b else "--"


CHANGES = ["initial", "E1", "E2", "E3", "E4", "E5", "E6", "E7"]


def boot_ci(xs, n=10_000, seed=1):
    """Percentile bootstrap 95% CI of the mean."""
    rng = random.Random(seed)
    means = sorted(st.mean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def points_of(r):
    """(change, released, wrong) per quiescent point; LLM runs keep full points, sim runs compact ones."""
    if "points" in r:
        return [tuple(x) for x in r["points"]]
    edit_of = {rev["rev"]: rev["edit"] for rev in r["revisions"] if rev["edit"] != "FB"}
    out = []
    for p in r["quiescent"]:
        last = max(rv for rv in edit_of if rv <= p["rev"])
        out.append((edit_of[last], bool(p["released"]), bool(p["released"] and p["issues"])))
    return out


def per_change(rows):
    """Releases and wrong releases attributed to the most recent change, per strategy."""
    t = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        for ch, rel, wrong in points_of(r):
            t[r["strategy"]][ch][0] += rel
            t[r["strategy"]][ch][1] += wrong
    return {s: dict(d) for s, d in t.items()}


def sim_summary():
    runs = json.loads((ROOT / "results/raw/sosym/sim/runs.json").read_text())
    man, rows = runs["manifest"], runs["runs"]
    by = defaultdict(list)
    for r in rows:
        by[r["strategy"]].append(r)
    out = {}
    for s in ORDER:
        rs = by[s]
        viol = Counter()
        for r in rs:
            viol.update({k: 1 for k in r["violations"]})
        rel = sum(r["releases"] for r in rs)
        out[s] = {"runs": len(rs), "requests_mean": st.mean(r["metrics"]["dispatched"] for r in rs),
                  "releases": rel, "wrong_releases": sum(r["wrong_releases"] for r in rs),
                  "runs_with_wrong_release": sum(r["wrong_releases"] > 0 for r in rs),
                  "final_released": sum(r["final_released"] for r in rs),
                  "final_wrong": sum(r["final_wrong"] for r in rs),
                  "violation_runs": dict(viol),
                  "max_episodes": max(r["max_episodes_per_view_and_revision"] for r in rs),
                  "runs_multi_episode": sum(r["max_episodes_per_view_and_revision"] > 1 for r in rs),
                  "bound_ok": sum(r["dispatch_bound_ok"] for r in rs),
                  "discarded": sum(r["metrics"]["discarded"] for r in rs),
                  "obsolete_installed": sum(r["metrics"]["obsolete_installed"] for r in rs),
                  "issue_kinds": dict(sum((Counter(r["issue_kinds"]) for r in rs), Counter())),
                  "issue_views": dict(sum((Counter(r["issue_views"]) for r in rs), Counter()))}
    # Per-run share of wrong releases (runs are the independent units) and paired cost tests.
    for s in ORDER:
        shares = [r["wrong_releases"] / r["releases"] for r in by[s] if r["releases"]]
        out[s]["wrong_share_run_mean"] = st.mean(shares) if shares else 0.0
        out[s]["wrong_share_run_ci"] = boot_ci(shares) if shares else (0.0, 0.0)
        out[s]["requests_sd"] = st.stdev(r["metrics"]["dispatched"] for r in by[s])
    seeds = {s: {r["seed"]: r["metrics"]["dispatched"] for r in by[s]} for s in ORDER}
    for other in ("full", "ungated"):
        common = sorted(set(seeds["exact"]) & set(seeds[other]))
        a, b = [seeds["exact"][i] for i in common], [seeds[other][i] for i in common]
        out[other]["wilcoxon_vs_exact_p"] = wilcoxon(a, b).pvalue
        out[other]["paired_diff_ci"] = boot_ci([y - x for x, y in zip(a, b)])
    out["per_change"] = per_change(rows)
    # Impact of each change: views that start a stale episode, for edits applied at quiescence.
    impact = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for rev in r["revisions"]:
            if not rev["mid"]:
                impact[rev["edit"]][r["strategy"]].append(rev["work_views"])
    imp = {e: {s: (st.mean(v) if v else None, len(v)) for s, v in d.items()} for e, d in impact.items()}
    clean = ROOT / "results/raw/sosym/impact/runs.json"
    if clean.exists():
        impact = defaultdict(lambda: defaultdict(list))
        for r in json.loads(clean.read_text())["runs"]:
            for rev in r["revisions"]:
                impact[rev["edit"]][r["strategy"]].append((rev["work_views"], rev["work_episodes"], rev["dispatches"]))
        imp = {e: {s: tuple(st.mean(x[i] for x in v) for i in range(3)) + (len(v),) for s, v in d.items()}
               for e, d in impact.items()}
    return man, out, imp


def llm_summary():
    paths = sorted((ROOT / "results/raw/sosym/llm").glob("*/runs.json"))
    models = {}
    for p in paths:
        d = json.loads(p.read_text())
        if not d["runs"]:
            continue
        m = d["runs"][0]["model"]
        if m in models and len(models[m]) >= len(d["runs"]):
            continue
        models[m] = d["runs"]
    table = {}
    for m, rows in sorted(models.items()):
        by = defaultdict(list)
        for r in rows:
            by[r["strategy"]].append(r)
        reps = len(by["exact"])
        cache = None
        for p in paths:
            if p.parent.name == m.replace(":", "_").replace("/", "_") and (p.parent / "cache.jsonl").exists():
                cache = p.parent / "cache.jsonl"
        calls = []
        if cache:
            calls = [json.loads(x) for x in cache.read_text().splitlines()]
        table[m] = {"reps": reps, "distinct_calls": len(calls),
                    "first_attempt_accept": None, "strategies": {}}
        for s in ORDER:
            rs = by[s]
            if not rs:
                continue
            rel = sum(r["releases"] for r in rs)
            table[m]["strategies"][s] = {
                "reps": len(rs), "requests": sum(r["metrics"]["dispatched"] for r in rs),
                "tokens": sum(r.get("tokens", 0) for r in rs), "releases": rel,
                "wrong_releases": sum(r["wrong_releases"] for r in rs),
                "final_released": sum(r["final_released"] for r in rs),
                "final_wrong": sum(r["final_wrong"] for r in rs),
                "rejected": sum(r["metrics"]["rejected"] for r in rs),
                "discarded": sum(r["metrics"]["discarded"] for r in rs),
                "obsolete_installed": sum(r["metrics"]["obsolete_installed"] for r in rs),
                "violation_runs": dict(sum((Counter({k: 1 for k in r["violations"]}) for r in rs), Counter())),
                "max_episodes": max(r["max_episodes_per_view_and_revision"] for r in rs),
                "stale_runs": sum(1 for r in rs if any(k in r["violations"] for k in
                                  ("S3 current validity", "S2/S4 authorised provenance"))),
                "issue_views": dict(sum((Counter(r["issue_views"]) for r in rs), Counter())),
                "failed_views": dict(Counter(v for r in rs for v in r["quiescent"][-1]["failed"]))}
        table[m]["per_change"] = per_change(rows)
        # distinct state-machine proposals that add an event outside the lifecycle ("other" rows)
        table[m]["sm_other_calls"] = sum(1 for c in calls if c["job"].startswith("sm/") and '"other"' in c["response"])
        table[m]["empty_replies"] = sum(1 for c in calls if not c["response"].strip())
        table[m]["max_call_seconds"] = max((c.get("seconds") or 0 for c in calls), default=0)
    return table


def excluded_models():
    """Models with a cache but no completed repetition (reported, not tabulated)."""
    out = {}
    for d in sorted((ROOT / "results/raw/sosym/llm").iterdir()):
        if (d / "cache.jsonl").exists() and not (d / "runs.json").exists():
            calls = [json.loads(x) for x in (d / "cache.jsonl").read_text().splitlines()]
            out[d.name] = {"calls": len(calls), "max_seconds": max(c.get("seconds") or 0 for c in calls),
                           "min_seconds": min(c.get("seconds") or 0 for c in calls)}
    return out


def sweep_summary():
    p = ROOT / "results/raw/sosym/sweep/runs.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    cell = defaultdict(list)
    for r in d["runs"]:
        cell[(r["factor"], r["value"], r["strategy"])].append(r)
    out = {}
    for (f, v, s), rs in cell.items():
        rel = sum(r["releases"] for r in rs)
        out.setdefault((f, v), {})[s] = {"runs": len(rs), "releases": rel,
                                         "wrong": sum(r["wrong_releases"] for r in rs),
                                         "requests": st.mean(r["requests"] for r in rs),
                                         "final_released": sum(r["final_released"] for r in rs)}
    return d["manifest"], out


def tlc_summary():
    p = OUT / "tlc-scaling.json"
    if not p.exists():
        return None
    base = json.loads(p.read_text())
    by_id = {r["id"]: r for r in base["results"]}
    hosts = []
    for extra in sorted(OUT.glob("tlc-scaling-*.json")):       # large instances run on HPC CPU nodes
        d = json.loads(extra.read_text())
        for r in d["results"]:
            if r["status"] != "error" and (r["id"] not in by_id or by_id[r["id"]]["status"] == "timeout"):
                by_id[r["id"]] = dict(r, workers=d["workers"])
                hosts.append(d["workers"])
    base["results"] = list(by_id.values())
    base["hpc_workers"] = max(hosts) if hosts else None
    return base


def main():
    gen = Blocks()
    OUT.mkdir(parents=True, exist_ok=True)
    man, sim, imp = sim_summary()
    llm = llm_summary()
    tlc = tlc_summary()
    excl = excluded_models()
    sweep = sweep_summary()
    (OUT / "summary.json").write_text(json.dumps({"sim": sim, "impact": imp, "llm": llm, "excluded": excl,
                                                  "sweep": {"%s=%s" % k: v for k, v in sweep[1].items()} if sweep else None},
                                                 indent=1, default=str) + "\n")
    macros = {}
    e, n = sim["exact"], sim["exact"]["runs"]
    macros.update({"SimRuns": fmt(n), "SimPerr": "%.2f" % man["p_err"], "SimBudget": man["budget"],
                   "SimPmid": "%.1f" % man["p_mid"],
                   "SimExactReleases": fmt(e["releases"]), "SimExactWrong": fmt(e["wrong_releases"]),
                   "SimExactRequests": "%.1f" % e["requests_mean"],
                   "SimFullRequests": "%.1f" % sim["full"]["requests_mean"],
                   "SimFullRatio": "%.1f" % (sim["full"]["requests_mean"] / e["requests_mean"]),
                   "SimDataWrong": fmt(sim["datakey"]["wrong_releases"]),
                   "SimDataReleases": fmt(sim["datakey"]["releases"]),
                   "SimDataWrongPct": pct(sim["datakey"]["wrong_releases"], sim["datakey"]["releases"]),
                   "SimLwwWrong": fmt(sim["lww"]["wrong_releases"]), "SimLwwReleases": fmt(sim["lww"]["releases"]),
                   "SimLwwWrongPct": pct(sim["lww"]["wrong_releases"], sim["lww"]["releases"]),
                   "SimLwwObsolete": fmt(sim["lww"]["obsolete_installed"]),
                   "SimExactDiscarded": fmt(e["discarded"]),
                   "SimUngatedMaxEp": sim["ungated"]["max_episodes"],
                   "SimUngatedMultiRuns": fmt(sim["ungated"]["runs_multi_episode"]),
                   "SimUngatedRequests": "%.1f" % sim["ungated"]["requests_mean"],
                   "SimExactFinal": fmt(e["final_released"]),
                   "SimDataFinalWrong": fmt(sim["datakey"]["final_wrong"]),
                   "SimLwwFinalWrong": fmt(sim["lww"]["final_wrong"]),
                   "SimDataShare": "%.1f" % (100 * sim["datakey"]["wrong_share_run_mean"]),
                   "SimDataShareLo": "%.1f" % (100 * sim["datakey"]["wrong_share_run_ci"][0]),
                   "SimDataShareHi": "%.1f" % (100 * sim["datakey"]["wrong_share_run_ci"][1]),
                   "SimLwwShare": "%.1f" % (100 * sim["lww"]["wrong_share_run_mean"]),
                   "SimLwwShareLo": "%.1f" % (100 * sim["lww"]["wrong_share_run_ci"][0]),
                   "SimLwwShareHi": "%.1f" % (100 * sim["lww"]["wrong_share_run_ci"][1]),
                   "SimExactSd": "%.1f" % e["requests_sd"], "SimFullSd": "%.1f" % sim["full"]["requests_sd"],
                   "SimFullDiffLo": "%.1f" % sim["full"]["paired_diff_ci"][0],
                   "SimFullDiffHi": "%.1f" % sim["full"]["paired_diff_ci"][1],
                   "SimUngatedDiffLo": "%.1f" % sim["ungated"]["paired_diff_ci"][0],
                   "SimUngatedDiffHi": "%.1f" % sim["ungated"]["paired_diff_ci"][1],
                   "SimFullPexp": "%d" % math.ceil(math.log10(max(sim["full"]["wilcoxon_vs_exact_p"], 1e-300))),
                   "SimUngatedPexp": "%d" % math.ceil(math.log10(max(sim["ungated"]["wilcoxon_vs_exact_p"], 1e-300))),
                   "SimExactBound": "%.1f" % (300.0 / n),
                   "SimBoundOk": fmt(e["bound_ok"])})
    pc = sim["per_change"]
    pre = [c for c in CHANGES if c not in ("E4", "E5", "E6", "E7")]
    post = ["E4", "E5", "E6", "E7"]
    for s, tag in (("datakey", "Data"), ("lww", "Lww")):
        rel_pre = sum(pc[s].get(c, [0, 0])[0] for c in pre)
        wr_pre = sum(pc[s].get(c, [0, 0])[1] for c in pre)
        rel_post = sum(pc[s].get(c, [0, 0])[0] for c in post)
        wr_post = sum(pc[s].get(c, [0, 0])[1] for c in post)
        macros.update({"Sim%sPreRel" % tag: fmt(rel_pre), "Sim%sPreWrong" % tag: fmt(wr_pre),
                       "Sim%sPostRel" % tag: fmt(rel_post), "Sim%sPostWrong" % tag: fmt(wr_post)})
    # ---- Table: stochastic campaign
    lines = []
    for s in ORDER:
        x = sim[s]
        v = x["violation_runs"]
        lines.append("%s & %.1f & %s & %s (%s\\%%) & %s & %s & %d & %s \\\\" % (
            NAMES[s], x["requests_mean"], fmt(x["releases"]), fmt(x["wrong_releases"]),
            pct(x["wrong_releases"], x["releases"]), fmt(x["final_wrong"]),
            ", ".join(LABEL[k] for k in sorted(v)) or "none", x["max_episodes"],
            fmt(x["obsolete_installed"])))
    gen.put("tab-sim", "\n".join(lines) + "\n")
    # ---- Table: wrong releases per change (simulated and LLM agents)
    lpc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for m, d in llm.items():
        for s, dd in d["per_change"].items():
            for c, (rel, wr) in dd.items():
                lpc[s][c][0] += rel
                lpc[s][c][1] += wr
    lines = []
    for c in CHANGES:
        cells = []
        for src in (pc, lpc):
            for s in ("exact", "datakey", "lww"):
                rel, wr = src.get(s, {}).get(c, [0, 0])
                cells.append("%s/%s" % (fmt(wr), fmt(rel)))
        lines.append("%s & %s \\\\" % (c, " & ".join(cells)))
    gen.put("tab-perchange", "\n".join(lines) + "\n")
    # ---- Table: sensitivity
    if sweep:
        smac, sw = sweep
        macros["SweepRuns"] = smac["runs"]
        lines = []
        names = {"p_mid": "$p_{\\mathrm{mid}}$", "p_err": "$p_{\\mathrm{err}}$", "budget": "$k$"}
        for (f, v) in sorted(sw, key=lambda k: (["p_mid", "p_err", "budget"].index(k[0]), k[1])):
            x = sw[(f, v)]
            lines.append("%s $=%s$ & %s/%s & %s/%s & %s/%s & %d & %.1f & %.1f \\\\" % (
                names[f], v, fmt(x["exact"]["wrong"]), fmt(x["exact"]["releases"]),
                fmt(x["datakey"]["wrong"]), fmt(x["datakey"]["releases"]),
                fmt(x["lww"]["wrong"]), fmt(x["lww"]["releases"]), x["exact"]["final_released"],
                x["exact"]["requests"], x["full"]["requests"] / x["exact"]["requests"]))
        gen.put("tab-sweep", "\n".join(lines) + "\n")
        allw = [x[s]["wrong"] for x in sw.values() for s in ("exact",)]
        macros["SweepExactWrong"] = sum(allw)
        ratios = [x["full"]["requests"] / x["exact"]["requests"] for x in sw.values()]
        macros["SweepRatioMin"], macros["SweepRatioMax"] = "%.1f" % min(ratios), "%.1f" % max(ratios)
    # ---- Table: impact per change
    lines = []
    for ed in ["initial", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "FB"]:
        if ed not in imp:
            continue
        row = [ed, EDIT_DESC[ed]]
        for s in ("exact", "coarse", "ungated", "datakey", "full"):
            x = imp[ed].get(s)
            if s == "ungated":
                row.append("--" if x is None else "%.1f" % x[1])      # episodes
            else:
                row.append("--" if x is None else "%.1f" % x[0])      # views
        lines.append(" & ".join(row) + " \\\\")
    gen.put("tab-impact", "\n".join(lines) + "\n")
    # ---- Table: LLM campaign
    lines, tot = [], Counter()
    for m, d in llm.items():
        ex, dk, lw, fu = (d["strategies"].get(s) for s in ("exact", "datakey", "lww", "full"))
        if not ex:
            continue
        lines.append("%s & %d & %s/%s & %s & %d & %s/%s & %d & %s/%s & %d & %s & %s \\\\" % (
            m.replace("_", "\\_"), d["reps"], fmt(ex["releases"]), fmt(ex["wrong_releases"]),
            fmt(ex["final_released"]), ex["stale_runs"],
            fmt(dk["releases"]), fmt(dk["wrong_releases"]), dk["stale_runs"],
            fmt(lw["releases"]), fmt(lw["wrong_releases"]), lw["stale_runs"],
            "%.1f" % (ex["tokens"] / max(1, ex["reps"]) / 1000), "%.1f" % (fu["tokens"] / max(1, fu["reps"]) / 1000)))
        for s, x in d["strategies"].items():
            for kk in ("releases", "wrong_releases", "requests", "tokens", "final_released", "final_wrong", "reps",
                       "obsolete_installed", "discarded", "stale_runs"):
                tot[s + ":" + kk] += x[kk]
    gen.put("tab-llm", "\n".join(lines) + "\n")
    macros.update({"LlmModels": len(llm), "LlmReps": sum(d["reps"] for d in llm.values()),
                   "LlmCalls": fmt(sum(d["distinct_calls"] for d in llm.values())),
                   "LlmExactReleases": fmt(tot["exact:releases"]), "LlmExactWrong": fmt(tot["exact:wrong_releases"]),
                   "LlmExactFinal": fmt(tot["exact:final_released"]),
                   "LlmDataReleases": fmt(tot["datakey:releases"]), "LlmDataWrong": fmt(tot["datakey:wrong_releases"]),
                   "LlmDataWrongPct": pct(tot["datakey:wrong_releases"], tot["datakey:releases"]),
                   "LlmLwwReleases": fmt(tot["lww:releases"]), "LlmLwwWrong": fmt(tot["lww:wrong_releases"]),
                   "LlmLwwWrongPct": pct(tot["lww:wrong_releases"], tot["lww:releases"]),
                   "LlmUngatedWrong": fmt(tot["ungated:wrong_releases"]), "LlmFullWrong": fmt(tot["full:wrong_releases"]),
                   "LlmTokenRatio": "%.1f" % (tot["full:tokens"] / max(1, tot["exact:tokens"])),
                   "LlmRequestRatio": "%.1f" % (tot["full:requests"] / max(1, tot["exact:requests"])),
                   "LlmDiscarded": fmt(tot["exact:discarded"]),
                   "LlmExactStale": tot["exact:stale_runs"], "LlmDataStale": tot["datakey:stale_runs"],
                   "LlmLwwStale": tot["lww:stale_runs"], "LlmRunsPerStrategy": tot["exact:reps"], "LlmLwwObsolete": fmt(tot["lww:obsolete_installed"])})
    top = max(llm, key=lambda m: llm[m]["strategies"]["exact"]["releases"])
    oth = max(llm, key=lambda m: llm[m]["sm_other_calls"])
    macros.update({"LlmTopModel": top.replace("_", "\\_"),
                   "LlmTopExactReleases": fmt(llm[top]["strategies"]["exact"]["releases"]),
                   "LlmTopDataWrong": fmt(llm[top]["strategies"]["datakey"]["wrong_releases"]),
                   "LlmModelsWithRelease": sum(1 for d in llm.values() if d["strategies"]["exact"]["releases"] > 0),
                   "LlmModelsComplete": sum(1 for d in llm.values() if d["strategies"]["exact"]["final_released"] > 0),
                   "LlmOtherModel": oth.replace("_", "\\_"), "LlmOtherCalls": llm[oth]["sm_other_calls"],
                   "LlmTopEmpty": llm[top]["empty_replies"],
                   "LlmExactBound": "%.1f" % (300.0 / max(1, tot["exact:releases"]))})
    if excl:
        name, x = next(iter(excl.items()))
        macros.update({"LlmExcludedCalls": x["calls"], "LlmExcludedMaxMin": "%.0f" % (x["max_seconds"] / 60),
                       "LlmExcludedMinS": "%.0f" % x["min_seconds"]})
    # ---- TLC scaling
    if tlc:
        res = tlc["results"]
        base = [r for r in res if r["id"].startswith("base-") and r["status"] == "passed"]
        mut = [r for r in res if r["id"].startswith("mut-")]
        lines = []
        for r in sorted(base, key=lambda r: (r["jobs"], r["k"], r["m"], r["topology"])):
            lines.append("%s & %d & %d & %d & %s & %s & %s & %.0f \\\\" % (
                r["topology"].replace("s_", "").replace("_", "\\_") + ("$^\\dagger$" if r.get("workers", 0) > tlc["workers"] else ""),
                r["jobs"], r["k"], r["m"],
                fmt(r["distinct_states"]), fmt(r["generated_states"]), r.get("diameter") or "--", r["seconds"]))
        for r in res:
            if r["status"] == "timeout":
                lines.append("%s & %d & %d & %d & \\multicolumn{3}{l}{not completed within %d\\,h} & -- \\\\" % (
                    r["topology"].replace("s_", "").replace("_", "\\_"), r["jobs"], r["k"], r["m"],
                    tlc["timeout_s"] // 3600))
        gen.put("tab-tlc-scaling", "\n".join(lines) + "\n")
        macros.update({"TLCScaleBaselines": len(base),
                       "TLCScaleMaxStates": fmt(max(r["distinct_states"] for r in base)),
                       "TLCScaleMaxGenerated": fmt(max(r["generated_states"] for r in base)),
                       "TLCScaleMaxJobs": max(r["jobs"] for r in base),
                       "TLCScaleHours": "%.1f" % (sum(r["seconds"] for r in base) / 3600),
                       "TLCScaleHpcRuns": sum(1 for r in base if r.get("workers", 0) > tlc["workers"]),
                       "TLCScaleMutants": len(mut),
                       "TLCScaleMutantsMet": sum(r["expectation_met"] for r in mut),
                       "TLCScaleAllMet": "yes" if all(r["expectation_met"] for r in res if r["status"] != "timeout") else "no",
                       "TLCScaleWorkers": tlc["workers"],
                       "TLCScaleHpcWorkers": tlc.get("hpc_workers") or "--",
                       "TLCScaleTimeouts": sum(r["status"] == "timeout" for r in res)})
    gen.put("macros", "".join("\\newcommand{\\%s}{%s}\n" % (k, v) for k, v in macros.items()))
    gen.write()
    print(json.dumps(macros, indent=1))


if __name__ == "__main__":
    main()
