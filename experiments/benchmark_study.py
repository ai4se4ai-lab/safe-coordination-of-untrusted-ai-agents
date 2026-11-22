"""RQ6: guarded coordination on standard benchmarks (EvalPlus HumanEval+ and MBPP+).

Each benchmark task becomes a two-job workflow coordinated by the generic kernel:

  code/<task>   the function, proposed by an LLM; declared validator V: the
                benchmark's *base* tests (outputs of the reference solution on
                base_input), with the first failing case returned as feedback;
  tests/<task>  an assert-based test suite for that function, depending on the
                accepted code; validator: >= 3 tests that pass on the reference
                solution and on the accepted code.

The benchmark's *plus* inputs are never shown to the controller: they are the ground
truth R used only to measure how often a validator-accepted value is nevertheless
wrong (validator-relative correctness, Corollary 3). After the initial repair, every
code job's contract is replaced by a reworded instruction with the same meaning; we
then measure how often the regenerated value is byte-, AST- or behaviourally equal,
and how many test-suite regenerations exact early cutoff avoids.

    python experiments/benchmark_study.py --benchmark humaneval --model qwen2.5-coder:7b \
        [--host http://127.0.0.1:11434] [--shard 0/1] [--limit 10] [--parallel 4] [--out DIR]
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import argparse
import datetime
import gzip
import hashlib
import json
import platform
import random
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "experiments")]

from vgc.graph import GraphController, Job  # noqa: E402
from llm.client import chat  # noqa: E402
from llm.workflow import ast_normal  # noqa: E402

RUNNER = ROOT / "experiments/bench/sandbox_bench.py"
FILES = {"humaneval": "HumanEvalPlus.jsonl.gz", "mbpp": "MbppPlus.jsonl.gz"}
MAX_PLUS = 200  # plus inputs per task used as ground truth (seeded subsample)

CONTRACTS = {
    "code-v1": "Complete the following Python task. Return the complete, self-contained function definition "
               "(with any imports it needs) in a single ```python code block and nothing else.",
    "code-v2": "Solve this Python programming task. Reply with only one ```python code block containing the "
               "full function definition, including every import it requires.",
    "tests-v1": "Write unit tests for the function below. Define at least three functions named test_<name>() "
                "that call the function and check results with plain assert statements; no imports of test "
                "frameworks, no I/O. Return a single ```python code block.",
}


def load_tasks(benchmark, shard="0/1", limit=0):
    rows = [json.loads(l) for l in gzip.open(ROOT / "data/benchmarks" / FILES[benchmark])]
    i, n = map(int, shard.split("/"))
    rows = [r for k, r in enumerate(rows) if k % n == i]
    if limit:
        rows = rows[:limit]
    tasks = {}
    for r in rows:
        reference = r["prompt"] + r["canonical_solution"] if benchmark == "humaneval" else r["canonical_solution"]
        rng = random.Random(r["task_id"])
        plus = list(r["plus_input"] or [])  # Mbpp/793 ships plus_input = {} (no plus inputs)
        plus = plus if len(plus) <= MAX_PLUS else rng.sample(plus, MAX_PLUS)
        prompt = r["prompt"] if benchmark == "humaneval" else (
            r["prompt"].strip() + "\nThe function must be named %s." % r["entry_point"])
        tasks[r["task_id"].replace("/", "_")] = {"task_id": r["task_id"], "prompt": prompt,
                                                  "entry_point": r["entry_point"], "reference": reference,
                                                  "base": r["base_input"], "plus": plus, "atol": r["atol"] or 0}
    return tasks


def sandbox(job, timeout=180):
    try:
        p = subprocess.run([sys.executable, "-I", str(RUNNER)], input=json.dumps(job), capture_output=True,
                           text=True, timeout=timeout)
        return json.loads(p.stdout) if p.stdout.strip() else {"ok": False, "diagnostic": "no verdict"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "diagnostic": "execution timed out"}
    except json.JSONDecodeError:
        return {"ok": False, "diagnostic": "unreadable verdict"}


def check(task, code, inputs, all_outputs=False):
    return sandbox({"kind": "code", "code": code, "reference": task["reference"], "entry_point": task["entry_point"],
                    "inputs": inputs, "atol": task["atol"], "all": all_outputs})


def build_jobs(tasks, contracts):
    jobs = []
    for key, task in tasks.items():
        def v_code(o, v, task=task):
            if not isinstance(v, str) or not v.strip():
                return False, "empty answer"
            verdict = check(task, v, task["base"])
            return verdict["ok"], verdict.get("diagnostic")

        def v_tests(o, v, task=task, key=key):
            code = o["prerequisites"]["code/" + key]
            verdict = sandbox({"kind": "tests", "tests": v, "code": code, "reference": task["reference"],
                               "entry_point": task["entry_point"]})
            return verdict["ok"], verdict.get("diagnostic")

        jobs.append(Job("code/" + key, 0, (), "coder", contracts["code"], lambda X, k=key: X[k], None, v_code))
        jobs.append(Job("tests/" + key, 1, ("code/" + key,), "tester", contracts["tests"], lambda X, k=key: X[k],
                        None, v_tests))
    return jobs


def parse_code(text):
    blocks = re.findall(r"```(?:python|py|Python)?\s*\n(.*?)```", text, re.S)
    return (max(blocks, key=len) if blocks else text).strip() + "\n"


def render(q):
    o = q.observation
    parts = [CONTRACTS[o["contract"]], "", o["source"]["prompt"].rstrip()]
    if q.job.startswith("tests/"):
        parts += ["", "Function under test:", "```python", o["prerequisites"]["code/" + q.job.split("/", 1)[1]].rstrip(),
                  "```"]
    if q.feedback:
        parts += ["", "Your previous answer was rejected: " + q.feedback[:600], "Fix it."]
    return "\n".join(parts)


class Provider:
    def __init__(self, host, model, log, temperature):
        self.host, self.model, self.log, self.temperature = host, model, log, temperature
        self.lock = threading.Lock()
        self.raw = {}
        self.calls = self.prompt_tokens = self.output_tokens = 0

    def __call__(self, q):
        prompt = render(q)
        seed = int(hashlib.sha256(q.identity.encode()).hexdigest()[:8], 16)
        text, meta = chat(self.host, self.model, prompt, self.temperature, seed, num_predict=2048, num_ctx=8192)
        with self.lock:
            self.calls += 1
            self.prompt_tokens += meta["prompt_tokens"] or 0
            self.output_tokens += meta["output_tokens"] or 0
            self.raw[q.identity] = text
            self.log.write(json.dumps({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                       "model": self.model, "request": q.identity, "job": q.job,
                                       "attempt": q.attempt, "feedback": q.feedback, "seed": seed,
                                       "temperature": self.temperature,
                                       "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                                       "response": text, **meta}) + "\n")
            self.log.flush()
        return parse_code(text)


def run_async(c, provider, workers):
    with ThreadPoolExecutor(workers) as pool:
        running = {}

        def work(q):
            value = provider(q)
            return q, value, c.resolve(q.identity, value)

        while True:
            for jid in c.eligible():
                q = c.dispatch(jid)
                if q is not None:
                    running[pool.submit(work, q)] = q
            if not running:
                return
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for f in done:
                running.pop(f)
                f.result()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", choices=sorted(FILES), required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--budget", type=int, default=3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    tasks = load_tasks(a.benchmark, a.shard, a.limit)
    tag = "%s__%s__%s" % (a.benchmark, a.model.replace(":", "_").replace("/", "_"), a.shard.replace("/", "of"))
    out = Path(a.out) if a.out else ROOT / "results/raw" / (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-bench-" + tag)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    contracts = {"code": "code-v1", "tests": "tests-v1"}
    inputs = {k: {"prompt": t["prompt"], "entry_point": t["entry_point"]} for k, t in tasks.items()}
    with (out / ("calls-%s.jsonl" % tag)).open("w") as log:
        provider = Provider(a.host, a.model, log, a.temperature)
        c = GraphController(build_jobs(tasks, contracts), inputs, {}, a.budget, "exact")
        run_async(c, provider, a.parallel)
        initial = {k: {"code": c.records["code/" + k].value if c.usable("code/" + k) else None,
                       "code_request": c.records["code/" + k].evidence_request,
                       "code_attempts": c.records["code/" + k].attempts,
                       "tests_usable": c.usable("tests/" + k),
                       "tests_attempts": c.records["tests/" + k].attempts if "tests/" + k in c.records else 0}
                   for k in tasks}
        calls_initial = provider.calls
        # Reworded contract with the same meaning for every code job.
        work0 = dict(c.work_episodes)
        contracts = {"code": "code-v2", "tests": "tests-v1"}
        c.edit(jobs=build_jobs(tasks, contracts))
        run_async(c, provider, a.parallel)
        rows = []
        for k, task in tasks.items():
            row = {"task": task["task_id"], "plus_inputs": len(task["plus"]), **initial[k]}
            requests = [q for q in c.history.values() if q.job == "code/" + k]
            first_q = min(requests, key=lambda q: (q.episode, q.attempt)) if requests else None
            first_code = parse_code(provider.raw[first_q.identity]) if first_q and first_q.identity in provider.raw else None
            # Ground truth on base+plus for the first proposal (no validator) and the accepted value.
            full = task["base"] + task["plus"]
            row["first_proposal_correct"] = bool(first_code and check(task, first_code, full)["ok"])
            row["first_proposal_base_ok"] = bool(first_code and check(task, first_code, task["base"])["ok"])
            if row["code"] is not None:
                row["accepted_correct"] = check(task, row["code"], full)["ok"]
            new = c.records["code/" + k].value if c.usable("code/" + k) else None
            row["regenerated_usable"] = new is not None
            row["regen_requests"] = c.records["code/" + k].attempts
            row["tests_regenerated"] = c.work_episodes.get("tests/" + k, 0) > work0.get("tests/" + k, 0)
            if row["code"] is not None and new is not None:
                row["raw_equal"] = provider.raw.get(c.records["code/" + k].evidence_request) == \
                    provider.raw.get(row["code_request"])
                row["value_equal"] = new == row["code"]
                row["ast_equal"] = ast_normal(new) is not None and ast_normal(new) == ast_normal(row["code"])
                o1 = check(task, row["code"], task["plus"], True).get("outputs")
                o2 = check(task, new, task["plus"], True).get("outputs")
                row["behaviour_equal"] = o1 is not None and o1 == o2
                row["regenerated_correct"] = check(task, new, full)["ok"]
            del row["code"]
            rows.append(row)
    report = {"benchmark": a.benchmark, "model": a.model, "shard": a.shard, "limit": a.limit, "budget": a.budget,
              "temperature": a.temperature, "tasks": len(tasks), "host": platform.node(),
              "python": platform.python_version(), "calls_initial": calls_initial, "calls_total": provider.calls,
              "prompt_tokens": provider.prompt_tokens, "output_tokens": provider.output_tokens,
              "discarded": c.discarded, "elapsed_seconds": time.monotonic() - started, "contracts": CONTRACTS,
              "dataset_sha256": hashlib.sha256((ROOT / "data/benchmarks" / FILES[a.benchmark]).read_bytes()).hexdigest(),
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                ("src/vgc/graph.py", "experiments/benchmark_study.py",
                                 "experiments/bench/sandbox_bench.py", "experiments/llm/client.py")},
              "rows": rows}
    (out / ("results-%s.json" % tag)).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(out, "%d tasks %.0fs %d calls" % (len(tasks), report["elapsed_seconds"], provider.calls))


if __name__ == "__main__":
    raise SystemExit(main())
