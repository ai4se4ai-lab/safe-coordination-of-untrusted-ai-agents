# Replication package: *Observation-Relative Consistency for Multi-View Models Built by Untrusted Generative Agents*

This directory is for the reviewers of the SoSyM manuscript [`../main.tex`](../main.tex). It maps every part of the
approach to the code that implements it and every theorem to its evidence. For each case-study research question it gives
the experiment, the recorded data and the table it produced. A script regenerates all numbers in the paper from the
recorded data and checks them against the manuscript.

Repository: <https://github.com/ai4se4ai-lab/safe-coordination-of-untrusted-ai-agents>. Paths below are relative to
the repository root unless they start with `./`, which means this directory. Section numbers (§), tables and
theorems refer to the manuscript.

---

## 1. Check the paper's numbers (about 10 seconds)

```bash
git clone https://github.com/ai4se4ai-lab/safe-coordination-of-untrusted-ai-agents
cd safe-coordination-of-untrusted-ai-agents
pip install scipy                                              # only for two Wilcoxon p-value exponents
python3 docs/paper/SoSyM/replication-package/verify.py         # Python >= 3.10
python3 docs/paper/SoSyM/replication-package/verify.py --rerun # also re-executes the simulated campaigns (~1 min)
```

`verify.py` calls no language model and does not invoke TLC or TLAPS. It performs these checks:

1. **Generated numbers and tables.** It builds a temporary, repository-shaped tree from [`./evidence/`](evidence/) and runs
   the repository's generator [`experiments/sosym/summarize.py`](../../../../experiments/sosym/summarize.py) on it. It then
   compares all **97 generated macros** (`%% BEGIN GENERATED macros`) and every row of the six generated tables
   (Tables `sim`, `perchange`, `impact`, `sweep`, `llm`, `tlc-scaling`) with `main.tex`. These must match exactly.
2. **Hand-maintained macros.** It recomputes the 19 macros above the generated block (first TLC campaign, TLAPS
   obligations, trace validation, differential test, specification size) from their records. It uses the same formulas
   as `experiments/scientific_paper.py` and `experiments/revision_paper.py`.
3. **Numbers typed in the prose and in Appendix B.** It checks every row of Table `tlc` (first TLC campaign: baselines,
   mutant state counts, counterexample lengths) and the per-module TLAPS obligation counts (8/2/9/6). It also checks the
   one-job campaign ("23 runs, 49 s"), the five reachability witnesses, the "193 runs" of the impact caption, the 13 jobs
   at four ranks, and that all scenarios pass, all corruptions are rejected and all regression tests pass.
4. **LLM replay.** For each of the eight models, it compares the original LLM runs with a replay from the cached model
   calls under the current code, run for run (§7).
5. **Source hashes.** It compares the SHA-256 of the code recorded in every raw result file with your checkout. This step
   only reports; §7 explains the differences.
6. With `--rerun`: it re-executes `run_case.py sim|impact|sweep` with the current code and requires the output to equal
   the recorded raw files exactly (500 + 200 + 100 seeds; the runs are deterministic functions of their seeds).

The output ends in `ALL CHECKS PASSED`. The regenerated fragments go to [`./generated/`](generated/).
[`./claims.csv`](claims.csv) lists every macro with its value, the sections that use it, its evidence file and its
generator.

---

## 2. What is in this directory

| Path | Contents |
|---|---|
| `README.md` | this map |
| `verify.py` | the regeneration and consistency check (§1) |
| `claims.csv` | one row per number macro (116): value, sections that use it, evidence, generator |
| `generated/` | regenerated `macros.tex`, `macros-manual.tex`, the six `tab-*.tex` table bodies and `summary.json` |
| `evidence/results/raw/sosym/{sim,impact,sweep}/runs.json` | case study with simulated agents: every run of every discipline, with a manifest (arguments, seeds, git commit, source SHA-256) |
| `evidence/results/raw/sosym/llm/<model>/runs.json`, `cache.jsonl` | RQ4: runs per model, and **every model call** (prompt, full reply, tokens, latency, cache key) |
| `evidence/results/raw/sosym/llm-replay/<model>/runs.json` | RQ4 replayed from `cache.jsonl` with the current code, without a model server |
| `evidence/results/processed/sosym/` | `tlc-scaling.json` (TLC scaling campaign, workstation) and three `tlc-scaling-base-*-k2-m2.json` (cluster rows marked †); `summary.json` |
| `evidence/results/processed/tse/tlc-extended.json` | first TLC campaign (14 baselines, 27 mutant runs, 2 nonvacuity runs) |
| `evidence/results/processed/tse/graph.json` | differential test of the generic kernel against the reference controller (§6.4) |
| `evidence/results/processed/document-service-v1/` | one-job TLC campaign, reachability witnesses, TLAPS records, trace validation, regression tests, policy enumeration |
| `evidence/results/raw/2026*-{models,mutations,witnesses,proofs,tests,case-study,conformance}-*/` | the seven raw runs behind `document-service-v1`, with TLC/TLAPS logs, scenario traces and the corrupted traces |
| `evidence/tlc-logs/workstation/` | console summaries of the scaling campaign (`campaign.log`) and its mutant runs (`mut.log`) |
| `evidence/tlc-logs/cluster/` | Slurm outputs of the three cluster TLC jobs (see §7 for the `mde5` job) |
| `SHA256SUMS` | checksums of `evidence/`, `generated/` and `claims.csv` (`sha256sum -c SHA256SUMS`) |

