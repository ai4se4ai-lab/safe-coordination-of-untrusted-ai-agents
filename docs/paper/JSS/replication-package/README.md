# Replication package: *Trustworthy Coordination of Untrusted LLM Agents in Software Engineering Workflows*

This directory is for the reviewers of the JSS manuscript [`../main.tex`](../main.tex). It shows where each part of the
approach is implemented, which experiment produced each result, and which recorded log each number in the paper comes from.
It also contains a script that regenerates all of those numbers from the logs and checks them against the manuscript.

Repository: <https://github.com/ai4se4ai-lab/safe-coordination-of-untrusted-ai-agents>. All paths below are relative to
the repository root unless they start with `./`, which means this directory.

---

## 1. Check the paper's numbers (about 10 seconds, standard library only)

```bash
git clone https://github.com/ai4se4ai-lab/safe-coordination-of-untrusted-ai-agents
cd safe-coordination-of-untrusted-ai-agents
python3 docs/paper/JSS/replication-package/verify.py      # Python >= 3.10, no packages needed
```

`verify.py` calls no model and runs no experiment again. It does the following:

1. It builds a temporary, repository-shaped tree from the recorded evidence in [`./evidence/`](evidence/) and runs the
   repository's own generators on it ([`experiments/scientific_paper.py`](../../../../experiments/scientific_paper.py) and
   [`experiments/revision_paper.py`](../../../../experiments/revision_paper.py)).
2. It compares **all 148 number macros** defined in `main.tex` (100 of them appear in the JSS text) with the regenerated
   values.
3. It checks that **every data row and figure cell** of the RQ1–RQ4 tables and figures appears verbatim in `main.tex`.
4. It recomputes the per-stage feedback counts that the RQ3 prose quotes without macros (212/290 overall; 153/165
   designs, 19/68 implementations, 40/57 test suites).
5. It compares the source-code hashes recorded inside every result file with the code in your checkout. This step only
   reports; see §7.

Expected output ends in `ALL CHECKS PASSED`. The regenerated fragments are written to [`./generated/`](generated/),
and [`./claims.csv`](claims.csv) lists every number with its value, the sections that use it, the evidence file and the
generator.

---

## 2. What is in this directory

| Path | Contents |
|---|---|
| `README.md` | this map |
| `verify.py` | the regeneration and consistency check (§1) |
| `claims.csv` | one row per number macro: value, sections of the paper that use it, evidence file, generator, producing experiment |
| `generated/` | TeX fragments regenerated from the evidence (`numbers*.tex`, `fig-*.tex`, `tab-*.tex`), plus `provenance*.json` holding the SHA-256 of every input and output |
| `evidence/results/processed/tse/` | processed results of RQ1 (`campaign.json` → `ablation`), the pre-fix defect (`prefix-defect.json`), RQ2 (`campaign.json` → `cost`, and `graph.json`), and the curated list of RQ3 runs (`llm-runs.json`) |
| `evidence/results/raw/20261121T172800-llm-all/` | RQ3 run on the local GB10 (`qwen3-coder:30b`, `gpt-oss:20b`): `results.json` and **every model call** in `calls.jsonl` |
| `evidence/hpc-fetched/{narval,rorqual}/results-raw/*-llm-all/` | RQ3 runs on the Alliance clusters (one model per run): `results.json` and `calls.jsonl` |
| `evidence/hpc-fetched/rorqual/outputs/full/benchmark/<model>/` | RQ4: per model and benchmark, `results-*.json` (per-task outcomes) and `calls-*.jsonl` (every model call) |
| `evidence/results/processed/document-service-v1/`, `evidence/results/processed/tse/tlc-extended.json` | inputs the generators also read; they feed only macros of the formal companion paper, which the JSS text does not use |
| `SHA256SUMS` | checksums of `evidence/` and `generated/` (`sha256sum -c SHA256SUMS`) |

The cluster outputs (`hpc/fetched/`) are not tracked in the repository's git history (see `.gitignore`), so this
directory holds the copies that reviewers can use. The call logs contain prompts, full responses, token counts and
latencies. They contain no credentials or user paths. Size: about 21 MB.

---

## 3. Approach → code

