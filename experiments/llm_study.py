"""RQ5: the coordination semantics with real LLM proposers (local, via Ollama).

    python experiments/llm_study.py --part completion|stale|cutoff|cost|all [--models m1,m2] [--quick]

Every model call is logged (prompt digest, full response, token counts, latency) to
results/raw/<run>/calls.jsonl. Models run locally; no data leaves the machine.

completion : initial repair of 4-service workspaces with budget k=3 and validator
             feedback; local and global (barrier) rejections; one bounded feedback
             epoch that promotes a barrier conflict to a workspace convention.
stale      : a requirement changes while the implementation request is in flight;
             the late reply is judged against the old and the current validator.
cutoff     : a reworded (semantically equal) contract regenerates a design or an
             implementation; how often is the new value byte-, canonically, AST- or
             semantically equal to the old one, and how many downstream requests does
             early cutoff save?
cost       : one change stream under four invalidation strategies; requests,
             tokens, wall-clock time and publication outcome.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import platform
import random
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from vgc.graph import GraphController, canonical  # noqa: E402
from llm import workflow as wf  # noqa: E402

import os
HOST = os.environ.get("VGC_OLLAMA", "http://localhost:11434")
OLLAMA = HOST + "/api/chat"
DEFAULT_MODELS = ["qwen2.5-coder:7b", "llama3.1:8b", "gpt-oss:20b", "qwen3-coder:30b"]
BASE_CONTRACTS = {"design": "design-v1", "impl": "impl-v1", "tests": "tests-v1"}


class Provider:
    """Calls a local model; the prompt is rendered from the request's observation only."""

    def __init__(self, model, log, temperature=0.7, workspace=None, seed=0):
        self.model, self.log, self.temperature = model, log, temperature
        self.workspace, self.seed = workspace, seed
        self.lock = threading.Lock()
        self.calls = self.prompt_tokens = self.output_tokens = 0
        self.seconds = 0.0
        self.raw = {}

    def __call__(self, q, controller=None):
        kind = q.job.split("/")[0]
        workspace = None
        if self.workspace is not None and controller is not None:
            workspace = {"inputs": q.observation.get("workspace", {}).get("inputs"),
                         "context": q.observation.get("workspace", {}).get("context")}
        prompt = wf.render(q, workspace)
        seed = int(hashlib.sha256((q.identity + str(self.seed)).encode()).hexdigest()[:8], 16)
        body = {"model": self.model, "stream": False, "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": self.temperature, "seed": seed, "num_predict": 2500, "num_ctx": 8192}}
        started = time.monotonic()
        error = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
                response = json.load(urllib.request.urlopen(request, timeout=900))
                break
            except Exception as e:  # noqa: BLE001 transport failure: retry the same call
                error, response = repr(e), None
                time.sleep(2)
        elapsed = time.monotonic() - started
        text = (response or {}).get("message", {}).get("content", "")
        value = wf.parse(kind, text)
        record = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "model": self.model,
                  "request": q.identity, "job": q.job, "attempt": q.attempt, "feedback": q.feedback,
                  "temperature": self.temperature, "seed": seed,
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt),
                  "prompt_tokens": (response or {}).get("prompt_eval_count"),
                  "output_tokens": (response or {}).get("eval_count"), "seconds": elapsed,
                  "transport_error": error, "response": text}
        with self.lock:
            self.calls += 1
            self.prompt_tokens += record["prompt_tokens"] or 0
            self.output_tokens += record["output_tokens"] or 0
            self.seconds += elapsed
            self.raw[q.identity] = text
            self.log.write(json.dumps(record) + "\n")
            self.log.flush()
        return value


def run_async(c, provider, workers=4, on_dispatch=None, max_seconds=3600):
    """Dispatch every eligible job, resolve replies as they arrive (validation off-lock)."""
    started = time.monotonic()
    outcomes = []
    with ThreadPoolExecutor(workers) as pool:
        running = {}
        while True:
            for jid in c.eligible():
                q = c.dispatch(jid)
                if q is None:
                    continue
                if on_dispatch:
                    on_dispatch(c, q)
                running[pool.submit(provider, q, c)] = q
            if not running or time.monotonic() - started > max_seconds:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                q = running.pop(future)
                value = future.result()
                outcome, diagnostic = c.resolve(q.identity, value)
                outcomes.append({"request": q.identity, "job": q.job, "attempt": q.attempt,
                                 "outcome": outcome, "diagnostic": diagnostic})
    return outcomes