Everything under `evidence/` except `tlc-logs/` is also tracked in the repository. It is copied here so that this
directory is self-contained. The TLC logs come from git-ignored directories (`tmp/`, `hpc/fetched/`). TLC state
databases (about 1 GB) are not included, because TLC regenerates them. Size: about 24 MB.

---

## 3. Approach → code

The case study runs the **case-study kernel** [`experiments/sosym/kernel.py`](../../../../experiments/sosym/kernel.py).
It extends the differentially tested generic kernel [`src/vgc/graph.py`](../../../../src/vgc/graph.py) with projections,
context selectors and owners. The trace-validated **reference controller** is
[`src/vgc/controller.py`](../../../../src/vgc/controller.py).

| Paper element | Implementation |
|---|---|
| Workflow model of the case study (Fig. 4): 13 jobs, read queries, projections, context selector, contracts, owners | [`mde_case.py`](../../../../experiments/sosym/mde_case.py) `make_jobs()` (l. 356); `Job` in `kernel.py` (l. 43) |
| Inputs X: requirements, conventions, shared context; changes E1–E7; feedback epoch | `mde_case.py` `base_requirements()`, `initial_state()`, `_e1()`…`_e7()`, `feedback_epoch()` (l. 73–176) |
| Observation o_j and key κ_j = enc(o_j), Eq. (1) | `kernel.py` `Kernel.full_observation()` (l. 115), `observation()`, `key_of()`, `canonical()` (l. 38) |
| Controller state: records B_j, requests, history (Sent), nonce, revision (§3.4) | `kernel.py` `Record` (l. 56), `Request` (l. 68), `Kernel.__init__` |
| Usable / stale / inactive, the upstream gate, Eqs. (2)–(4) | `Kernel.usable()` (l. 107); gate = `full_observation(gate=True)`; `eligible()` |
| Reconciliation R with new episodes, early cutoff and cancellation, Eq. (5) | `Kernel._reconcile()` (l. 154) |
| Edit / Reconf | `Kernel.edit()` (l. 183); in the driver `mde_case.apply()` |
| Dispatch (fresh request identity, budget k) | `Kernel.dispatch()` (l. 200) |
| Accept / Reject / Timeout / Discard: commit guard (1)–(5), validation on the immutable u.o, recheck | `Kernel.resolve()` (l. 222), `Kernel._current()` (l. 214) |
| Publish, Eq. (6): no inactive, stale or pending view, and G | `Kernel.publishable()` (l. 266); G = `mde_case.global_predicate()` (l. 334) |
| Validators V_j (§7.1, "Validators") | `mde_case.py` `validate_cls`, `validate_ocl` (grid equivalence), `validate_sm`, `validate_api`, `validate_test` (l. 191–333) |
| Five coordination disciplines + view-level dependencies (§7.1) | `kernel.py` `STRATEGIES`; differences in `usable()`, `observation()`, `key_of()`, `_current()`, `resolve()` (module docstring explains each) |
| Deferred structural checks, rules (a) and (b) (§3.6) | reference controller: `controller.py` `_check_structure()`, `_candidate()`/`_install()`, `_reconcile()` |
| Algorithm 1 (topological repair) | `src/vgc/scheduler.py` `repair()`; generic kernel `src/vgc/graph.py` `repair()` |
| Finite behavioral models (App. A) | `specification/DocumentPolicy.tla`, `proofs/DocumentPolicyProofs.tla`; exhaustive enumeration = scenario S28 of `experiments/scenarios.py` (`case-study` stage) |

---