| Paper element | Implementation |
|---|---|
| Generic kernel used for RQ2 (coupled, scheduling) and RQ3–RQ4 (§3.7, "generic kernel", 258 lines) | [`src/vgc/graph.py`](../../../../src/vgc/graph.py), class `GraphController` |
| Reference controller used for RQ1 and RQ2 (independent) (§3.7, about 350 lines) | [`src/vgc/controller.py`](../../../../src/vgc/controller.py), class `Controller` |
| Canonical dependency key (§3.2) | `graph.py: canonical()`, `GraphController.observation()`; `controller.py: Controller.observation()` |
| Usable(j) (§3.2) | `GraphController.usable()`; `Controller._usable()` |
| Algorithm 1, ApplyChange / Refresh / NewEpisode (cancellation, demotion) | `GraphController.edit()` and `._reconcile()`; `Controller.edit_source()`, `.update_context()`, `.reconfigure()`, `._reconcile()`, `._candidate()`/`._install()` (private copy, then install) |
| Algorithm 2, Dispatch (upstream gate, budget, fresh request identity) | `GraphController.dispatch()`, `.eligible()`; `Controller.dispatch()` |
| Algorithm 2, OnReply / OnTimeout (commit guard: active request, key recheck, authority, validator, WF for every configured consumer) | `GraphController.resolve()`, `._current()`; `Controller.resolve()`, `._check_structure()` |
| Algorithm 3, Publish (all usable, then global predicate G) | `GraphController.publishable()`; `Controller.check_publication()`, `.publish()` |
| Transition log and independent trace checker (§3.7) | `Controller._event()`; [`verification/trace_conformance.py`](../../../../verification/trace_conformance.py) (does not import the controller) |
| Scripted document-service case study (RQ1, RQ2) | [`case-study/document-service/`](../../../../case-study/document-service/), [`experiments/scenarios.py`](../../../../experiments/scenarios.py), [`src/vgc/validators.py`](../../../../src/vgc/validators.py), [`src/vgc/structure.py`](../../../../src/vgc/structure.py) |
| LLM document-service workflow (RQ3): job declarations (22 lines), validators (43 lines), global predicate | [`experiments/llm/workflow.py`](../../../../experiments/llm/workflow.py): `jobs()`, `findings()`, `conventions()`, `spec_of()`, `global_predicate()`; `validate_design()`, `validate_implementation()`, `validate_tests()` |
| Sandboxed property-based checker with shrinking (183 lines) | [`experiments/llm/sandbox_runner.py`](../../../../experiments/llm/sandbox_runner.py) |
| Ollama client (fixed seeds, logged calls) | [`experiments/llm/client.py`](../../../../experiments/llm/client.py) |
| Benchmark workflow (RQ4): code and tests jobs (17 lines) | [`experiments/benchmark_study.py`](../../../../experiments/benchmark_study.py): `build_jobs()`, `check()`, `sandbox()` |
| Benchmark data (HumanEval+, MBPP+) | [`data/benchmarks/`](../../../../data/benchmarks/) (SHA-256 recorded in each RQ4 result file as `dataset_sha256`) |
| Unit and regression tests | [`tests/test_transactions.py`](../../../../tests/test_transactions.py) (`python3 -m unittest discover -s tests`) |

The line counts quoted in the paper (`\GraphLines`, `\WorkflowDeclLines`, `\WorkflowValidatorLines`, `\SandboxLines`,
`\BenchDeclLines`) are computed from these files by `revision_paper.py: effort()`, counting non-blank, non-comment lines.

---

## 4. Research questions → experiment → evidence → paper

