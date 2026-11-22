"""Experiments on the generic coordination kernel (src/vgc/graph.py).

    python experiments/graph_experiments.py [--quick]

1. differential : the generic kernel and the reference controller must dispatch the
                  same number of requests and accept the same values on the RQ2
                  document-service change streams, for all five strategies.
2. coupled      : invalidation cost on a *coupled* modular workspace in which every
                  module's design depends on f of S shared data-model components.
3. scheduling   : number of dependency episodes and requests per job after one edit
                  on layered dependency lattices, for the gated scheduler of the paper
                  and an eager scheduler without the upstream usability gate, under
                  random asynchronous latencies (Theorem 'single-episode repair').

No language model is called; providers are deterministic functions of the
observation, so every number is a function of the recorded seeds.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import argparse
import hashlib
import heapq
import json
import platform
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "experiments")]

from vgc.graph import GraphController, Job, MODES, canonical, repair  # noqa: E402
from vgc.validators import validate, table  # noqa: E402
import tse_campaign as rq  # noqa: E402

# --------------------------------------------------------------- 1. differential

DOC_STAGES = ("requirements", "architecture", "implementation", "verification")
PREREQ = {"requirements": (), "architecture": ("requirements",), "implementation": ("architecture",),
          "verification": ("implementation",)}


def doc_jobs(documents, contracts):
    jobs = []
    for rank, stage in enumerate(DOC_STAGES):
        for d in sorted(documents):
            reads = (lambda X, d=d: X[d]) if stage in rq.SOURCE_STAGES else None
            selects = ((lambda C, d=d: {k: v for k, v in sorted(C.items()) if v["document"] == d})
                       if stage in rq.CONTEXT_STAGES else None)
            jobs.append(Job("%s/%s" % (stage, d), rank, tuple("%s/%s" % (p, d) for p in PREREQ[stage]),
                            stage + "-worker", contracts[stage], reads, selects,
                            lambda o, v, s=stage: validate(s, o, v)))
    return jobs


def doc_provider(q):
    stage = q.job.split("/")[0]
    strict = (q.observation["source"] or {}).get("strict")
    if stage == "requirements":
        return {"clauses": ["R01", "R02", "R03"], "strict": strict}
    if stage == "architecture":
        return {"id_type": "string", "operations": ["create", "read", "update", "archive", "list"]}
    if stage == "implementation":
        return table(strict)
    return {"id_type": "string", "covered": ["R01", "R02", "R03"]}


def differential(sizes, seeds, changes, seed0=7000):
    rows = []
    for n in sizes:
        for i in range(seeds):
            seed = seed0 + 101 * n + i
            rng = random.Random(seed)
            documents = {"d%02d" % k: {"strict": rng.random() < 0.5} for k in range(n)}
            context = {"f-" + d: {"document": d, "finding": "initial"} for d in documents if rng.random() < 0.5}
            stream = rq.change_stream(rng, documents, changes)
            for mode in MODES:
                ref = rq.Strategy(documents, 2, mode)
                ref.update_context(0, context)
                assert rq.repair(ref)
                contracts = {s: "v1" for s in DOC_STAGES}
                g = GraphController(doc_jobs(documents, contracts), documents, {}, 2, mode)
                g.edit(context=context)
                assert repair(g, doc_provider)
                mismatches = 0
                for change in stream:
                    r0, g0 = ref.sent_requests, g.sent_requests
                    rq.apply_change(ref, change)
                    assert rq.repair(ref)
                    kind, document, stage, salt = change
                    if kind == "source":
                        docs = deepcopy(g.inputs)
                        docs[document]["strict"] = not docs[document]["strict"]
                        g.edit(inputs=docs)
                    elif kind.startswith("context"):
                        ctx = deepcopy(g.context)
                        if kind == "context-selected":
                            ctx["f-" + document] = {"document": document, "finding": "finding-%d" % salt}
                        elif kind == "context-unselected":
                            ctx["f-outside"] = {"document": "outside", "finding": "finding-%d" % salt}
                        g.edit(context=ctx)
                    else:
                        contracts[stage] = "c%d" % salt
                        g.edit(jobs=doc_jobs(g.inputs, contracts))
                    assert repair(g, doc_provider)
                    ref_values = {"%s/%s" % tuple(ref.split(k)): canonical(r.value)
                                  for k, r in ref.records.items() if k in ref.active}
                    g_values = {k: canonical(v) for k, v in g.values().items()}
                    if (ref.sent_requests - r0 != g.sent_requests - g0) or ref_values != g_values:
                        mismatches += 1
                rows.append({"n": n, "seed": seed, "mode": mode, "changes": len(stream),
                             "mismatching_changes": mismatches,
                             "requests_reference": ref.sent_requests, "requests_generic": g.sent_requests})
    return {"runs": rows, "all_equal": all(r["mismatching_changes"] == 0 and
                                           r["requests_reference"] == r["requests_generic"] for r in rows)}


# --------------------------------------------------------------- 2. coupled

def coupled_jobs(modules, shared, deps, contracts):
    jobs = []
    for c in shared:
        jobs.append(Job("spec/" + c, 0, (), "model-worker", contracts["spec"], lambda X, c=c: X["shared"][c],
                        None, lambda o, v: isinstance(v, dict) and v.get("fields") == sorted(o["source"]["fields"])))
        jobs.append(Job("schema/" + c, 1, ("spec/" + c,), "model-worker", contracts["schema"], None, None,
                        lambda o, v, c=c: v == {"fields": o["prerequisites"]["spec/" + c]["fields"]}))
    for m in modules:
        jobs.append(Job("req/" + m, 0, (), "requirements-worker", contracts["req"], lambda X, m=m: X["modules"][m],
                        None, lambda o, v: v == {"strict": o["source"]["strict"]}))
        jobs.append(Job("arch/" + m, 2, ("req/" + m,) + tuple("schema/" + c for c in deps[m]),
                        "architecture-worker", contracts["arch"], None, None, lambda o, v: isinstance(v, dict)))
        sel = lambda C, m=m: {k: x for k, x in sorted(C.items()) if x["module"] == m}
        jobs.append(Job("impl/" + m, 3, ("arch/" + m,), "implementation-worker", contracts["impl"],
                        lambda X, m=m: X["modules"][m], sel, lambda o, v: isinstance(v, dict)))
        jobs.append(Job("ver/" + m, 4, ("impl/" + m,), "verification-worker", contracts["ver"],
                        lambda X, m=m: X["modules"][m], sel, lambda o, v: isinstance(v, dict)))
    return jobs


def coupled_provider(q):
    kind = q.job.split("/")[0]
    o = q.observation
    if kind == "spec":
        return {"fields": sorted(o["source"]["fields"]), "description": o["source"]["description"]}
    if kind == "schema":
        return {"fields": o["prerequisites"]["spec/" + q.job.split("/")[1]]["fields"]}
    if kind == "req":
        return {"strict": o["source"]["strict"]}
    if kind == "arch":
        preds = o["prerequisites"]
        uses = sorted(f for k, v in preds.items() if k.startswith("schema/") for f in (v or {}).get("fields", []))
        return {"strict": (preds.get("req/" + q.job.split("/")[1]) or {}).get("strict"), "uses": uses}
    # impl and ver depend on the design value (a request id in no-cutoff mode) and the findings.
    design = next(iter(o["prerequisites"].values()))
    return {"design": design, "strict": o["source"]["strict"], "findings": sorted((o["context"] or {}))}


COUPLED_CHANGES = (("module", 35), ("shared-semantic", 15), ("shared-cosmetic", 10),
                   ("context-selected", 15), ("context-unselected", 5), ("contract", 20))


def coupled_run(m_count, s_count, fanout, seed, changes):
    rng = random.Random(seed)
    modules = ["m%02d" % i for i in range(m_count)]
    shared = ["s%d" % i for i in range(s_count)]
    deps = {m: sorted(rng.sample(shared, fanout)) for m in modules}
    inputs = {"modules": {m: {"strict": rng.random() < 0.5} for m in modules},
              "shared": {c: {"fields": ["id"], "description": "v0"} for c in shared}}
    names, weights = zip(*COUPLED_CHANGES)
    stream = [(rng.choices(names, weights)[0], rng.choice(modules), rng.choice(shared),
               rng.choice(("req", "arch", "impl", "ver")), rng.randint(0, 10 ** 6)) for _ in range(changes)]
    out = {}
    for mode in ("exact", "no-cutoff", "workspace", "full"):
        contracts = {k: "v1" for k in ("spec", "schema", "req", "arch", "impl", "ver")}
        g = GraphController(coupled_jobs(modules, shared, deps, contracts), inputs, {}, 2, mode)
        assert repair(g, coupled_provider)
        per = {k: [0, 0, 0] for k in names}  # changes, requests, work episodes (exact affected set)
        for kind, m, c, stage, salt in stream:
            r0, e0 = g.sent_requests, sum(g.work_episodes.values())
            X = deepcopy(g.inputs)
            if kind == "module":
                X["modules"][m]["strict"] = not X["modules"][m]["strict"]
                g.edit(inputs=X)
            elif kind == "shared-semantic":
                X["shared"][c]["fields"] = X["shared"][c]["fields"] + ["f%d" % salt]
                g.edit(inputs=X)
            elif kind == "shared-cosmetic":
                X["shared"][c]["description"] = "d%d" % salt
                g.edit(inputs=X)
            elif kind.startswith("context"):
                ctx = deepcopy(g.context)
                target = m if kind == "context-selected" else "outside"
                ctx["f-" + target] = {"module": target, "finding": "x%d" % salt}
                g.edit(context=ctx)
            else:
                contracts[stage] = "c%d" % salt
                g.edit(jobs=coupled_jobs(modules, shared, deps, contracts))
            assert repair(g, coupled_provider), (mode, kind)
            per[kind][0] += 1
            per[kind][1] += g.sent_requests - r0
            per[kind][2] += sum(g.work_episodes.values()) - e0
        out[mode] = per
    return {"modules": m_count, "shared": s_count, "fanout": fanout, "seed": seed, "per_kind": out,
            "jobs": 2 * s_count + 4 * m_count}


def coupled(m_count, s_count, fanouts, seeds, changes, seed0=9100):
    runs = [coupled_run(m_count, s_count, f, seed0 + 31 * f + i, changes) for f in fanouts for i in range(seeds)]
    summary = {}
    for f in fanouts:
        rows = [r for r in runs if r["fanout"] == f]
        summary[str(f)] = {}
        for mode in ("exact", "no-cutoff", "workspace", "full"):
            totals = {k: [sum(r["per_kind"][mode][k][i] for r in rows) for i in range(3)] for k, _ in COUPLED_CHANGES}
            count = sum(t[0] for t in totals.values())
            summary[str(f)][mode] = {
                "requests_per_change": sum(t[1] for t in totals.values()) / count,
                "by_kind": {k: (t[1] / t[0] if t[0] else None) for k, t in totals.items()},
                # In exact mode every request is caused by a stale stamp: requests == work episodes.
                "requests_equal_affected": all(t[1] == t[2] for t in totals.values()) if mode == "exact" else None,
            }
    return {"runs": runs, "summary": summary}


# --------------------------------------------------------------- 3. scheduling

def lattice_jobs(depth, width):
    jobs = []
    for layer in range(depth):
        for w in range(width):
            prereqs = tuple("n%d.%d" % (layer - 1, x) for x in range(width)) if layer else ()
            jobs.append(Job("n%d.%d" % (layer, w), layer, prereqs, "worker", "v1",
                            (lambda X: X["root"]) if layer == 0 else None, None, lambda o, v: True))
    return jobs


def lattice_provider(q):
    o = q.observation
    return hashlib.sha256(canonical([o["source"], o["prerequisites"], q.job]).encode()).hexdigest()[:12]


def simulate(g, rng, latency=(1.0, 3.0)):
    """Event-driven asynchronous execution with unlimited parallel workers."""
    now, heap, seq, stale_commits = 0.0, [], 0, 0
    while True:
        for jid in g.eligible():
            q = g.dispatch(jid)
            if q is not None:
                seq += 1
                heapq.heappush(heap, (now + rng.uniform(*latency), seq, q))
        if not heap:
            return now, stale_commits
        now, _, q = heapq.heappop(heap)
        before = any(not g.usable(p) for p in g.jobs[q.job].prereqs)
        outcome, _ = g.resolve(q.identity, lattice_provider(q))
        if outcome == "committed" and before:
            stale_commits += 1  # committed while a prerequisite was being repaired


def scheduling(depths, widths, seeds, seed0=4400):
    rows = []
    for depth in depths:
        for width in widths:
            for gate in (True, False):
                for i in range(seeds):
                    rng = random.Random(seed0 + 1000 * depth + 10 * width + i)
                    g = GraphController(lattice_jobs(depth, width), {"root": 0}, {}, 2, "exact", gate=gate)
                    simulate(g, rng)
                    e0 = dict(g.work_episodes)
                    r0 = g.sent_requests
                    g.edit(inputs={"root": 1})
                    makespan, stale = simulate(g, rng)
                    episodes = [g.work_episodes[j] - e0[j] for j in g.jobs]
                    rows.append({"depth": depth, "width": width, "gated": gate, "seed": i,
                                 "requests": g.sent_requests - r0, "jobs": depth * width,
                                 "max_episodes": max(episodes), "mean_episodes": sum(episodes) / len(episodes),
                                 "discarded": g.discarded, "makespan": makespan, "stale_commits": stale})
    summary = {}
    for depth in depths:
        for width in widths:
            for gate in (True, False):
                sel = [r for r in rows if r["depth"] == depth and r["width"] == width and r["gated"] == gate]
                summary["%d/%d/%s" % (depth, width, "gated" if gate else "eager")] = {
                    k: sum(r[k] for r in sel) / len(sel) for k in
                    ("requests", "max_episodes", "mean_episodes", "makespan", "stale_commits", "discarded")}
                summary["%d/%d/%s" % (depth, width, "gated" if gate else "eager")]["worst_max_episodes"] = max(
                    r["max_episodes"] for r in sel)
    return {"runs": rows, "summary": summary,
            "gated_single_episode": all(r["max_episodes"] <= 1 for r in rows if r["gated"]),
            "gated_requests_equal_jobs": all(r["requests"] == r["jobs"] for r in rows if r["gated"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    if args.quick:
        cfg = {"diff_sizes": [1, 4], "diff_seeds": 1, "diff_changes": 10, "modules": 8, "shared": 4,
               "fanouts": [0, 1, 2], "coupled_seeds": 1, "coupled_changes": 20,
               "depths": [2, 4], "widths": [1, 2], "sched_seeds": 3}
    else:
        cfg = {"diff_sizes": [1, 2, 4, 8, 16, 32], "diff_seeds": 5, "diff_changes": 40, "modules": 32, "shared": 8,
               "fanouts": [0, 1, 2, 4, 8], "coupled_seeds": 5, "coupled_changes": 60,
               "depths": [2, 3, 4, 5, 6], "widths": [1, 2, 3, 4], "sched_seeds": 30}
    report = {"config": cfg, "python": platform.python_version(), "platform": platform.platform()}
    report["differential"] = differential(cfg["diff_sizes"], cfg["diff_seeds"], cfg["diff_changes"])
    print("differential all_equal", report["differential"]["all_equal"], flush=True)
    report["coupled"] = coupled(cfg["modules"], cfg["shared"], cfg["fanouts"], cfg["coupled_seeds"],
                                cfg["coupled_changes"])
    print("coupled", json.dumps({f: {m: round(v["requests_per_change"], 1) for m, v in s.items()}
                                 for f, s in report["coupled"]["summary"].items()}), flush=True)
    report["scheduling"] = scheduling(cfg["depths"], cfg["widths"], cfg["sched_seeds"])
    print("scheduling gated single episode", report["scheduling"]["gated_single_episode"],
          report["scheduling"]["gated_requests_equal_jobs"], flush=True)
    report["elapsed_seconds"] = time.monotonic() - started
    report["source_sha256"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                               for p in ("src/vgc/graph.py", "experiments/graph_experiments.py",
                                         "experiments/tse_campaign.py")}
    out = ROOT / "results/processed/tse" / ("graph-quick.json" if args.quick else "graph.json")
    out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(out.relative_to(ROOT), "%.0fs" % report["elapsed_seconds"])
    return int(not (report["differential"]["all_equal"] and report["scheduling"]["gated_single_episode"]))


if __name__ == "__main__":
    raise SystemExit(main())