## 4. Theorems → evidence (Table `evidence` of the manuscript)

| Result | Paper proof | Machine evidence | Where the evidence is |
|---|---|---|---|
| Lem. 1 request currency | §4.1 | TLC: (iv), (0) in `Inv`; executable monitor (`L1 request currency`) | `specification/Core.tla` `HistoryShape`, `RequestBudget`; `run_case.py` `monitor()` (l. 51) |
| Thm. 2 safety (S1–S6) | §4.1 | TLC `Inv` on 14 + 11 baselines; TLAPS `ControllerSafety` (the Accept step of S4) and `Budget`; monitor in every case-study run | `Core.tla` `Inv`, `Provenance`, `CurrentValidity`, `CommitSafety`, `PublicationSafety`; `evidence/results/processed/{tse/tlc-extended.json, sosym/tlc-scaling*.json}`; `proofs/ControllerSafety.tla`, `proofs/Budget.tla` |
| Thm. 3 forward simulation | §4.2 | TLC checks `AtomicRefinement` on every baseline; two nonvacuity runs (`refine-obsolete-both-*`) fail as expected | `specification/AtomicController.tla`, `Refinement.tla` (`Alpha`); `models/extended/refine-*.cfg`, `models/sosym/refine-*.cfg` |
| Thm. 4 necessity (Table `necessity`) | §4.3 | 9 TLC guard mutants × 3 topologies (first campaign) + ×1 on `s_mde5` (scaling); regression test for fresh identities; case study (rows C) | `models/mutants/`, `models/extended/mut-*.cfg`, `models/sosym/mut-*.cfg`; App. B; `tests/test_transactions.py::test_deletion_recreation_does_not_reauthorize_old_request` |
| Lem. 5 exact invalidation, Thm. 6 single-episode repair | §5.1 | case study: `dispatch_bound_ok` and `max_episodes_per_view_and_revision` per run | `evidence/results/raw/sosym/sim/runs.json`; macros `\SimBoundOk`, `\SimUngatedMaxEp` |
| Prop. 7 separation without the gate | §5.1 | case study, discipline `ungated` (w = 3 at `api/Loan`) | same file, `strategy == "ungated"` |
| Prop. 8, Lem. 9, Thm. 10 terminal outcome | §5.2 | one frozen two-job liveness instance in TLC; Algorithm 1 in the reference controller | `models/core/*frozen*.cfg`, `AsyncController.tla` `LiveSpec`, `Termination`; `src/vgc/scheduler.py` |
| Thm. 11 reconfiguration | §5.3 | TLC (Reconfigure action); trace validation of scenarios that reconfigure | `AsyncController.tla` `Reconfigure`; `case-study/document-service/scenarios/campaign.json` |
| Thm. 12 sound table generation | App. A | TLAPS `DocumentPolicyProofs` (6 obligations); 8,192 tables and 1,093 event words enumerated (scenario S28) | `proofs/DocumentPolicyProofs.tla`; `document-service-v1/detailed-results.json` → `policy_metrics` |

**What is not machine-checked:** the parameterized inductive invariant and refinement (§6.3 names the three TLAPS
obstacles), (S1) and the necessity rows marked P, and early cutoff through projections in TLA+. See the manuscript's
Limitations paragraph and [`proofs/README.md`](../../../../proofs/README.md). `proofs/proof-status.json` records
`central_gate: incomplete` and lists the remaining obligations.

---

## 5. Mechanization (§6)

### TLA+ modules (186 non-blank, non-comment lines in the four protocol modules)

| Module | Role |
|---|---|
| [`specification/Core.tla`](../../../../specification/Core.tla) | jobs 1..J, `Obs`, recursive `Usable` (upstream gate), `Reconcile` with cancellation, invariant `Inv`; Boolean constants that disable guards (mutants) |
| [`specification/AsyncController.tla`](../../../../specification/AsyncController.tla) | `EditSource`, `UpdateContext`, `Reconfigure`, `Lifecycle`, `Dispatch`, `ResolveAccepted`, `ResolveRejected`, `Timeout`, `DiscardObsoleteOrDuplicate`, `Publish`; targeted properties `CurrentCommit`, `ContractCommit`, `ContextCommit`, `AuthorityCommit`, `BudgetSafety`, `SuspensionPublication`, `RevisionPublication`; witnesses; `LiveSpec`/`Termination` |
| [`specification/AtomicController.tla`](../../../../specification/AtomicController.tla) | the atomic specification A (Table `abstract`) |
| [`specification/Refinement.tla`](../../../../specification/Refinement.tla) | refinement mapping α (`Alpha`) and property `AtomicRefinement` |
| `StructuralKernel.tla`, `DocumentPolicy.tla`, `CaseStudy.tla` | constant modules for the TLAPS lemmas and App. A |