| RQ | What is measured | Driver (re-run command) | Evidence | Paper artifacts |
|---|---|---|---|---|
| **RQ1** necessity | 12 controllers (reference + 11 variants) × 300 seeds × 120 adversarial actions = 3,600 runs; independent oracle for P1–P7, L1 | `python3 experiments/scientific_campaign.py` (about 9 min; no LLM) → `results/processed/tse/campaign.json` | `evidence/results/processed/tse/campaign.json` → `ablation` | Table 4 (variants), Fig. 4 (ablation heat map), RQ1 prose |
| RQ1 defect | pre-fix controller: 7 of 300 runs with API exceptions | earlier controller version, same campaign driver | `evidence/results/processed/tse/prefix-defect.json` | "A defect found by the campaign" |
| **RQ2** independent cost | 5 strategies, N ∈ {1…32}, 5 seeds × 40 changes | `experiments/scientific_campaign.py` (same run) | `campaign.json` → `cost` | Fig. 5 (cost) |
| RQ2 coupled, scheduling, differential | 32 modules / 8 shared models / f ∈ {0,1,2,4,8}; layered graphs d ≤ 6, w ≤ 4, 30 seeds; kernel vs. reference on 150 streams | `python3 experiments/graph_experiments.py` (about 31 min; no LLM) → `results/processed/tse/graph.json` | `evidence/results/processed/tse/graph.json` | Table "coupled", Table "scheduling", §3.7 differential claim |
| **RQ3** real LLMs | completion (42 trials), stale (77), cutoff, cost (3 models); 7 models, 3,437 logged calls | `python3 experiments/llm_study.py --part all --models <m>` (needs Ollama); on the clusters through `hpc/slurm/vgc_llm.sbatch` with `STUDY=llm` (submitted with `hpc/scripts/fleet.py`) | the 6 runs listed in `evidence/results/processed/tse/llm-runs.json` | Tables "llm", "llm-cutoff", "llm-cost"; RQ3 prose |
| **RQ4** benchmarks | 5 models × 542 tasks (164 HumanEval+, 378 MBPP+), 14,069 calls; base tests as validator, plus tests as ground truth | `python3 experiments/benchmark_study.py --benchmark {humaneval,mbpp} --model <m>`; on the clusters through `vgc_llm.sbatch` with `STUDY=benchmark` | `evidence/hpc-fetched/rorqual/outputs/full/benchmark/*/results-*.json` | Table "bench"; RQ4 prose |
| Tables/figures/macros | rendering only | `python3 experiments/scientific_paper.py && python3 experiments/revision_paper.py` (writes `docs/paper/generated/`); `verify.py` does the same from this package | `./generated/`, `./generated/provenance*.json` | inlined into `main.tex` between `% BEGIN inlined generated/...` markers |

RQ1/RQ2 are deterministic functions of their seeds (`seed0` arguments in the drivers): rerunning them reproduces the
processed files exactly. RQ1 alone (`scientific_campaign.py`) and RQ2's kernel experiments (`graph_experiments.py`) run on a
laptop. Add `--quick` for a smoke run that writes `*-quick.json` and leaves the paper's inputs untouched.

### RQ3 runs used in the paper

| Run | Site / hardware | Model(s) | Ollama digest | Calls | Cost runs |
|---|---|---|---|---|---|
| `20261121T172800-llm-all` | local NVIDIA GB10 | `qwen3-coder:30b`, `gpt-oss:20b` | `06c1097e…`, `17052f91…` | 1,139 | `qwen3-coder:30b` |
| `20261121T173759-llm-all` | Rorqual (H100) | `qwen2.5-coder:7b` | `dae161e2…` | 682 | yes |
| `20261121T173930-llm-all` | Rorqual (H100) | `mistral-small:24b` | `8039dd90…` | 791 | yes |
| `20261121T173526-llm-all` | Narval (A100) | `llama3.1:8b` | `46e0c10c…` | 279 | no |
| `20261121T173530-llm-all` | Narval (A100) | `phi4:14b` | `ac896e5b…` | 350 | no |
| `20261121T174731-llm-all` | Narval (A100) | `gemma2:9b` | `ff02c370…` | 196 | no |

Full digests are in each run's `results.json` → `model_digests`. Total calls: 3,437 (`\LlmCallsTotal`).

### RQ4 runs used in the paper

All ten RQ4 result files come from Rorqual (5 models × 2 benchmarks, temperature 0.2, budget k = 3, shard 0/1). Each
file records `calls_total`, token counts, `dataset_sha256` (equal to `sha256sum data/benchmarks/*.gz`) and the per-task
`rows`. The RQ4 result files do not record the model digest. The same Ollama tags were used for RQ3, whose digests are
listed above.

---

## 5. Inspecting a single decision

Every call log line is one JSON object with the job, episode, attempt, prompt digest, full response, token counts and
latency. For example, all stale-trial replies of one model:

```bash
python3 - <<'EOF'
import json
p = "docs/paper/JSS/replication-package/evidence/hpc-fetched/rorqual/results-raw/20261121T173930-llm-all/results.json"
r = json.load(open(p))
for t in r["stale"][:3]:
    print({k: v for k, v in t.items() if not isinstance(v, (list, dict))})
EOF
```

The RQ3 per-trial records are under `completion`, `stale`, `cutoff` and `cost` in each `results.json`. The RQ4
per-task records are under `rows`.

---

## 6. Runs that were excluded, and why

