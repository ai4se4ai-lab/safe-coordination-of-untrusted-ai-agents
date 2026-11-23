# Safe coordination of untrusted AI agents

## What this project is

Multi-agent LLM frameworks split software development among agents that write
requirements, designs, code and tests. Each answer can look valid while the
workflow as a whole still goes wrong: a slow agent answers a question that has
since changed, two valid outputs disagree on an interface, or a reviewer added
late is skipped. These are coordination failures, and better prompting does not
remove them.

This project treats every agent, and every language model behind it, as
**untrusted**. Agents only **propose** primitive values. A small, deterministic
controller owns artifact structure, dependency tracking and publication, and it
decides what is accepted.

### Core ideas

- **Observation and dependency key.** Each generated attribute (a design, a
  function, a test suite, a model view) is the answer to an explicit question.
  The question is its *observation*: the source footprint it reads, the shared
  context selected for it, the upstream values it depends on and its generation
  contract. A canonical encoding of the observation is the attribute's
  **exact dependency signature** (key).
- **Requests are bound to the question they were asked.** Each dispatch gets a
  fresh request identity and records the key it was asked under. When a reply
  arrives, the controller accepts it only if the request is still active, the key
  still matches the current observation, the agent is authorized and the
  validator accepts it. Late, duplicate and obsolete replies are discarded.
- **Exact invalidation with early cutoff.** A change invalidates exactly the
  attributes whose key changes. If a regenerated value equals the old one,
  invalidation stops there instead of spreading downstream.
- **Upstream gate.** A job is dispatched only when all its inputs are usable, so
  repair proceeds in topological order and each attribute is regenerated at most
  once per change (one dependency episode).
- **Bounded attempts.** Each dependency episode has a generation budget *k*. A job
  that exhausts it is suspended instead of retried forever.
- **Consistent publication.** A snapshot is published only if no attribute is
  inactive, stale or pending and a global predicate *G* holds across all of them.

Together these give a guarded transition system that:

- accepts a proposal only if it answers the *current* question;
- invalidates exactly the work a change affects;
- bounds generation attempts per dependency episode;
- publishes only globally consistent snapshots.

### What the repository contains

1. **TLA+ specifications** of the protocol: an asynchronous controller, an atomic
   abstract controller and a refinement mapping between them. They come with
   scoped TLAPS proofs and bounded TLC model checking, including seeded guard
   mutants and reachability witnesses ([specification/](specification/), [proofs/](proofs/), [models/](models/)).
2. **A Python reference controller** with no dependencies outside the standard
   library, plus a smaller generic graph kernel that is differentially tested
   against it ([src/vgc/](src/vgc/)).
3. **An independent trace-conformance oracle** that replays the controller's
   transition logs without importing the controller ([verification/](verification/)).
4. **Scripted evaluations**: a document-service case study with 28 pre-registered
   scenarios, randomized adversarial guard-ablation campaigns and
   invalidation-cost experiments ([case-study/](case-study/), [experiments/](experiments/)).
5. **A model-driven case study**: a 13-view library-system model (requirements,
   class diagrams, OCL constraints, state machines, API and tests) built by
   simulated and real LLM agents under five coordination disciplines
   ([experiments/sosym/](experiments/sosym/)).
6. **Studies with real LLMs** served by Ollama: coordinating design, code and
   tests, and the HumanEval+ and MBPP+ benchmarks. Every model call is logged
   ([experiments/llm/](experiments/llm/), [experiments/benchmark_study.py](experiments/benchmark_study.py)).

The formal and scripted parts call **no language model**. Their proposals come
from scripted or adversarial providers ([src/vgc/providers/scripted.py](src/vgc/providers/scripted.py)),
so their numbers are deterministic functions of recorded seeds and fixtures and
need no API keys, credentials or network access (apart from the one-time tool
download). The LLM studies need a model server, but every recorded call is stored,
so their results can be checked, and the model-driven case study can be replayed,
without one.

### Main findings

- **Every guard is needed.** Across 3,600 randomized adversarial runs, the reference
  controller shows no safety violation. Removing a guard breaks the property it
  protects in 9 of 11 variants. The other two each remove only one of the two
  obsolete-reply defenses, and the remaining defense covers for it.
- **Exact keys make change cheap.** At 32 modules, a change costs 10.8 generation
  requests on average, against 128.0 for regenerating everything (11.9×). The
  reductions against whole-workspace, version-keyed and no-cutoff strategies are
  8.1×, 3.0× and 2.3×, with identical accepted values in every run.
- **Weaker disciplines publish wrong models.** In the 13-view model-driven case
  study (500 seeded runs), exact coordination released 1,709 snapshots with none
  wrong. Data-version and last-writer-wins coordination released wrong snapshots
  58% of the time. With eight real LLMs (4,549 logged calls), exact coordination
  again released no wrong snapshot.