### Model-checking campaigns

| Campaign | Configurations | Driver | Evidence | Paper |
|---|---|---|---|---|
| one-job campaign (23 runs) | `models/smoke/`, `models/core/`, `models/mutants/`, `models/Model_*.tla` | `python3 scripts/reproduce.py models|mutations|witnesses` | `document-service-v1/detailed-results.json` → `models`, `mutations`, `witnesses`; raw runs `20261121T1717*` | §6.2 |
| first campaign (43 runs) | `models/extended/*.cfg`, `models/Model_x_*.tla` | `python3 scripts/run_models_extended.py` | `results/processed/tse/tlc-extended.json` | §6.2, App. B, Table `tlc` |
| scaling campaign (11 baselines, 9 mutants, 1 nonvacuity) | `models/sosym/*.cfg`, `models/Model_s_*.tla` | `python3 scripts/run_models_sosym.py --workers 16 --heap 90`; the † rows through `hpc/slurm/vgc_tlc.sbatch` with `--only base-s_<topology>-k2-m2 --workers 62` | `results/processed/sosym/tlc-scaling*.json`; `./evidence/tlc-logs/` | §6.2, Table `tlc-scaling` |

Mutant ↔ Core constant: `no-cancel` = `CancelObsolete=FALSE`; `no-recheck` = `RecheckCurrent=FALSE`; `obsolete-both` =
both; `budget-reset` = `ResetBudget`; `contract-omitted` = `IgnoreContract`; `membership-omitted` = `IgnoreContext`;
`publish-suspended` = `IgnoreSuspension`; `revoked-authority` = `IgnoreAuthority`; `stale-publication` =
`StalePublication`. TLC: `TLC2 Version 2026.11.19.180144 (rev: bc1b506)`, `tla2tools.jar` SHA-256 `fdffef24…6713`
(recorded in every TLC result file). It needs Java 17 and the jar in `.tools/` (`python3 scripts/bootstrap_tools.py`).
`run_models_sosym.py` writes the configurations of the three cluster instances when it runs them. These are not all
present in `models/sosym/` beforehand.

### TLAPS (25 obligations)

`proofs/Budget.tla` (8), `ControllerSafety.tla` (2), `StructuralKernelProofs.tla` (9), `DocumentPolicyProofs.tla` (6).
Toolchain: [`environment/toolchain.lock.json`](../../../../environment/toolchain.lock.json) (TLAPS 1.6.0-pre, Z3
4.8.9) and [`environment/Dockerfile.proofs`](../../../../environment/Dockerfile.proofs). Run:
`python3 scripts/reproduce.py proofs` (strict mode, `--cleanfp`). The recorded run is
`evidence/results/raw/20261027T014850-proofs-3137953d/`, with per-module logs, commands and obligation counts.

### Trace validation and differential testing (§6.4)

| Claim | Code | Driver | Evidence |
|---|---|---|---|
| 28 scripted scenarios admitted by an independent trace checker | `experiments/scenarios.py`, `case-study/document-service/`; checker [`verification/trace_conformance.py`](../../../../verification/trace_conformance.py) (does not import the controller) | `python3 scripts/reproduce.py case-study` then `conformance` | raw runs `20261121T165119-case-study-*`, `20261121T165120-conformance-*` (traces, verdicts) |
| 9 corrupted traces rejected | `trace_conformance.py` | `conformance` stage | `detailed-results.json` → `conformance.corruptions` |
| 14 regression tests | [`tests/test_transactions.py`](../../../../tests/test_transactions.py) | `python3 -m unittest discover -s tests` | raw run `20261121T165119-tests-*` |
| generic kernel ≡ reference controller on 150 streams / 6,000 changes | `src/vgc/graph.py` vs. `src/vgc/controller.py` | `python3 experiments/graph_experiments.py` (`differential`) | `results/processed/tse/graph.json` → `differential` |

The case-study kernel was **not** differentially tested (§6.4 says so). It is checked at every step of every run by the
monitor `run_case.py: monitor()`.

---

## 6. Case study (§7): research question → experiment → evidence → paper

All commands need Python 3.12 (3.10+ works) and `scipy`. Times are for one workstation core.