def workspace(rng, n, findings_rate=0.5):
    services = rng.sample(wf.SERVICES, n)
    documents = {"d%d" % (i + 1): wf.source(s, rng.random() < 0.5) for i, s in enumerate(services)}
    context = {"f-" + d: {"kind": "finding", "document": d, "finding": "path-traversal",
                          "text": "SEC-1 path traversal: identifiers must not contain '/' or '..'."}
               for d in documents if rng.random() < findings_rate}
    return documents, context


def controller(documents, context, mode="exact", contracts=None, budget=3):
    contracts = contracts or dict(BASE_CONTRACTS)
    c = GraphController(wf.jobs(documents, contracts), documents, context, budget, mode,
                        global_predicate=wf.global_predicate)
    return c, contracts


def kind_of(job):
    return job.split("/")[0]


# ------------------------------------------------------------------- completion

def part_completion(models, log, trials, n=4, seed0=500):
    rows = []
    for model in models:
        for t in range(trials):
            rng = random.Random(seed0 + t)
            documents, context = workspace(rng, n)
            provider = Provider(model, log, 0.7, seed=t)
            c, _ = controller(documents, context)
            started = time.monotonic()
            outcomes = run_async(c, provider)
            publishable = c.publishable()
            barrier_conflict = (not c.suspended and not c.pending and
                                all(c.usable(j) for j in c.active) and not publishable)
            epoch_outcomes, epoch_used = [], False
            if barrier_conflict:
                # Bounded feedback epoch (K_epoch = 1): the controller promotes the barrier
                # diagnostic to a workspace convention selected by every design job.
                types = [c.records[j].value["id_type"] for j in c.active if j.startswith("design/")]
                majority = max(sorted(set(types)), key=types.count)
                ctx = deepcopy(c.context)
                ctx["convention-ids"] = {"kind": "convention", "finding": "ids", "document": "*",
                                         "text": "All services of this workspace use %s identifiers." % majority}
                c.edit(context=ctx)
                epoch_used = True
                epoch_outcomes = run_async(c, provider)
            status = c.status()
            accepted = {j: c.records[j].value for j in c.active if c.usable(j)}
            rows.append({"model": model, "trial": t, "documents": n, "seconds": time.monotonic() - started,
                         "outcomes": outcomes, "epoch_outcomes": epoch_outcomes,
                         "barrier_conflict": barrier_conflict, "feedback_epoch": epoch_used,
                         "published": c.publishable(), "failed": status["failed"], "suspended": status["suspended"],
                         "calls": provider.calls, "prompt_tokens": provider.prompt_tokens,
                         "output_tokens": provider.output_tokens, "model_seconds": provider.seconds,
                         "implementation_forms": sorted({wf.ast_normal(v) and hashlib.sha256(
                             wf.ast_normal(v).encode()).hexdigest()[:12] for j, v in accepted.items()
                             if j.startswith("implementation/")} - {None}),
                         "accepted_ids": {j: v["id_type"] for j, v in accepted.items() if j.startswith("design/")}})
            print("completion", model, t, "published" if rows[-1]["published"] else "not published",
                  "conflict" if barrier_conflict else "", provider.calls, "calls", flush=True)
    return rows


# ------------------------------------------------------------------- stale