- **Validators are not a ground truth.** On 542 HumanEval+ and MBPP+ tasks with
  five models (14,069 calls), 12.9% of the code that passed the base tests failed
  the stronger plus tests. The controller guarantees *currency and consistency*,
  not the correctness of what a validator accepts.

### Scope of the claims

This is a research artifact. It is not a verified production system. The scoped
TLAPS lemmas pass, and TLC checks the refinement mapping on bounded instances, but
the central parameterized safety/budget invariant and the general refinement proof
are **proved only on paper**. The `proofs` stage therefore exits nonzero on
purpose (see [Expected outcomes](#expected-outcomes)). The
[claim–evidence matrix](docs/claim-evidence-matrix.csv) lists each theorem with its
level of evidence (paper proof, machine-checked, finite-checked or tested) and the
work that remains. [docs/deviations.md](docs/deviations.md) records where the
artifact departs from the original development plan.

## Repository layout

| Path | Contents |
|---|---|
| [specification/](specification/) | TLA+ modules: `Core`, `AsyncController`, `AtomicController`, `Refinement`, `StructuralKernel`, `DocumentPolicy`, `CaseStudy` |
| [proofs/](proofs/) | TLAPS proof modules and [proof-status.json](proofs/proof-status.json) (latest obligation counts) |
| [models/](models/) | TLC configurations: `smoke/`, `core/` (safety, reachability and liveness), `mutants/` (9 seeded protocol bugs), `extended/` (3–5 jobs, mutants on multi-job topologies, refinement checks), `sosym/` (scaling campaign up to 6 jobs) |
| [src/vgc/](src/vgc/) | Reference controller (`controller.py`), generic kernel (`graph.py`), observations, scheduler, structure kernel, validators, scripted providers |
| [case-study/document-service/](case-study/document-service/) | Five-stage ranked workflow, requirements, policies, fixtures and the 28 pre-registered scenarios (`scenarios/campaign.json`) |
| [verification/](verification/) | Independent trace-conformance oracle; `baseline/` holds the original user-supplied sources |
| [experiments/](experiments/) | Guard-ablation and cost campaign (`scientific_campaign.py`), generic-kernel experiments (`graph_experiments.py`), LLM study (`llm_study.py`, `llm/`), benchmark study (`benchmark_study.py`, `bench/`), model-driven case study (`sosym/`), paper-fragment generators |
| [data/benchmarks/](data/benchmarks/) | EvalPlus datasets (HumanEvalPlus v0.1.10, MbppPlus v0.2.0) |
| [tests/](tests/) | Regression tests (`unittest`) |
| [scripts/](scripts/) | `reproduce.py` (single entry point), TLC campaign drivers, tool bootstrap, packaging, clean-room verification |
| [hpc/](hpc/) | Slurm job scripts and the fleet tool for running LLM and TLC jobs on compute clusters |
| [environment/](environment/) | Pinned toolchain lock file (URLs and SHA-256) and the TLAPS proof container |
| [results/raw/](results/raw/) | One directory per run: manifest, exact command, source hashes, source snapshot, logs |
| [results/processed/](results/processed/) | Aggregated data that the manuscripts are generated from |
| [docs/paper/](docs/paper/) | The two manuscripts, each with a self-contained replication package (see [Manuscripts](#manuscripts-and-replication-packages)) |
| [docs/](docs/) | Semantics, assumptions, threat model, trusted components, toolchain provenance, reproducibility notes |

## Requirements

| Tool | Needed for | Tested version |
|---|---|---|
| Python ≥ 3.11 (standard library only) | everything | 3.12.3, 3.13 |
| `scipy` (optional) | Wilcoxon tests in the model-driven case study | — |
| Java ≥ 11 | TLC (`spec-check`, `models`, `mutations`, `witnesses`) | Amazon Corretto 11.0.16.1 |
| Docker Engine/Desktop **or** native Linux TLAPS | `proofs` | Docker 29.5.3; TLAPS 1.6.0-pre (Z3 4.8.9) |
| pdfLaTeX + BibTeX | building the manuscripts | TeX Live / MiKTeX 24.1 |
| [Ollama](https://github.com/ollama/ollama) | only for new LLM runs | — |

The scripts run on Linux and Windows and in CI on Ubuntu 24.04
([.github/workflows/](.github/workflows/)). If `java` is not on `PATH`, point
`VGC_JAVA` at the executable. The default TLC runs use one worker and a 768 MB
heap, so an ordinary laptop is enough. The larger scaling instances were run
with more workers on a workstation and on a cluster.

Tool binaries are **not** in the repository. `bootstrap_tools.py` downloads
`tla2tools.jar` and the TLAPS archive into `.tools/` and checks every byte against
[environment/toolchain.lock.json](environment/toolchain.lock.json). If an upstream
asset has changed, it refuses to continue. [docs/toolchain.md](docs/toolchain.md)
gives the provenance of each tool.

## Quick start (about 5 minutes, Python only)

```text
git clone https://github.com/ai4se4ai-lab/safe-coordination-of-untrusted-ai-agents
cd safe-coordination-of-untrusted-ai-agents
python scripts/reproduce.py tests          # 14 regression tests
python scripts/reproduce.py case-study     # 28 scenarios, records traces
python scripts/reproduce.py conformance    # independent oracle replays those traces
python experiments/scientific_campaign.py --quick   # small guard-ablation/cost smoke run
```

Each `reproduce.py` command prints the run directory it created and `passed` or
`failed`.

## Reproducing the results

Every `reproduce.py` stage writes `results/raw/<UTC timestamp>-<stage>-<id>/`
containing `manifest.json` (command, commit, git status, OS, Python, SHA-256 of
every source file), `sources.zip` (a snapshot of those sources), `results.json`
and the raw tool logs. The committed runs are already in
[results/raw/](results/raw/), so you can compare against them.

### 1. Set up tools

```text
python scripts/bootstrap_tools.py
docker build -f environment/Dockerfile.proofs -t vgc-tlaps:local .   # proofs only
python scripts/reproduce.py doctor          # reports which tools were found
```

The proof container pins its Debian base image by digest and pins package
versions. TLAPS needs glibc ≥ 2.38, which some hosts (including Docker Desktop's
internal distribution) lack, which is why the container is provided.

### 2. Formal and scripted stages

| What | Command | Approx. time |
|---|---|---|
| Specs parse (SANY) | `python scripts/reproduce.py spec-check` | < 1 min |
| Bounded model checking, one job | `python scripts/reproduce.py models --profile core` | ~1 min |
| Seeded mutants are caught | `python scripts/reproduce.py mutations` | ~1 min |
| Reachability witnesses | `python scripts/reproduce.py witnesses` | ~1 min |
| Scoped TLAPS lemmas | `python scripts/reproduce.py proofs --timeout 90` | ~1 min |
| Regression tests | `python scripts/reproduce.py tests` | < 1 min |
| Scenario campaign | `python scripts/reproduce.py case-study` | < 1 min |
| Independent trace conformance | `python scripts/reproduce.py conformance` | < 1 min |
| Aggregate the latest run of each stage | `python scripts/reproduce.py analyze` | < 1 min |
| Guard ablation and invalidation cost | `python scripts/reproduce.py tse-campaign` (or `python experiments/scientific_campaign.py`) | ~10–30 min |
| Generic kernel: differential test, coupled workspaces, gated vs. ungated scheduling | `python experiments/graph_experiments.py` | ~30 min |
| Multi-job TLC, mutants on multi-job topologies, checked refinement mapping | `python scripts/run_models_extended.py` | hours |
| TLC scaling campaign (up to 6 jobs, 42 M states) | `python scripts/run_models_sosym.py` | hours (multi-core) |

`python scripts/reproduce.py all --profile core` runs every formal and scenario
stage in sequence (doctor → baseline → spec-check → proofs → models → mutations →
witnesses → tests → case-study → conformance → analyze → claims → paper →
package) and prints a JSON summary of exit codes. It does **not** include the
campaigns in the last four rows of the table.

### 3. Model-driven case study

```text
python experiments/sosym/run_case.py sim    --runs 500   # consistency and cost   (~25 s)
python experiments/sosym/run_case.py impact --runs 200   # per-change impact      (~13 s)
python experiments/sosym/run_case.py sweep  --runs 100   # sensitivity            (~21 s)
python experiments/sosym/summarize.py                    # tables and numbers
```

The LLM part can be replayed from the recorded calls without a model server; see
[experiments/sosym/README.md](experiments/sosym/README.md).

### 4. Studies with real LLMs

| Study | Command | Output |
|---|---|---|
| LLM agents coordinating design, code and tests | `python experiments/llm_study.py --part all --models <m>` | `results/raw/*-llm-all/` (every call logged) |
| HumanEval+ and MBPP+ | `python experiments/benchmark_study.py --benchmark humaneval --model <m>` | per-run `results-*.json`, `calls-*.jsonl` |

These need an Ollama server (`VGC_OLLAMA` or `--host`). Generated code runs only
in a separate, resource-limited interpreter
([experiments/llm/sandbox_runner.py](experiments/llm/sandbox_runner.py),
[experiments/bench/sandbox_bench.py](experiments/bench/sandbox_bench.py)).

### 5. Running on a cluster

[hpc/](hpc/) runs the LLM and TLC jobs on Slurm clusters (the configured sites are
in `hpc/config/clusters.json`):

```text
bash hpc/scripts/ssh-session.sh connect <site>      # interactive MFA once; socket in hpc/.ssh
python3 hpc/scripts/fleet.py probe   --sites <site>
python3 hpc/scripts/fleet.py setup   --sites <site>   # copy Ollama runtime + models into the work directory
python3 hpc/scripts/fleet.py deploy  --sites <site>   # rsync src/, experiments/, data/
python3 hpc/scripts/fleet.py submit --site <site> --model qwen2.5-coder:7b --study benchmark \
        --args="--benchmark;humaneval;--limit;12" --tag smoke --time 0:30:00
python3 hpc/scripts/fleet.py status
python3 hpc/scripts/fleet.py fetch                    # -> hpc/fetched/<site>/
```

Each job starts a node-local Ollama server on one GPU and refuses to run unless the
model is fully GPU-resident.

### How the numbers reach the manuscripts

No evaluation number is typed into the manuscripts by hand. Generators read
`results/processed/` and write the tables, figures and number macros:

- `experiments/scientific_paper.py` and `experiments/revision_paper.py` produce the
  fragments for the empirical study (with `provenance*.json` holding the SHA-256 of
  every input, generator and output);
- `experiments/sosym/summarize.py` rewrites the blocks marked
  `%% BEGIN GENERATED ...` in the model-driven manuscript.

`analyze` always selects the **most recent** run of each stage and keeps failed
cases in the denominator. Older runs remain in `results/raw/` but are not mixed in.
If you change a source file, rerun the affected stages before `analyze`.

### Expected outcomes

| Quantity | Value |
|---|---|
| Guard ablation: randomized runs (300 seeds × 12 controllers, 120 steps each) | 3,600 |
| Guard ablation: safety violations in the reference controller | 0 |
| Guard ablation: variants that violate their targeted property | 9 of 11 (removing either obsolete-reply defense alone is masked by the other) |
| One-job TLC: mutants caught / baselines with no violation | 7 of 9 / 9 |
| Scaling TLC: baselines passed / mutants caught | 11 / 9 of 9 |
| Requests per change at N = 32, exact vs. full regeneration | 10.8 vs. 128.0 (11.9×) |
| Reduction vs. whole-workspace / version-keyed / no-cutoff strategies | 8.1× / 3.0× / 2.3× |
| Accepted values identical across strategies | all runs |
| Scenarios passed | 28 of 28 |
| TLAPS obligations proved (scoped lemmas) | 25 |
| Regression tests | 14 |

**What should match exactly:** all counts, verdicts and ratios of the scripted
and simulated campaigns. They are deterministic given the seeds, and TLC state
counts are fixed for the same sources and configuration.
**What will differ:** wall-clock timings, TLC fingerprint randomization, PDF bytes
and the output of new (not replayed) LLM runs.

**Nonzero exit codes that are expected:**

- `proofs` exits nonzero even when every scoped lemma passes, because the central
  obligations are still open. Finite TLC results never satisfy this gate.
- `baseline` reports `inconclusive` because some of the original historical
  materials were never supplied.
- `all` therefore exits nonzero. Read its JSON summary: every other stage should
  report `0`.

## Clean-room reproduction

To check that the artifact works outside this checkout:

```text
python scripts/reproduce.py package   # writes dist/vgc-artifact-0.1.0.zip + checksums
python scripts/verify_package.py      # extracts to a fresh directory, downloads pinned
                                      # tools, reruns the pipeline, compares outcomes
```

`verify_package.py` writes `dist/clean-reproduction.json`, which includes the hash
of the archive it tested, and leaves the fresh directory in place for inspection.
The archive contains no `.git`, credentials, virtual environments, tool binaries
or TLC state databases. See [docs/reproducibility.md](docs/reproducibility.md) for
details.

## Further documentation

- [docs/semantics.md](docs/semantics.md): the coordination semantics
- [docs/assumptions.md](docs/assumptions.md) and [docs/threat-model.md](docs/threat-model.md):
  what is assumed about agents, the environment and the attacker
- [docs/trusted-components.md](docs/trusted-components.md): the trusted computing base
- [specification/README.md](specification/README.md) and [proofs/README.md](proofs/README.md):
  what the TLA+ model and the proofs cover and what they don't
- [case-study/document-service/README.md](case-study/document-service/README.md):
  the document-service workflow
- [experiments/README.md](experiments/README.md): campaign protocol and the
  statistical interpretation of results (deterministic fixtures, not samples)
- [experiments/sosym/README.md](experiments/sosym/README.md): the model-driven
  case study, seeds, defaults and LLM replay

## Citation

If you use this artifact, please cite the accompanying manuscripts.
Machine-readable metadata is in [CITATION.cff](CITATION.cff).

## License

Code and documentation: MIT ([LICENSE](LICENSE)). Publisher class and style files
under `docs/paper/` are included unchanged and remain under their publishers' terms.