| RQ | What is measured | Command | Evidence | Paper |
|---|---|---|---|---|
| **RQ1**, **RQ3** | 5 disciplines × 500 seeds, asynchronous (latency, duplicates, losses, mid-flight changes), simulated agents; oracle on every quiescent snapshot; monitor at every step | `python3 experiments/sosym/run_case.py sim --runs 500` (~25 s) | `evidence/results/raw/sosym/sim/runs.json` | Table `sim`, Table `perchange` (left), RQ1 and RQ3 prose |
| **RQ2** | views that start a stale episode per change, 6 disciplines × 200 seeds, correct agents, reliable delivery | `run_case.py impact --runs 200` (~13 s) | `.../impact/runs.json` | Table `impact` |
| sensitivity | 10 cells (p_mid, p_err, k) × 100 seeds × 4 disciplines | `run_case.py sweep --runs 100` (~21 s) | `.../sweep/runs.json` | Table `sweep` |
| RQ2 cost | requests per run, bootstrap CI, Wilcoxon | (from `sim`) | `sim/runs.json` → `metrics.dispatched` | RQ2 prose, `\SimFullRatio` etc. |
| **RQ4** | 8 open models × 10 repetitions × 5 disciplines; 4,549 distinct model calls | `run_case.py llm --model <m> --reps 10` (needs Ollama), or replay: `run_case.py llm --model <m> --reps 10 --cache-only --cache-from results/raw/sosym --out /tmp/replay` | `.../llm/<model>/{runs.json,cache.jsonl}`, `.../llm-replay/` | Table `llm`, Table `perchange` (right), RQ4 prose |
| all of the above | aggregation, CIs, tests, LaTeX | `python3 experiments/sosym/summarize.py` (writes the `%% GENERATED` blocks of `main.tex`) | `results/processed/sosym/summary.json` | all generated macros and tables |

Seeds: run *i* uses schedule seed *i* and agent seed 10000+*i* (`sim`); 50000+*i* / 20000+*i* (`impact`); 40000+*i* /
30000+*i* (`sweep`); 1000+rep (`llm`). Defaults are k = 4, p_mid = 0.6, p_err = 0.25, mean latency 1, duplicate 0.1,
loss 0.05, timeout 5. LLM settings: JSON mode, temperature 0.7, `num_predict` 1500, `num_ctx` 8192, and a seed derived
from the cache key. Full details: [`experiments/sosym/README.md`](../../../../experiments/sosym/README.md).

**Where each measurement is computed**

| Measurement (§7.1) | Code |
|---|---|
| asynchrony (latency, duplicates, losses, mid-flight changes) | `run_case.py` `run()` (l. 73) |
| simulated agents and their detectable errors | `mde_case.py` `SimulatedAgent` (l. 486), `reference_value()`, `corrupt()` |
| LLM agents: prompt rendered from u.o only, parsing, cache | `mde_case.py` `render()` (l. 500), `parse()`; `run_case.py` `LLMAgent` (l. 170) |
| monitor: S3, S3↑, S2/S4, S6, request currency | `run_case.py` `monitor()` (l. 51) |
| oracle for wrong releases | `mde_case.py` `oracle()` (l. 396) |
| attribution to E1–E7, bootstrap CI, Wilcoxon, rule of three | `summarize.py` `points_of()`, `per_change()`, `boot_ci()`, `sim_summary()` |

**Inspecting one decision.** Each line of `cache.jsonl` is one model call:

```bash
python3 - <<'EOF'
import json
p = "docs/paper/SoSyM/replication-package/evidence/results/raw/sosym/llm/phi4_14b/cache.jsonl"
for line in list(open(p))[:3]:
    c = json.loads(line)
    print(c["job"], c.get("seconds"), c["response"][:200].replace("\n", " "))
EOF
```

Each run in `runs.json` records `strategy`, `seed`/`rep`, `releases`, `wrong_releases`, `violations` (monitor counts),
`issue_views`, `metrics` (dispatched, discarded, rejected, obsolete_installed, …) and the quiescent points.

---

## 7. Provenance notes and known deviations

* **Source hashes.** Every raw file records the SHA-256 of `kernel.py`, `mde_case.py`, `run_case.py` and `summarize.py`.
  * `mde_case.py` (workflow model, validators, oracle, agents) matches the checkout in **all** raw files.
  * `kernel.py` matches in all files except the five LLM runs made on the Alliance clusters (`gemma2:9b`, `llama3.1:8b`,
    `phi4:14b` on Rorqual; `mistral-small:24b`, `qwen2.5-coder:7b` on Narval). They used an earlier kernel revision
    (`9632adfa…`).
  * `run_case.py` (the driver) changed during the campaign. Only `sim/runs.json` was produced by the committed driver.