def part_stale(models, log, trials, seed0=800):
    rows = []
    for model in models:
        for t in range(trials):
            rng = random.Random(seed0 + t)
            refused = t % 2 == 0
            documents = {"d1": wf.source(rng.choice(wf.SERVICES), refused)}
            provider = Provider(model, log, 0.7, seed=1000 + t)
            c, _ = controller(documents, {})
            # Repair the design first (synchronously).
            while True:
                q = c.dispatch("design/d1")
                if q is None:
                    break
                c.resolve(q.identity, provider(q, c))
            if not c.usable("design/d1"):
                rows.append({"model": model, "trial": t, "skipped": "design failed"})
                continue
            q = c.dispatch("implementation/d1")
            old_observation = q.observation
            future_value = {}
            worker = threading.Thread(target=lambda: future_value.setdefault("v", provider(q, c)))
            worker.start()
            # The clause changes while the agent is generating (409 tightened or relaxed).
            time.sleep(0.5)
            c.edit(inputs={"d1": wf.source(documents["d1"]["service"], not refused)})
            design_after = c.usable("design/d1")
            worker.join()
            value = future_value["v"]
            outcome, _ = c.resolve(q.identity, value)
            old_ok, old_diag = wf.validate_implementation(old_observation, value)
            # Judge the late reply against the current question (the new clause, new design if repaired).
            current = deepcopy(old_observation)
            current["source"] = c.inputs["d1"]
            if c.usable("design/d1"):
                current["prerequisites"] = {"design/d1": c.records["design/d1"].value}
            else:
                # Design must be regenerated for the new clause; use the old design with the new status code.
                d = deepcopy(old_observation["prerequisites"]["design/d1"])
                d["status"]["archived_put"] = 409 if not refused else 200
                current["prerequisites"] = {"design/d1": d}
            new_ok, new_diag = wf.validate_implementation(current, value)
            rows.append({"model": model, "trial": t, "from_refused": refused, "controller_outcome": outcome,
                         "valid_for_old_question": old_ok, "valid_for_current_question": new_ok,
                         "old_diagnostic": old_diag, "current_diagnostic": new_diag,
                         "design_usable_after_edit": design_after})
            print("stale", model, t, outcome, "old", old_ok, "current", new_ok, flush=True)
    return rows


# ------------------------------------------------------------------- cutoff

def part_cutoff(models, log, trials, temperatures=(0.0, 0.7), seed0=900):
    rows = []
    for model in models:
        for temperature in temperatures:
            for t in range(trials):
                rng = random.Random(seed0 + t)
                documents, context = workspace(rng, 1)
                provider = Provider(model, log, temperature, seed=2000 + t)
                c, contracts = controller(documents, context)
                run_async(c, provider)
                if not all(c.usable(j) for j in c.active) or c.suspended:
                    rows.append({"model": model, "temperature": temperature, "trial": t, "skipped": "initial repair"})
                    continue
                for stage, new in (("design", "design-v2"), ("impl", "impl-v2")):
                    job = ("design/d1" if stage == "design" else "implementation/d1")
                    before = deepcopy(c.records[job].value)
                    raw_before = provider.raw.get(c.records[job].evidence_request)
                    r0 = provider.calls
                    contracts = dict(contracts)
                    contracts[stage] = new
                    c.edit(jobs=wf.jobs(c.inputs, contracts))
                    run_async(c, provider)
                    after = c.records[job].value
                    raw_after = provider.raw.get(c.records[job].evidence_request)
                    calls = provider.calls - r0
                    if stage == "design":
                        semantic = (isinstance(after, dict) and isinstance(before, dict) and
                                    after.get("id_type") == before.get("id_type") and
                                    after.get("status") == before.get("status") and
                                    sorted(after.get("operations", [])) == sorted(before.get("operations", [])))
                        ast_equal = None
                    else:
                        semantic = None
                        ast_equal = wf.ast_normal(before) == wf.ast_normal(after) if isinstance(after, str) else False
                    rows.append({"model": model, "temperature": temperature, "trial": t, "stage": stage,
                                 "usable_after": c.usable(job),
                                 "raw_equal": raw_before is not None and raw_before == raw_after,
                                 "value_equal": canonical(before) == canonical(after),
                                 "ast_equal": ast_equal, "semantic_equal": semantic, "requests": calls})
                    print("cutoff", model, temperature, t, stage, "value_equal", rows[-1]["value_equal"],
                          "requests", calls, flush=True)
                    # Restore the original contract for the next stage's measurement.
                    contracts[stage] = BASE_CONTRACTS[stage]
                    c.edit(jobs=wf.jobs(c.inputs, contracts))
                    run_async(c, provider)
    return rows


# ------------------------------------------------------------------- cost

def cost_stream():
    return [("source", "d1"), ("finding-add", "d2"), ("finding-outside", None), ("contract", "design"),
            ("source", "d3"), ("finding-remove", "d2"), ("context-equal", None), ("contract", "impl")]


