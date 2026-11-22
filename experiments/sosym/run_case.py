"""Campaigns of the SoSyM model-driven case study.

    python experiments/sosym/run_case.py sim    [--runs 500]           # stochastic agents (RQ1, RQ3)
    python experiments/sosym/run_case.py impact [--runs 200]           # change impact (RQ2)
    python experiments/sosym/run_case.py sweep  [--runs 100]           # sensitivity to p_mid, p_err, k
    python experiments/sosym/run_case.py llm    --model qwen2.5:7b [--reps 10] [--host URL] [--cache-only]
    python experiments/sosym/summarize.py                              # aggregate -> results/processed/sosym

--cache-only replays an LLM campaign from its recorded replies without contacting a model;
a cache miss is answered with an empty (invalid) reply and counted in the output, so a
replay with zero misses reproduces the campaign exactly with the current code.

Asynchrony is simulated by a seeded discrete-event driver: every dispatched request
gets an exponentially distributed latency, is duplicated with probability p_dup and
lost (timeout) with probability p_drop, and each of the seven model changes arrives
either while requests are in flight (probability p_mid) or at quiescence. The same
schedule seed is used for every strategy. LLM answers are cached by (model, prompt,
attempt, repetition), so strategies that ask the same question receive the same
answer (common random numbers); only distinct prompts reach the model.

At every step a monitor checks the safety properties of the article on the kernel
state: current validity of usable views (S3), authorised provenance (S2/S4), the
per-episode budget (S6) and request currency (Lemma 1); at every quiescent point the
released snapshot, if any, is judged by an oracle against the *current* model.
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import datetime
import hashlib
import heapq
import json
import os
import platform
import random
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mde_case as mde  # noqa: E402
from kernel import STRATEGIES, CAMPAIGN  # noqa: E402

RAW = ROOT / "results/raw/sosym"
OUT = ROOT / "results/processed/sosym"


# --------------------------------------------------------------------- monitor
def monitor(k, state, counts):
    for jid in k.active:
        if not k.usable(jid):
            continue
        v = k.records[jid].value
        o = k.full_observation(jid)
        if o is None:
            # usable although a prerequisite is not: its value was computed over stale inputs
            counts["S3 upstream currency"] += 1
        elif not k.jobs[jid].validator(o, v)[0]:
            counts["S3 current validity"] += 1
        ev = k.records[jid].evidence
        if ev.owner != k.jobs[jid].owner or ev.owner in state["revoked"]:
            counts["S2/S4 authorised provenance"] += 1
    per = Counter((q.job, q.episode) for q in k.history.values())
    if any(n > k.budget for n in per.values()):
        counts["S6 episode budget"] += 1
    if k.guards and any(not k._current(q) for q in k.pending.values()):
        counts["L1 request currency"] += 1


# --------------------------------------------------------------------- driver
def run(strategy, agent, seed, budget=3, p_mid=0.6, mean_lat=1.0, p_dup=0.1, p_drop=0.05, check=True):
    rng = random.Random(seed)
    state = mde.initial_state()
    k = mde.make_kernel(state, strategy, budget)
    heap, seq, t = [], [0], [0.0]
    nxt = [0]
    violations = Counter()
    revisions = [{"rev": 0, "edit": "initial", "mid": False}]
    unusable_at_start = {0: set(k.jobs)}       # W includes views not usable when the revision starts
    quiescent_points = []

    def push(when, kind, payload):
        seq[0] += 1
        heapq.heappush(heap, (when, seq[0], kind, payload))

    def schedule_edit():
        if nxt[0] < len(mde.EDITS) and rng.random() < p_mid:
            push(t[0] + rng.uniform(0.2, 2.5) * mean_lat, "edit", None)
            return True
        return False

    def do_edit(mid):
        name, desc, fn = mde.EDITS[nxt[0]]
        fn(state)
        mde.apply(k, state)
        nxt[0] += 1
        revisions.append({"rev": k.revision, "edit": name, "mid": mid})
        unusable_at_start[k.revision] = {j for j in k.jobs if not k.usable(j)}
        return schedule_edit()

    edit_in_heap = schedule_edit()
    steps = 0
    while True:
        for jid in k.eligible():
            q = k.dispatch(jid)
            value = agent(q)
            lat = rng.expovariate(1.0 / mean_lat)
            if rng.random() < p_drop:
                push(t[0] + 5 * mean_lat, "timeout", q.identity)
            else:
                push(t[0] + lat, "reply", (q.identity, value))
                if rng.random() < p_dup:
                    push(t[0] + lat + rng.expovariate(1.0 / mean_lat), "reply", (q.identity, value))
        if check:
            monitor(k, state, violations)
        steps += 1
        if not heap:
            released = k.publishable()
            issues = mde.oracle(k, state) if released else None
            values = k.values()
            all_usable = not k.suspended and all(k.usable(j) for j in k.active)
            quiescent_points.append({"rev": k.revision, "released": released, "issues": issues,
                                     "all_usable": all_usable, "G": mde.global_predicate(values),
                                     "failed": sorted(j for j in k.active if k.records[j].failed),
                                     "suspended": sorted(k.suspended)})
            if all_usable and not mde.global_predicate(values) and state["epochs"] == 0:
                mde.feedback_epoch(state)
                mde.apply(k, state)
                revisions.append({"rev": k.revision, "edit": "FB", "mid": False})
                unusable_at_start[k.revision] = {j for j in k.jobs if not k.usable(j)}
                continue
            if nxt[0] < len(mde.EDITS):
                edit_in_heap = do_edit(False)
                continue
            break
        when, _, kind, payload = heapq.heappop(heap)
        t[0] = when
        if kind == "edit":
            edit_in_heap = do_edit(True)
        elif kind == "timeout":
            k.resolve(payload, timeout=True)
        else:
            k.resolve(payload[0], payload[1])
    # Theorem checks over stable intervals (each revision is an interval without edits).
    work = Counter(k.work_log)
    per_rev_jobs, per_rev_dispatch = defaultdict(set), Counter(r for r, _ in k.dispatch_log)
    for (rev, jid) in k.work_log:
        per_rev_jobs[rev].add(jid)
    bound_ok = all(per_rev_dispatch[r] <= budget * len(per_rev_jobs[r] | unusable_at_start.get(r, set()))
                   for r in per_rev_dispatch)
    for r in revisions:
        r["work_views"] = len(per_rev_jobs[r["rev"]])
        r["work_episodes"] = sum(n for (rev, _), n in work.items() if rev == r["rev"])
        r["dispatches"] = per_rev_dispatch[r["rev"]]
    final = quiescent_points[-1]
    releases = [p for p in quiescent_points if p["released"]]
    return {"strategy": strategy, "seed": seed, "metrics": dict(k.metrics), "violations": dict(violations),
            "max_episodes_per_view_and_revision": max(work.values()) if work else 0,
            "dispatch_bound_ok": bound_ok, "revisions": revisions, "quiescent": quiescent_points,
            "releases": len(releases), "wrong_releases": sum(bool(p["issues"]) for p in releases),
            "final_released": final["released"], "final_wrong": bool(final["released"] and final["issues"]),
            "issue_kinds": dict(Counter(i[1].split(":")[0] for p in releases for i in (p["issues"] or []))),
            "issue_views": dict(Counter(i[0] for p in releases for i in (p["issues"] or []))),
            "epochs": state["epochs"], "steps": steps}


# --------------------------------------------------------------------- LLM agent
class LLMAgent:
    def __init__(self, model, host, rep, cache_path, temperature=0.7, cache_only=False):
        self.model, self.host, self.rep, self.temperature = model, host, rep, temperature
        self.cache_only, self.misses = cache_only, 0
        self.cache_path = cache_path
        self.cache = {}
        if cache_path.exists():
            for line in cache_path.read_text().splitlines():
                r = json.loads(line)
                self.cache[r["key"]] = r
        self.calls = self.hits = 0
        self.reset()

    def reset(self):
        """Per-run cost: every dispatched request is charged, whether or not it hit the cache."""
        self.run_tokens = self.run_seconds = 0

    def _charge(self, rec):
        self.run_tokens += (rec.get("prompt_tokens") or 0) + (rec.get("output_tokens") or 0)
        self.run_seconds += rec.get("seconds") or 0

    def __call__(self, q):
        prompt = mde.render(q)
        key = hashlib.sha256(json.dumps([self.model, prompt, q.attempt, self.rep]).encode()).hexdigest()
        if key in self.cache:
            self.hits += 1
            self._charge(self.cache[key])
            return mde.parse(self.cache[key]["response"])
        if self.cache_only:
            self.misses += 1
            return mde.parse("")
        seed = int(key[:8], 16)
        body = {"model": self.model, "stream": False, "format": "json",
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": self.temperature, "seed": seed, "num_predict": 1500, "num_ctx": 8192}}
        started, response, error = time.monotonic(), None, None
        for _ in range(3):
            try:
                req = urllib.request.Request(self.host + "/api/chat", json.dumps(body).encode(),
                                             {"Content-Type": "application/json"})
                response = json.load(urllib.request.urlopen(req, timeout=900))
                break
            except Exception as e:  # noqa: BLE001 transport failure: retry
                error = repr(e)
                time.sleep(3)
        text = (response or {}).get("message", {}).get("content", "")
        rec = {"key": key, "model": self.model, "rep": self.rep, "job": q.job, "attempt": q.attempt,
               "feedback": q.feedback, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "prompt": prompt, "response": text, "prompt_tokens": (response or {}).get("prompt_eval_count"),
               "output_tokens": (response or {}).get("eval_count"), "seconds": round(time.monotonic() - started, 2),
               "transport_error": error, "utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        self.cache[key] = rec
        self._charge(rec)
        with self.cache_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        self.calls += 1
        return mde.parse(text)


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def compact_quiescent(r):
    """Per quiescent point: the change it follows, whether a snapshot was released and whether it was wrong."""
    edit_of = {rev["rev"]: rev["edit"] for rev in r["revisions"] if rev["edit"] != "FB"}   # feedback epochs
    out = []                                                                        # belong to their change
    for p in r.pop("quiescent"):
        last = max(rv for rv in edit_of if rv <= p["rev"])
        out.append([edit_of[last], bool(p["released"]), bool(p["released"] and p["issues"])])
    r["points"] = out
    return r


def manifest(extra):
    return dict(extra, git_commit=git_commit(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), python=platform.python_version(),
                host=platform.node(), sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                               for p in sorted(Path(__file__).resolve().parent.glob("*.py"))})


def cmd_sim(a):
    out = Path(a.out) / "sim"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(a.runs):
        for s in CAMPAIGN:
            agent = mde.SimulatedAgent(random.Random(10_000 + i), p_err=a.p_err)
            r = run(s, agent, seed=i, budget=a.budget, p_mid=a.p_mid, check=not a.nocheck)
            rows.append(compact_quiescent(r))
        if i % 50 == 0:
            print("sim run", i, flush=True)
    (out / "runs.json").write_text(json.dumps({"manifest": manifest(vars(a)), "runs": rows}) + "\n")
    print(out / "runs.json")


def cmd_impact(a):
    """Change-impact analysis: every change is applied at quiescence to a fully repaired model,
    agents are correct and the transport is reliable, so each revision runs to completion."""
    out = Path(a.out) / "impact"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(a.runs):
        for s in STRATEGIES:
            agent = mde.SimulatedAgent(random.Random(20_000 + i), p_err=0.0)
            r = run(s, agent, seed=50_000 + i, budget=a.budget, p_mid=0.0, p_dup=0.0, p_drop=0.0)
            rows.append({"strategy": s, "seed": i, "revisions": r["revisions"],
                         "requests": r["metrics"]["dispatched"], "wrong_releases": r["wrong_releases"]})
    (out / "runs.json").write_text(json.dumps({"manifest": manifest(vars(a)), "runs": rows}) + "\n")
    print(out / "runs.json")


def cmd_sweep(a):
    """Sensitivity of the RQ1/RQ2 contrast to the timing of changes, the agent error rate and the budget."""
    out = Path(a.out) / "sweep"
    out.mkdir(parents=True, exist_ok=True)
    grid = [("p_mid", v, dict(p_mid=v)) for v in (0.0, 0.3, 0.6, 0.9)] + \
           [("p_err", v, dict(p_err=v)) for v in (0.1, 0.25, 0.5)] + \
           [("budget", v, dict(budget=v)) for v in (2, 4, 8)]
    rows = []
    for factor, value, over in grid:
        cfg = dict(p_mid=a.p_mid, p_err=a.p_err, budget=a.budget)
        cfg.update(over)
        for i in range(a.runs):
            for s in ("exact", "datakey", "lww", "full"):
                agent = mde.SimulatedAgent(random.Random(30_000 + i), p_err=cfg["p_err"])
                r = run(s, agent, seed=40_000 + i, budget=cfg["budget"], p_mid=cfg["p_mid"], check=False)
                rows.append({"factor": factor, "value": value, "strategy": s, "seed": i,
                             "requests": r["metrics"]["dispatched"], "releases": r["releases"],
                             "wrong_releases": r["wrong_releases"], "final_released": r["final_released"],
                             "final_wrong": r["final_wrong"]})
        print("sweep", factor, value, flush=True)
    (out / "runs.json").write_text(json.dumps({"manifest": manifest(vars(a)), "runs": rows}) + "\n")
    print(out / "runs.json")


def cmd_llm(a):
    tag = a.model.replace(":", "_").replace("/", "_")
    out = Path(a.out) / "llm" / tag
    cache = Path(a.cache_from) / "llm" / tag / "cache.jsonl" if a.cache_from else out / "cache.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    path = out / "runs.json"
    for rep in range(a.reps):
        agent = LLMAgent(a.model, a.host, rep, cache, cache_only=a.cache_only)
        for s in CAMPAIGN:
            agent.reset()
            r = run(s, agent, seed=1000 + rep, budget=a.budget, p_mid=a.p_mid)
            r.update({"model": a.model, "rep": rep, "tokens": agent.run_tokens,
                      "model_seconds": round(agent.run_seconds, 1), "cache_misses": agent.misses})
            rows.append(r)
            print(a.model, rep, s, "released", r["releases"], "wrong", r["wrong_releases"], "final",
                  r["final_released"], r["final_wrong"], "llm calls so far", agent.calls, flush=True)
            path.write_text(json.dumps({"manifest": manifest(vars(a)), "runs": rows}) + "\n")
    print(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sim", "llm", "impact", "sweep"])
    ap.add_argument("--out", default=str(RAW), help="raw-results directory (default results/raw/sosym)")
    ap.add_argument("--cache-only", dest="cache_only", action="store_true")
    ap.add_argument("--cache-from", dest="cache_from", default=None, help="read LLM caches from this raw directory")
    ap.add_argument("--runs", type=int, default=500)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--host", default=os.environ.get("VGC_OLLAMA", "http://localhost:11434"))
    ap.add_argument("--budget", type=int, default=4)
    ap.add_argument("--p-mid", dest="p_mid", type=float, default=0.6)
    ap.add_argument("--p-err", dest="p_err", type=float, default=0.25)
    ap.add_argument("--nocheck", action="store_true")
    a = ap.parse_args()
    {"sim": cmd_sim, "llm": cmd_llm, "impact": cmd_impact, "sweep": cmd_sweep}[a.cmd](a)
