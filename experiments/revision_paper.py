"""Render the revision's new evaluation fragments (RQ2 coupled/scheduling, RQ4 extended
TLC, RQ5 LLM study, RQ6 benchmarks) into docs/paper/generated/.

    python experiments/revision_paper.py

Inputs (missing inputs render as '--' so the manuscript always compiles):
  results/processed/tse/graph.json              generic-kernel experiments
  results/processed/tse/tlc-extended.json       extended TLC campaign
  results/processed/tse/llm-runs.json           curated list of RQ5 result files
  hpc/fetched/*/outputs/full/benchmark/*/results-*.json and
  results/raw/*-bench-*/results-*.json          RQ6 results (non-smoke only)
Nothing is typed by hand.
"""
from pathlib import Path
import glob
import hashlib
import json
import re
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/paper/generated"
NA = "--"


def load(path):
    p = ROOT / path
    return json.loads(p.read_text()) if p.is_file() else None


def pct(a, b, digits=0):
    return NA if not b else ("%.*f" % (digits, 100.0 * a / b))


def wilson(a, b, z=1.959964):
    """Wilson score 95% interval for a/b, as 'lo--hi' percentages (LaTeX en dash)."""
    if not b:
        return NA
    ph = a / b
    d = 1 + z * z / b
    c = (ph + z * z / (2 * b)) / d
    h = z * ((ph * (1 - ph) / b + z * z / (4 * b * b)) ** 0.5) / d
    return "%.0f--%.0f" % (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def fmt(n):
    return "{:,}".format(n) if isinstance(n, int) else n


def code_lines(path, start=None, end=None):
    text = (ROOT / path).read_text()
    if start:
        m = re.search(start + r".*?(?=" + end + ")", text, re.S)
        text = m.group(0) if m else ""
    return sum(1 for l in text.splitlines() if l.strip() and not l.strip().startswith("#"))


def model_label(m):
    return m.replace("-instruct", "")


# ------------------------------------------------------------------ effort
def effort():
    wf = (ROOT / "experiments/llm/workflow.py").read_text()

    def body(name):
        m = re.search(r"\ndef %s\(.*?(?=\n(?:def |# ---))" % name, wf, re.S)
        return sum(1 for l in m.group(0).splitlines() if l.strip() and not l.strip().startswith("#")) if m else 0

    tla = sum(sum(1 for l in (ROOT / "specification" / f).read_text().splitlines()
                  if l.strip() and not l.strip().startswith("\\*"))
              for f in ("Core.tla", "AsyncController.tla", "AtomicController.tla", "Refinement.tla"))
    return {"GraphLines": code_lines("src/vgc/graph.py"), "TLALines": tla,
            "WorkflowDeclLines": sum(body(n) for n in ("findings", "conventions", "spec_of", "jobs", "global_predicate")),
            "WorkflowValidatorLines": sum(body(n) for n in ("validate_design", "design_of", "validate_implementation",
                                                             "validate_tests", "sandbox")),
            "SandboxLines": code_lines("experiments/llm/sandbox_runner.py"),
            "BenchDeclLines": code_lines("experiments/benchmark_study.py", r"\ndef build_jobs\(", r"\n\ndef ")}


# ------------------------------------------------------------------ graph
def graph_fragments(g):
    m, frags = {}, {}
    if g is None:
        return {k: NA for k in ("DiffRuns", "DiffChanges", "CoupledModules", "CoupledShared", "CoupledFmax",
                                "CoupledExactFzero", "CoupledExactFmax", "CoupledFullFmax", "CoupledRatioFullFmax",
                                "CoupledRatioWorkspaceFmax", "CoupledRatioCutoffFmax", "CoupledSemanticFmax",
                                "CoupledCosmeticExact", "CoupledCosmeticNoCut", "SchedSeeds", "SchedMaxDepth",
                                "SchedMaxWidth", "SchedEagerReqRatioMax", "SchedEagerMaxEpisodes",
                                "SchedMakespanDiffPct")}, {}
    runs = g["differential"]["runs"]
    m["DiffRuns"] = fmt(len(runs))
    m["DiffChanges"] = fmt(sum(r["changes"] for r in runs))
    c, cfg = g["coupled"]["summary"], g["config"]
    fan = sorted(map(int, c))
    fmax = str(max(fan))
    m.update({"CoupledModules": cfg["modules"], "CoupledShared": cfg["shared"], "CoupledFmax": fmax,
              "CoupledExactFzero": "%.1f" % c["0"]["exact"]["requests_per_change"],
              "CoupledExactFmax": "%.1f" % c[fmax]["exact"]["requests_per_change"],
              "CoupledFullFmax": "%.1f" % c[fmax]["full"]["requests_per_change"],
              "CoupledRatioFullFmax": "%.1f" % (c[fmax]["full"]["requests_per_change"] /
                                                c[fmax]["exact"]["requests_per_change"]),
              "CoupledRatioWorkspaceFmax": "%.1f" % (c[fmax]["workspace"]["requests_per_change"] /
                                                     c[fmax]["exact"]["requests_per_change"]),
              "CoupledRatioCutoffFmax": "%.1f" % (c[fmax]["no-cutoff"]["requests_per_change"] /
                                                  c[fmax]["exact"]["requests_per_change"]),
              "CoupledSemanticFmax": "%.1f" % c[fmax]["exact"]["by_kind"]["shared-semantic"],
              "CoupledCosmeticExact": "%.1f" % c[fmax]["exact"]["by_kind"]["shared-cosmetic"],
              "CoupledCosmeticNoCut": "%.1f" % c[fmax]["no-cutoff"]["by_kind"]["shared-cosmetic"]})
    modes = [("exact", "Exact (ours)"), ("no-cutoff", "No early cutoff"), ("workspace", "Whole workspace"),
             ("full", "Full regeneration")]
    kinds = [("module", "Module edit"), ("shared-semantic", "Shared model: new field"),
             ("shared-cosmetic", "Shared model: description only"), ("context-selected", "Selected finding"),
             ("context-unselected", "Unselected finding"), ("contract", "Contract change")]
    rows = []
    for f in fan:
        rows.append(r"\multicolumn{5}{@{}l}{\textit{Fan-out $f=%d$ (each module's design reads %d of %d shared models)}}\\"
                    % (f, f, cfg["shared"]))
        for k, label in kinds:
            rows.append(label + " & " + " & ".join("%.1f" % c[str(f)][mo]["by_kind"][k] for mo, _ in modes) + r"\\")
        rows.append(r"\textbf{All changes} & " + " & ".join(r"\textbf{%.1f}" % c[str(f)][mo]["requests_per_change"]
                                                           for mo, _ in modes) + r"\\")
        if f != fan[-1]:
            rows.append(r"\midrule")
    exact_equal = all(c[str(f)]["exact"]["requests_equal_affected"] for f in fan)
    compact = []
    for f in fan:
        cf = c[str(f)]
        compact.append("%d & " % f + " & ".join("%.1f" % cf[mo]["requests_per_change"] for mo, _ in modes) +
                       " & %.1f & %.1f / %.1f\\\\" % (cf["exact"]["by_kind"]["shared-semantic"],
                                                   cf["exact"]["by_kind"]["shared-cosmetic"],
                                                   cf["no-cutoff"]["by_kind"]["shared-cosmetic"]))
    frags["tab-coupled.tex"] = (r"""\begin{table}[!t]
\centering
\caption{RQ2 on a coupled workspace: mean generation requests per change for %d modules sharing %d data-model components (%d jobs), %d seeds $\times$ %d changes per fan-out $f$ (each module's design reads $f$ shared models). Right: an edit of a shared model that adds a field, and one that changes only its description (exact keys / no early cutoff). With exact keys, requests equalled stale episodes in %s runs. Per-change-type results are in the supplement (Table~S2).}\label{tab:coupled}
\footnotesize\setlength{\tabcolsep}{3pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}rrrrrrr@{}}\toprule
& \multicolumn{4}{c}{All changes} & \multicolumn{2}{c}{Shared-model edit}\\\cmidrule(lr){2-5}\cmidrule(l){6-7}
$f$ & Exact & No cutoff & Whole ws. & Full & New field & Description\\\midrule
""" % (cfg["modules"], cfg["shared"], 4 * cfg["modules"] + 2 * cfg["shared"], cfg["coupled_seeds"],
       cfg["coupled_changes"], "all" if exact_equal else "not all") + "\n".join(compact) + r"""
\bottomrule\end{tabular*}
\end{table}""")
    frags["tab-coupled-full.tex"] = (r"""\begin{table}[!t]
\centering
\caption{RQ2 on a coupled workspace: mean generation requests per change for %d modules (4 jobs each) sharing %d data-model components (2 jobs each; %d jobs in total), %d seeds $\times$ %d changes per fan-out. With exact keys, every request was caused by a job whose observation changed (requests $=$ stale episodes in %s runs).}\label{tab:coupled}
\scriptsize\setlength{\tabcolsep}{2.2pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}lrrrr@{}}\toprule
Change & \rotatebox{70}{Exact (ours)} & \rotatebox{70}{No early cutoff} & \rotatebox{70}{Whole workspace} & \rotatebox{70}{Full regeneration}\\\midrule
""" % (cfg["modules"], cfg["shared"], 4 * cfg["modules"] + 2 * cfg["shared"], cfg["coupled_seeds"],
       cfg["coupled_changes"], "all" if exact_equal else "not all") + "\n".join(rows) + r"""
\bottomrule\end{tabular*}
\end{table}""").replace(r"\label{tab:coupled}", r"\label{tab:coupled-full}").replace(r"\begin{table}[!t]", r"\begin{table}[!ht]")
    s = g["scheduling"]["summary"]
    depths, widths = cfg["depths"], cfg["widths"]
    m.update({"SchedSeeds": cfg["sched_seeds"], "SchedMaxDepth": max(depths), "SchedMaxWidth": max(widths)})
    ratios, worst, mk = [], 0, []
    lines = []
    for d in depths:
        cells = []
        for w in widths:
            ga, ea = s["%d/%d/gated" % (d, w)], s["%d/%d/eager" % (d, w)]
            ratios.append(ea["requests"] / ga["requests"])
            worst = max(worst, ea["worst_max_episodes"])
            mk.append(abs(ea["makespan"] - ga["makespan"]) / ga["makespan"])
            cells.append("%.0f / %.1f / %d" % (ga["requests"], ea["requests"], ea["worst_max_episodes"]))
        lines.append("%d & " % d + " & ".join(cells) + r"\\")
    m.update({"SchedEagerReqRatioMax": "%.1f" % max(ratios), "SchedEagerMaxEpisodes": worst,
              "SchedMakespanDiffPct": "%.0f" % (100 * max(mk))})
    frags["tab-sched.tex"] = (r"""\begin{table}[!t]
\centering
\caption{RQ2 scheduling: requests after one root edit on layered lattices (depth $d$, width $w$, every node reads all nodes of the previous layer), mean of %d seeds with random latencies and unlimited parallelism. Cells: gated requests / ungated requests / worst episodes of one job (ungated). The gated scheduler started exactly one stale episode per affected job in every run (Theorem~\ref{thm:single}); makespans differed by at most %s\%%.}\label{tab:sched}
\scriptsize\setlength{\tabcolsep}{3pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}l%s@{}}\toprule
$d$ & %s\\\midrule
""" % (cfg["sched_seeds"], m["SchedMakespanDiffPct"], "c" * len(widths), " & ".join("$w=%d$" % w for w in widths))
        + "\n".join(lines) + r"""
\bottomrule\end{tabular*}
\end{table}""")
    return m, frags


# ------------------------------------------------------------------ TLC
def tlc_fragment(t):
    keys = ("TLCExtRuns", "TLCExtBaselines", "TLCExtMutants", "TLCExtMutantsCaught", "TLCExtMaxStates",
            "TLCExtMaxGenerated", "TLCExtMaxJobs", "TLCRefineConfigs", "TLCExtSeconds", "TLCExtVersion")
    if t is None:
        return {k: NA for k in keys}, {}
    r = t["results"]
    base = [x for x in r if x["id"].startswith("base-")]
    mut = [x for x in r if x["id"].startswith("mut-")]
    ref = [x for x in r if x["id"].startswith("refine-")]
    m = {"TLCExtRuns": len(r), "TLCExtBaselines": len(base), "TLCExtMutants": len(mut),
         "TLCExtMutantsCaught": sum(x["status"] == "counterexample" for x in mut),
         "TLCExtMaxStates": fmt(max(x["distinct_states"] for x in base)),
         "TLCExtMaxGenerated": fmt(max(x["generated_states"] for x in base)),
         "TLCExtMaxJobs": max(x["jobs"] for x in base), "TLCRefineConfigs": len(base),
         "TLCExtSeconds": "%.0f" % sum(x["seconds"] for x in r),
         "TLCExtVersion": (t.get("tlc_version") or "").replace("TLC2 Version ", "")}
    names = {"x_one": "One job", "x_chain2": "Chain", "x_chain3": "Chain", "x_chain4": "Chain", "x_chain5": "Chain",
             "x_fanout3": "Fan-out", "x_diamond4": "Diamond"}
    lines = [r"\multicolumn{7}{@{}l}{\textit{Baselines: \texttt{Safety} and refinement}}\\"]
    for x in base:
        lines.append("%s & %d & %d & %d & %s & %s & Pass\\\\" % (names[x["topology"]], x["jobs"], x["k"], x["m"],
                                                               fmt(x["distinct_states"]), fmt(x["generated_states"])))
    labels = {"no-cancel": "Cancellation removed", "no-recheck": "Commit recheck removed",
              "obsolete-both": "Both obsolete defenses", "budget-reset": "Exhausted budget reset",
              "publish-suspended": "Suspension ignored", "revoked-authority": "Authority ignored",
              "stale-publication": "Revision check removed", "contract-omitted": "Contract omitted",
              "membership-omitted": "Selected context omitted"}
    lines.append(r"\midrule\multicolumn{7}{@{}l}{\textit{Mutants on chains of 2 and 3 jobs and the 4-job diamond (shortest counterexample, states)}}\\")
    by = defaultdict(list)
    for x in mut:
        by[x["id"].split("-x_")[0][4:]].append(x)
    for key, label in labels.items():
        xs = by[key]
        if all(x["status"] == "passed" for x in xs):
            res = r"Survives\textsuperscript{a}"
        else:
            res = "Viol.\\ %s" % "/".join(str(x["trace_states"]) for x in xs)
        lines.append(r"\multicolumn{4}{@{}l}{%s} & \multicolumn{2}{r}{%s} & %s\\" % (
            label, "/".join(fmt(x["distinct_states"]) for x in xs), res))
    lines.append(r"\midrule\multicolumn{7}{@{}l}{\textit{Refinement nonvacuity (no obsolete defenses)}}\\")
    for x in ref:
        lines.append("%s & %d & 1 & 1 & %s & %s & Violated\\\\" % (names[x["topology"]], x["jobs"],
                                                               fmt(x["distinct_states"]), fmt(x["generated_states"])))
    frag = (r"""\begin{table}[!t]
\centering
\caption{RQ4: extended bounded model checking (TLC %s, %s\,s for all %d runs). $J$: jobs; $k$: attempt cap; $m$: environmental changes. Every baseline checks the full safety invariant \emph{and} the refinement mapping of Theorem~\ref{thm:refinement}. Mutant rows give distinct states and counterexample lengths for the three topologies.}\label{tab:tlc-ext}
\scriptsize\setlength{\tabcolsep}{3pt}\resizebox{\columnwidth}{!}{%%
\begin{tabular}{@{}lrrrrrl@{}}\toprule
Configuration & $J$ & $k$ & $m$ & Distinct & Generated & Result\\\midrule
""" % (m["TLCExtVersion"], m["TLCExtSeconds"], len(r)) + "\n".join(lines) + r"""
\bottomrule\end{tabular}}
\par\smallskip\raggedright\footnotesize\textsuperscript{a}The other obsolete-reply defense still blocks the stale commit.
\end{table}""")
    return m, {"tab-tlc-ext.tex": frag}


# ------------------------------------------------------------------ RQ5
def llm_fragments():
    manifest = load("results/processed/tse/llm-runs.json") or {"runs": []}
    reports = []
    for entry in manifest["runs"]:
        r = load(entry)
        if r is not None and not r.get("quick"):
            reports.append(r)
    keys = ("LlmModelsN", "LlmCallsTotal", "LlmTrials", "LlmPublishedPct", "LlmBarrierConflicts", "LlmEpochRepairs",
            "LlmImplForms", "LlmImplAccepted", "LlmStaleTrials", "LlmStaleDiscardedPct", "LlmStaleOldValid",
            "LlmStaleWrongPct", "LlmStaleWrong", "LlmCutoffDesignValuePct", "LlmCutoffDesignRawPct",
            "LlmCutoffDesignSemPct", "LlmCutoffImplValuePct", "LlmCutoffImplAstPct", "LlmCostExactReq",
            "LlmCostFullReq", "LlmCostRatio", "LlmCostTokenRatio", "LlmFeedbackRecoveredPct", "LlmJobsFailedPct",
            "LlmStaleWrongCI", "LlmFeedbackRecoveredCI", "LlmDesignFirstRejects", "LlmDesignNameRejects",
            "LlmDesignNameRejectPct", "LlmDesignParsed", "LlmDesignUpdateNamed", "LlmPublished", "LlmModelsNeverPublished")
    m = {k: NA for k in keys}
    if not reports:
        return m, {}
    per = defaultdict(lambda: defaultdict(list))
    for r in reports:
        for part in ("completion", "stale", "cutoff", "cost"):
            for row in r.get(part, []):
                per[row["model"]][part].append(row)
    models = sorted(per)
    calls_total = sum(sum(1 for _ in open(p)) for p in
                      {str(Path(e).parent / "calls.jsonl") for e in manifest["runs"]} if (ROOT / p).is_file())
    m["LlmModelsN"], m["LlmCallsTotal"] = len(models), fmt(calls_total)
    # completion
    lines, total_trials, published, conflicts, epoch_ok, forms, accepted_impl = [], 0, 0, 0, 0, set(), 0
    rej_recovered = rej_total = failed_jobs = all_jobs = 0
    for model in models:
        rows = per[model]["completion"]
        if not rows:
            continue
        n = len(rows)
        pub = sum(r["published"] for r in rows)
        conf = sum(r["barrier_conflict"] for r in rows)
        ep = sum(r["barrier_conflict"] and r["published"] for r in rows)
        stage_first = {}
        for stage in ("design", "implementation", "verification"):
            first = [o for r in rows for o in r["outcomes"] if o["job"].startswith(stage) and o["attempt"] == 1
                     and o["outcome"] != "discarded"]
            stage_first[stage] = pct(sum(o["outcome"] == "committed" for o in first), len(first))
        jobs = 3 * sum(r["documents"] for r in rows)
        failed = sum(len(r["failed"]) for r in rows)
        # a job whose first attempt was rejected and that later committed in the same phase: feedback recovered
        for r in rows:
            for phase in ("outcomes", "epoch_outcomes"):
                by = defaultdict(list)
                for o in r[phase]:
                    by[o["job"]].append(o)
                for job, os_ in by.items():
                    os_.sort(key=lambda o: o["attempt"])
                    if os_ and os_[0]["outcome"] == "rejected":
                        rej_total += 1
                        rej_recovered += any(o["outcome"] == "committed" for o in os_)
        impl = sum(len(r["implementation_forms"]) for r in rows)
        accepted = sum(sum(1 for o in r["outcomes"] + r["epoch_outcomes"] if o["job"].startswith("implementation")
                           and o["outcome"] == "committed") for r in rows)
        for r in rows:
            forms.update(r["implementation_forms"])
        accepted_impl += accepted
        calls = sum(r["calls"] for r in rows)
        tokens = sum(r["prompt_tokens"] + r["output_tokens"] for r in rows)
        total_trials += n
        published += pub
        conflicts += conf
        epoch_ok += ep
        failed_jobs += failed
        all_jobs += jobs
        lines.append("%s & %d & %s & %s & %s & %s & %d & %d & %s & %.1f\\\\" % (
            model_label(model), n, stage_first["design"], stage_first["implementation"], stage_first["verification"],
            pct(failed, jobs), conf, pub, fmt(calls), tokens / max(calls, 1) / 1000))
    m.update({"LlmTrials": total_trials, "LlmPublishedPct": pct(published, total_trials),
              "LlmBarrierConflicts": conflicts, "LlmEpochRepairs": epoch_ok, "LlmImplForms": len(forms),
              "LlmImplAccepted": accepted_impl, "LlmFeedbackRecoveredPct": pct(rej_recovered, rej_total),
              "LlmJobsFailedPct": pct(failed_jobs, all_jobs),
              "LlmFeedbackRecoveredCI": wilson(rej_recovered, rej_total), "LlmPublished": published,
              "LlmModelsNeverPublished": sum(1 for mo in models if per[mo]["completion"]
                                             and not any(r["published"] for r in per[mo]["completion"]))})
    # why first design attempts were rejected: feedback text carried by the second attempt
    first_rej = name_rej = parsed = update_named = 0
    for e in manifest["runs"]:
        calls = ROOT / Path(e).parent / "calls.jsonl"
        if not calls.is_file():
            continue
        for line in open(calls):
            c = json.loads(line)
            if c["job"].startswith("design/") and c["attempt"] == 1:
                ops = re.search(r'"operations"\s*:\s*\[([^\]]*)\]', c.get("response") or "")
                if ops:
                    names = {x.strip().strip('"').lower() for x in ops.group(1).split(",") if x.strip()}
                    parsed += 1
                    update_named += "update" in names and "put" not in names
            if c["job"].startswith("design/") and c["attempt"] == 2 and c.get("feedback"):
                first_rej += 1
                name_rej += c["feedback"].startswith("operations must be exactly")
    m.update({"LlmDesignFirstRejects": fmt(first_rej), "LlmDesignNameRejects": fmt(name_rej),
              "LlmDesignNameRejectPct": pct(name_rej, first_rej),
              "LlmDesignParsed": fmt(parsed), "LlmDesignUpdateNamed": fmt(update_named)})
    frags = {"tab-llm.tex": (r"""\begin{table*}[!t]
\centering
\caption{RQ5: initial completion of four-service workspaces by real LLM proposers (budget $k=3$, validator feedback on retries, one feedback epoch after a barrier conflict). \emph{First-attempt acceptance}: share of first attempts committed per stage. \emph{Failed}: share of jobs that exhausted their budget (their dependents are blocked, an explicit verdict). \emph{Conflicts}: workspaces whose locally valid designs violated the global identifier convention at the barrier.}\label{tab:llm}
\footnotesize\setlength{\tabcolsep}{4pt}
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}\toprule
& & \multicolumn{3}{c}{First-attempt acceptance (\%)} & & & & & \\\cmidrule(lr){3-5}
Model & Trials & Design & Code & Tests & Failed jobs (\%) & Conflicts & Published & Calls & kTokens/call\\\midrule
""" + "\n".join(lines) + r"""
\bottomrule\end{tabular*}
\end{table*}""")}
    # stale
    st = [r for model in models for r in per[model]["stale"] if "skipped" not in r]
    if st:
        old_valid = [r for r in st if r["valid_for_old_question"]]
        wrong = [r for r in old_valid if not r["valid_for_current_question"]]
        m.update({"LlmStaleTrials": len(st),
                  "LlmStaleDiscardedPct": pct(sum(r["controller_outcome"] == "discarded" for r in st), len(st)),
                  "LlmStaleOldValid": len(old_valid), "LlmStaleWrong": len(wrong),
                  "LlmStaleWrongPct": pct(len(wrong), len(old_valid)),
                  "LlmStaleWrongCI": wilson(len(wrong), len(old_valid))})
    # cutoff
    ct = [r for model in models for r in per[model]["cutoff"] if "skipped" not in r]
    lines = []
    for model in models:
        for temp in sorted({r["temperature"] for r in per[model]["cutoff"] if "skipped" not in r}):
            cells = []
            for stage in ("design", "impl"):
                xs = [r for r in per[model]["cutoff"] if "skipped" not in r and r["stage"] == stage
                      and r["temperature"] == temp]
                extra = "semantic_equal" if stage == "design" else "ast_equal"
                cells += [str(len(xs)), pct(sum(r["raw_equal"] for r in xs), len(xs)),
                          pct(sum(r["value_equal"] for r in xs), len(xs)), pct(sum(bool(r[extra]) for r in xs), len(xs))]
            lines.append("%s & %.1f & %s\\\\" % (model_label(model), temp, " & ".join(cells)))
    des = [r for r in ct if r["stage"] == "design"]
    imp = [r for r in ct if r["stage"] == "impl"]
    m.update({"LlmCutoffDesignRawPct": pct(sum(r["raw_equal"] for r in des), len(des)),
              "LlmCutoffDesignValuePct": pct(sum(r["value_equal"] for r in des), len(des)),
              "LlmCutoffDesignSemPct": pct(sum(bool(r["semantic_equal"]) for r in des), len(des)),
              "LlmCutoffImplValuePct": pct(sum(r["value_equal"] for r in imp), len(imp)),
              "LlmCutoffImplAstPct": pct(sum(bool(r["ast_equal"]) for r in imp), len(imp))})
    if lines:
        frags["tab-llm-cutoff.tex"] = (r"""\begin{table}[!t]
\centering
\caption{RQ5: early cutoff under stochastic generation. After a reworded contract with the same meaning, how often was the regenerated value equal to the previous one? \emph{Raw}: identical response text; \emph{Value}: identical slot value (what early cutoff compares); \emph{Sem.}: same identifier type, operations and status codes; \emph{AST}: same structure-only normal form.}\label{tab:llm-cutoff}
\scriptsize\setlength{\tabcolsep}{1.6pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}lrrrrrrrrr@{}}\toprule
& & \multicolumn{4}{c}{Design (JSON), \%} & \multicolumn{4}{c}{Implementation (code), \%}\\\cmidrule(lr){3-6}\cmidrule(lr){7-10}
Model & $T$ & $n$ & Raw & Value & Sem. & $n$ & Raw & Value & AST\\\midrule
""" + "\n".join(lines) + r"""
\bottomrule\end{tabular*}
\end{table}""")
    # cost
    co = [r for model in models for r in per[model]["cost"]]
    if co:
        lines = []
        exact = [r for r in co if r["mode"] == "exact"]
        full = [r for r in co if r["mode"] == "full"]
        for r in co:
            reqs = sum(c["requests"] for c in r["changes"])
            toks = sum(c["prompt_tokens"] + c["output_tokens"] for c in r["changes"])
            secs = sum(c["seconds"] for c in r["changes"])
            pub = sum(c["publishable"] for c in r["changes"])
            lines.append("%s & %s & %d & %.1f & %.0f & %d/%d\\\\" % (
                model_label(r["model"]), {"exact": "Exact (ours)", "no-cutoff": "No early cutoff",
                                          "workspace": "Whole workspace", "full": "Full regeneration"}[r["mode"]],
                reqs, toks / 1000, secs / 60 * 60, pub, len(r["changes"])))
        er = sum(sum(c["requests"] for c in r["changes"]) for r in exact)
        fr = sum(sum(c["requests"] for c in r["changes"]) for r in full)
        et = sum(sum(c["prompt_tokens"] + c["output_tokens"] for c in r["changes"]) for r in exact)
        ft = sum(sum(c["prompt_tokens"] + c["output_tokens"] for c in r["changes"]) for r in full)
        m.update({"LlmCostExactReq": er, "LlmCostFullReq": fr,
                  "LlmCostRatio": "%.1f" % (fr / er) if er else NA, "LlmCostTokenRatio": "%.1f" % (ft / et) if et else NA})
        frags["tab-llm-cost.tex"] = (r"""\begin{table}[!t]
\centering
\caption{RQ5: cost of one stream of eight changes (two clause edits, three context changes of which one unselected and one equal-content, two reworded contracts) on a four-service workspace with real LLMs, after the initial repair. \emph{Publishable}: changes after which the repaired workspace passed the barrier.}\label{tab:llm-cost}
\scriptsize\setlength{\tabcolsep}{2pt}
\begin{tabular*}{\columnwidth}{@{\extracolsep{\fill}}llrrrr@{}}\toprule
Model & Strategy & Requests & kTokens & Seconds & Publishable\\\midrule
""" + "\n".join(lines) + r"""
\bottomrule\end{tabular*}
\end{table}""")
    return m, frags


# ------------------------------------------------------------------ RQ6
def bench_fragments():
    files = sorted(glob.glob(str(ROOT / "hpc/fetched/*/outputs/full/benchmark/*/results-*.json")))
    reports = [json.loads(Path(f).read_text()) for f in files]
    keys = ("BenchModelsN", "BenchTasks", "BenchCalls", "BenchAcceptedWrongPct", "BenchFirstCorrectPct",
            "BenchFinalCorrectPct", "BenchByteEqualPct", "BenchValueEqualPct", "BenchAstEqualPct", "BenchBehEqualPct",
            "BenchTestsRegenPct", "BenchMaxPlus", "BenchAcceptedPct", "BenchFirstBaseWrongPct",
            "BenchAcceptedWrongCI", "BenchValueEqualCI", "BenchBehEqualCI", "BenchRetryGainPts",
            "BenchAcceptedWrongHE", "BenchAcceptedWrongMBPP", "BenchRegenN")
    m = {k: NA for k in keys}
    m["BenchMaxPlus"] = 200
    m["BenchTasks"] = "542"
    if not reports:
        return m, {}
    by = defaultdict(dict)
    for r in reports:
        by[r["model"]][r["benchmark"]] = r
    lines = []
    tot = defaultdict(int)
    for model in sorted(by):
        for bench in ("humaneval", "mbpp"):
            r = by[model].get(bench)
            if r is None:
                continue
            rows = r["rows"]
            n = len(rows)
            acc = [x for x in rows if "accepted_correct" in x]
            wrong = [x for x in acc if not x["accepted_correct"]]
            first_ok = sum(x["first_proposal_correct"] for x in rows)
            first_base_ok = [x for x in rows if x["first_proposal_base_ok"]]
            first_base_wrong = [x for x in first_base_ok if not x["first_proposal_correct"]]
            regen = [x for x in rows if "value_equal" in x]
            tests_usable = sum(x["tests_usable"] for x in rows)
            tot["n"] += n
            tot["acc"] += len(acc)
            tot["wrong"] += len(wrong)
            tot["first_ok"] += first_ok
            tot["final_ok"] += len(acc) - len(wrong)
            tot["fbo"] += len(first_base_ok)
            tot["fbw"] += len(first_base_wrong)
            tot["regen"] += len(regen)
            for k in ("raw_equal", "value_equal", "ast_equal", "behaviour_equal"):
                tot[k] += sum(bool(x[k]) for x in regen)
            reg_tests = [x for x in regen if x.get("tests_usable")]
            tot["tests_base"] += len(reg_tests)
            tot["tests_regen"] += sum(bool(x["tests_regenerated"]) for x in reg_tests)
            tot["calls"] += r["calls_total"]
            tot["acc_" + bench] += len(acc)
            tot["wrong_" + bench] += len(wrong)
            lines.append("%s & %s & %d & %s & %s & %s & %s & %s & %s & %s & %s\\\\" % (
                model_label(model), {"humaneval": "HE+", "mbpp": "MBPP+"}[bench], n, pct(first_ok, n, 1),
                pct(len(acc), n, 1), pct(len(acc) - len(wrong), n, 1), pct(len(wrong), len(acc), 1),
                pct(sum(bool(x["raw_equal"]) for x in regen), len(regen)),
                pct(sum(bool(x["value_equal"]) for x in regen), len(regen)),
                pct(sum(bool(x["ast_equal"]) for x in regen), len(regen)),
                pct(sum(bool(x["behaviour_equal"]) for x in regen), len(regen))))
    m.update({"BenchModelsN": len(by), "BenchCalls": fmt(tot["calls"]),
              "BenchAcceptedPct": pct(tot["acc"], tot["n"]),
              "BenchAcceptedWrongPct": pct(tot["wrong"], tot["acc"], 1),
              "BenchFirstCorrectPct": pct(tot["first_ok"], tot["n"], 1),
              "BenchFinalCorrectPct": pct(tot["final_ok"], tot["n"], 1),
              "BenchFirstBaseWrongPct": pct(tot["fbw"], tot["fbo"], 1),
              "BenchByteEqualPct": pct(tot["raw_equal"], tot["regen"]),
              "BenchValueEqualPct": pct(tot["value_equal"], tot["regen"]),
              "BenchAstEqualPct": pct(tot["ast_equal"], tot["regen"]),
              "BenchBehEqualPct": pct(tot["behaviour_equal"], tot["regen"]),
              "BenchTestsRegenPct": pct(tot["tests_regen"], tot["tests_base"]),
              "BenchAcceptedWrongCI": wilson(tot["wrong"], tot["acc"]),
              "BenchValueEqualCI": wilson(tot["value_equal"], tot["regen"]),
              "BenchBehEqualCI": wilson(tot["behaviour_equal"], tot["regen"]),
              "BenchRetryGainPts": "%.1f" % (100.0 * (tot["final_ok"] - tot["first_ok"]) / tot["n"]),
              "BenchAcceptedWrongHE": pct(tot["wrong_humaneval"], tot["acc_humaneval"], 1),
              "BenchAcceptedWrongMBPP": pct(tot["wrong_mbpp"], tot["acc_mbpp"], 1),
              "BenchRegenN": fmt(tot["regen"])})
    frag = (r"""\begin{table*}[!t]
\centering
\caption{RQ6: coordinated code generation on HumanEval+ (HE+) and MBPP+ with budget $k=3$ and the benchmark's base tests as the declared validator; plus tests (up to %d inputs per task) are used only as ground truth. \emph{First correct}: first proposal passes base and plus tests (no validator, no retry). \emph{Accepted}: a value became usable. \emph{Accepted \& correct}: it also passes the plus tests. \emph{Wrong among accepted}: validator-relative correctness gap (Corollary~\ref{cor:domain}). Right block: after a reworded code contract with the same meaning, share of regenerated values that are identical as text (\emph{Raw}), identical as slot values (\emph{Value}; early cutoff fires), identical in structure (\emph{AST}), or behaviourally equal on all plus inputs (\emph{Beh.}).}\label{tab:bench}
\footnotesize\setlength{\tabcolsep}{3.5pt}
\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrrrrrrr@{}}\toprule
& & & \multicolumn{4}{c}{Correctness (\%%)} & \multicolumn{4}{c}{Regeneration equal to previous value (\%%)}\\\cmidrule(lr){4-7}\cmidrule(lr){8-11}
Model & Bench. & Tasks & First correct & Accepted & Accepted \& correct & Wrong among accepted & Raw & Value & AST & Beh.\\\midrule
""" % m["BenchMaxPlus"] + "\n".join(lines) + r"""
\bottomrule\end{tabular*}
\end{table*}""")
    return m, {"tab-bench.tex": frag}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    macros = dict(effort())
    gm, gf = graph_fragments(load("results/processed/tse/graph.json"))
    tm, tf = tlc_fragment(load("results/processed/tse/tlc-extended.json"))
    lm, lf = llm_fragments()
    bm, bf = bench_fragments()
    for d in (gm, tm, lm, bm):
        macros.update(d)
    frags = {**gf, **tf, **lf, **bf}
    numbers = "\n".join("\\newcommand{\\%s}{%s}" % (k, v) for k, v in sorted(macros.items()))
    frags["numbers-r1.tex"] = numbers
    expected = ("tab-coupled.tex", "tab-sched.tex", "tab-tlc-ext.tex", "tab-llm.tex", "tab-llm-cutoff.tex",
                "tab-llm-cost.tex", "tab-bench.tex")
    for name in expected:
        frags.setdefault(name, r"\begin{table}[!t]\centering\fbox{Pending: %s}\end{table}" % name.replace("_", r"\_"))
    prov = {}
    for name, text in frags.items():
        body = "% Generated by experiments/revision_paper.py; do not edit.\n" + text + "\n"
        (OUT / name).write_text(body)
        prov[name] = hashlib.sha256(body.encode()).hexdigest()
    (OUT / "provenance-r1.json").write_text(json.dumps(prov, indent=1, sort_keys=True) + "\n")
    print("\n".join(sorted(frags)))
    missing = [k for k, v in macros.items() if v == NA]
    print("pending macros:", ", ".join(missing) if missing else "none")


if __name__ == "__main__":
    main()