| Excluded data | Reason (as stated in the paper or in `llm-runs.json`) |
|---|---|
| `20261121T173345-llm-all` (Rorqual) | one-trial smoke run (`llm-runs.json` → `note`) |
| `20261121T173855-llm-all` (Rorqual) | empty call log, no `results.json` (job produced no data) |
| `deepseek-coder-v2:16b` (RQ3 and RQ4) | needed minutes per short completion on our Ollama build; replaced by `gemma2:9b` before any reported data was collected (§7, External validity). Its partial logs are not included. |
| Narval MBPP+ benchmark jobs | produced call logs but no result files; MBPP+ was resubmitted on Rorqual, and only those results are used |
| `outputs/smoke/*`, `*-quick.json`, `results/raw/*-bench-*` (local) | smoke and pilot runs; the generators ignore them |

---

## 7. Known deviations between recorded code hashes and this checkout

Each result file records the SHA-256 of the code that produced it (`source_sha256`). `verify.py` compares these hashes
with the current checkout:

* RQ1, RQ2 and five of the six RQ3 runs: **all recorded hashes match** the committed code.
* **RQ3, GB10 run `20261121T172800-llm-all`**: `src/vgc/graph.py`, `experiments/llm/workflow.py` and
  `experiments/llm/sandbox_runner.py` match. Only the driver `experiments/llm_study.py` differs: the run was made with
  an earlier, uncommitted revision of the driver. That run's `results.json` lacks the `host`/`ollama`/`quick`/
  `cost_models` metadata fields that the later runs record. The kernel, workflow declarations, validators and sandbox
  were identical.
* **RQ4, all five HumanEval+ result files**: the kernel, workflow and sandbox match. Only `experiments/benchmark_study.py`
  differs from the committed revision. The HumanEval+ jobs ran first, and the MBPP+ jobs, which were resubmitted later,
  match the committed file.

---

## 8. Repository map

| Directory | Role | Used by the JSS paper |
|---|---|---|
| `src/vgc/` | reference controller (`controller.py`), generic kernel (`graph.py`), validators, structural normalizer, scripted providers | yes: all RQs |
| `experiments/` | drivers: `scientific_campaign.py` (RQ1, RQ2 independent), `graph_experiments.py` (RQ2 coupled/scheduling/differential), `llm_study.py` + `llm/` (RQ3), `benchmark_study.py` + `bench/` (RQ4); generators `scientific_paper.py`, `revision_paper.py` | yes |
| `case-study/document-service/` | requirements, policies, fixtures, scenarios of the scripted case study | yes: RQ1, RQ2 |
| `data/benchmarks/` | HumanEval+ and MBPP+ (EvalPlus releases) | yes: RQ4 |
| `hpc/` | Slurm job script (`slurm/vgc_llm.sbatch`), submit/fetch tool (`scripts/fleet.py`), cluster config | yes: RQ3, RQ4 execution |
| `results/processed/tse/` | processed RQ1–RQ3 inputs of the generators (copied in `./evidence/`) | yes |
| `results/raw/` | timestamped raw runs with manifests and source archives | RQ3 GB10 run only; the rest is mostly the formal companion work |
| `verification/` | independent trace checker; baseline of an earlier manuscript | trace checker (§3.7) |
| `tests/` | regression tests of the controller | supporting |
| `specification/`, `models/`, `proofs/`, `experiments/sosym/`, `results/processed/sosym/` | TLA+ specification, TLC model configurations, TLAPS proofs, SoSyM case study | **no**: these belong to the separately submitted formal companion paper. The JSS manuscript makes no claim that rests on them. |
| `docs/` | threat model, semantics, assumptions, reproducibility notes, claim–evidence matrix of the earlier artifact; manuscripts | background |
| `environment/` | Dockerfile and lock file of the proof toolchain | companion paper |

---

## 9. Numbers in the prose that are not macros

`verify.py` checks every macro, every table/figure row, and the RQ3 per-stage feedback counts. A few numbers in the
prose were derived by hand from these regenerated tables or logs and are not checked automatically:

* RQ2: "87.7" requests per change for the whole-workspace strategy at N = 32 is the point `(32,87.68)` of that series
  in `generated/fig-cost.tex`.
* RQ3 cost: "71 against 313 requests (4.4×)" and "59.4 against 243.6 kTokens (4.1×)" are the exact-key and
  full-regeneration rows of `generated/tab-llm-cost.tex`, summed over `mistral-small:24b` and `qwen3-coder:30b`.
* RQ3 stale: "Of 84 planned trials, 7 could not run" means 84 `stale` records in the six RQ3 `results.json` files,
  7 of them with `skipped` set.
* RQ4 transitions ("2,710 task–model pairs, 2,263 … 1,821 … 70 … 63 … 384 …", "1,773 … 420 … 499 … 1,274 …") are
  derived from the per-task `rows` of the ten RQ4 result files (2,710 = 542 tasks × 5 models).