def part_cost(models, log, n=4, seed0=1200, strategies=("exact", "no-cutoff", "workspace", "full")):
    rows = []
    for model in models:
        rng = random.Random(seed0)
        documents, context = workspace(rng, n, findings_rate=0.0)
        for mode in strategies:
            provider = Provider(model, log, 0.7, workspace=(mode == "workspace"), seed=3000)
            c, contracts = controller(documents, context, mode)
            started = time.monotonic()
            run_async(c, provider)
            per_change = []
            for kind, target in cost_stream():
                calls0, p0, o0, s0 = provider.calls, provider.prompt_tokens, provider.output_tokens, time.monotonic()
                ctx = deepcopy(c.context)
                if kind == "source":
                    X = deepcopy(c.inputs)
                    X[target] = wf.source(X[target]["service"], not X[target]["archived_put_refused"])
                    c.edit(inputs=X)
                elif kind == "finding-add":
                    ctx["f-" + target] = {"kind": "finding", "document": target, "finding": "path-traversal",
                                          "text": "SEC-1 path traversal: identifiers must not contain '/' or '..'."}
                    c.edit(context=ctx)
                elif kind == "finding-outside":
                    ctx["f-outside"] = {"kind": "finding", "document": "billing-ui", "finding": "xss",
                                        "text": "SEC-2 escape HTML in the billing UI."}
                    c.edit(context=ctx)
                elif kind == "finding-remove":
                    ctx.pop("f-" + target, None)
                    c.edit(context=ctx)
                elif kind == "context-equal":
                    c.edit(context=ctx)
                else:
                    contracts = dict(contracts)
                    contracts[target] = {"design": "design-v2", "impl": "impl-v2"}[target]
                    c.edit(jobs=wf.jobs(c.inputs, contracts))
                run_async(c, provider)
                per_change.append({"change": kind, "target": target, "requests": provider.calls - calls0,
                                   "prompt_tokens": provider.prompt_tokens - p0,
                                   "output_tokens": provider.output_tokens - o0,
                                   "seconds": time.monotonic() - s0, "publishable": c.publishable(),
                                   "failed": c.status()["failed"]})
                print("cost", model, mode, kind, target, per_change[-1]["requests"], "requests",
                      "pub" if per_change[-1]["publishable"] else "NOT pub", flush=True)
            rows.append({"model": model, "mode": mode, "changes": per_change, "total_calls": provider.calls,
                         "prompt_tokens": provider.prompt_tokens, "output_tokens": provider.output_tokens,
                         "seconds": time.monotonic() - started})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", default="all", choices=["completion", "stale", "cutoff", "cost", "all"])
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--cost-models", default="qwen2.5-coder:7b,qwen3-coder:30b")
    parser.add_argument("--trials", type=int, default=None)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    models = args.models.split(",")
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-llm-" + args.part
    directory = ROOT / "results/raw" / run_id
    directory.mkdir(parents=True)
    tags = json.load(urllib.request.urlopen(HOST + "/api/tags"))
    report = {"run": run_id, "part": args.part, "models": models, "quick": args.quick, "trials": args.trials,
              "cost_models": args.cost_models, "host": platform.node(), "ollama": HOST, "python": platform.python_version(),
              "platform": platform.platform(),
              "model_digests": {m["name"]: m["digest"] for m in tags["models"] if m["name"] in models +
                                args.cost_models.split(",")},
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                ("src/vgc/graph.py", "experiments/llm_study.py", "experiments/llm/workflow.py",
                                 "experiments/llm/sandbox_runner.py")},
              "contracts": wf.CONTRACTS}
    started = time.monotonic()
    with (directory / "calls.jsonl").open("w") as log:
        quick = args.quick
        if args.part in ("completion", "all"):
            report["completion"] = part_completion(models, log, args.trials or (1 if quick else 6))
        if args.part in ("stale", "all"):
            report["stale"] = part_stale(models, log, args.trials or (2 if quick else 12))
        if args.part in ("cutoff", "all"):
            report["cutoff"] = part_cutoff(models, log, args.trials or (1 if quick else 8))
        if args.part in ("cost", "all") and args.cost_models != "none":
            report["cost"] = part_cost(args.cost_models.split(",") if not quick else models[:1], log)
    report["elapsed_seconds"] = time.monotonic() - started
    (directory / "results.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(directory.relative_to(ROOT), "%.0fs" % report["elapsed_seconds"])


if __name__ == "__main__":
    raise SystemExit(main())