* **Why the deviations do not matter.** `llm-replay/` re-runs all eight models from the cached calls with the current
  kernel. It has zero cache misses and is identical run for run to `llm/` in releases, wrong releases, monitor violations
  and request counts (checked by `verify.py`, step 4). With `--rerun`, `verify.py` re-executes `sim`, `impact` and `sweep`
  with the committed code and obtains files identical to the recorded ones. `summarize.py` changed after the runs. Its
  current version regenerates every number (step 1).
* **Largest TLC instance (`mde5`, k = m = 2, 42,035,622 states).** The fetched Slurm output
  `evidence/tlc-logs/cluster/vgc-tlc-mde5-k2-m2-27408175.out` holds only its header, and its 64-CPU job header differs
  from the `host_cpus: 192` recorded in `tlc-scaling-base-s_mde5-k2-m2.json`. The result file, not that log, is the
  evidence for this row: status `passed`, 62 workers, 12,480 s. The other two cluster rows have complete logs.
* **Excluded model.** `deepseek-coder-v2:16b` has a cache (14 calls, 74 s to 14 min each) but no completed repetition.
  `summarize.py` reports it separately (`\LlmExcludedCalls`) and does not tabulate it (§7.2, RQ4).
* **Machine-specific fields.** Manifests and TLC/TLAPS records contain host names and absolute paths of the machines that
  produced them. They are kept unchanged so that the recorded SHA-256 values stay valid.

---

## 8. Repository map

| Directory | Role | Used by this paper |
|---|---|---|
| `specification/` | TLA+ modules (§5) | yes: §6 |
| `models/` | TLC model modules and configurations: `smoke/`, `core/`, `mutants/` (one-job), `extended/` (first campaign), `sosym/` (scaling) | yes: §6.2 |
| `proofs/` | TLAPS modules, `proof-status.json`, `README.md` | yes: §6.3 |
| `experiments/sosym/` | case-study kernel, workflow model and validators, driver and monitor, generator | yes: §7 |
| `src/vgc/` | reference controller, generic kernel, scheduler, validators, structural normalizer | yes: §6.4, App. A |
| `verification/trace_conformance.py`, `tests/`, `case-study/document-service/`, `experiments/scenarios.py` | trace checker, regression tests, scripted scenarios | yes: §6.4 |
| `experiments/graph_experiments.py` | differential test (`differential`) | yes: §6.4 (only that part) |
| `scripts/` | `reproduce.py` (stages doctor…proofs…conformance), `run_models_extended.py`, `run_models_sosym.py`, `run_proofs.py`, `bootstrap_tools.py` | yes |
| `hpc/slurm/vgc_tlc.sbatch`, `vgc_llm.sbatch` | cluster job scripts for TLC † rows and LLM runs | yes |
| `environment/` | TLAPS toolchain lock file and Dockerfile | yes: §6.3 |
| `results/raw/sosym/`, `results/processed/sosym/` | case study and scaling campaign data (copied in `./evidence/`) | yes |
| `experiments/llm*`, `experiments/bench`, `benchmark_study.py`, `scientific_campaign.py`, `data/benchmarks/` | LLM code-generation workflows | **no**: these belong to the companion empirical article (JSS). This paper makes no claim that rests on them. |

---

## 9. Numbers that are not checked automatically

`verify.py` checks every macro, every generated table row, Appendix B and the prose numbers listed in §1. The following
are fixed by the design or quoted from the configuration rather than measured. They can be read directly in the code:

* the case-study design (4 entities, 13 views, 3 agents, 7 changes, k = 4, latency, duplicate and loss probabilities,
  timeout 5, grid of ten values per attribute): `mde_case.py`, `run_case.py` argument defaults;
* state-machine sizes "three to five states, three or four events" (App. A): `mde_case.base_requirements()` and `_e3()`/`_e7()`;
* "9 mutants", "chains of two and three jobs and the diamond", worker and heap settings: `scripts/run_models_extended.py`,
  `run_models_sosym.py` (`MUTANTS`, `TOPOLOGIES`) and the headers of the TLC result files;
* the RQ4 qualitative observations (an `other` event added by `phi4:14b`, tests calling events instead of operations,
  miscomputed expected codes): the `sm/` and `test/` replies in the models' `cache.jsonl`. The `phi4:14b` count is the
  macro `\LlmOtherCalls`, which is checked.
