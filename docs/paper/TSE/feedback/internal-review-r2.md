# Internal pre-submission review (revision R1, round 2)

Four simulated TSE reviewers assessed the revised manuscript (29 pages, built 2026-11-21) against the
TSE criteria: novelty, rigor, relevance, verifiability and transparency, and presentation. Each
reviewer took a different angle. Every finding was checked against the manuscript and the data before
being recorded. The last section tracks how each finding was resolved.

Scores: 1 = poor, 5 = excellent.

---

## Reviewer A: multi-agent coordination and agent-oriented SE

| Novelty | Rigor | Relevance | Verifiability | Presentation |
|---|---|---|---|---|
| 3 | 4 | 3 | 4 | 2 |

**Summary.** The revision now places the controller explicitly in the line of A&A, tuple centres,
information protocols and institutions, and the new positioning table is useful. The contribution is
best read as a careful *combination* of known mechanisms for a new kind of participant.

**Major**

- **A1.** The introduction still motivates the work only from classical MAS and 2023-era LLM frameworks.
  - The closest work is the 2025–2026 line on transactions and concurrency control for LLM agents (Yang
    et al., ICML 2026; SagaLLM; CoAgent; PlanFence). It appears only in §IX.
  - A reader of §I cannot tell what the paper adds beyond "OCC for agents".
  - *Request:* say this in §I, in one paragraph, with the differentiator.
- **A2.** Contribution 2 lists nine results in one sentence. Several of them (structural integrity, exact
  invalidation) hold by construction, as §VI itself says.
  - *Request:* separate the results that carry the argument (safety relative to observations,
    single-episode repair, terminal outcome, refinement) from the bookkeeping lemmas.
- **A3.** In RQ5 the cross-service barrier never fires with real models. The "local validity, global
  conflict" failure (F2) is therefore motivated in §I but never observed with LLMs.
  - The discussion admits this. The introduction and abstract should not imply otherwise.

**Minor**

- **A4.** The term "institutional governor" is used in §I before institutions are explained (§II-B).

---

## Reviewer B: formal methods and verification

| Novelty | Rigor | Relevance | Verifiability | Presentation |
|---|---|---|---|---|
| 3 | 3 | 3 | 4 | 2 |

**Major**

- **B1.** Fig. 5, the control automaton, is hard to read.
  - The edge labels "reject / timeout, n<k", "n=k" and "a=σ' (cutoff)" overlap each other and cross
    edges.
  - Two edges into Dirty have no clear source.
  - The automaton is the only picture of the per-job semantics, so it has to be unambiguous.
- **B2.** Fig. 2 is a verbatim code listing whose lines wrap mid-token ("endpoint:put)", "409"},").
  - It is the first concrete instance of the key concepts (match key, target, read set, observation,
    key, request, record), yet it is the hardest figure to read.
  - *Request:* present it as a structured table.
- **B3.** The abstract claims "we prove … and we delimit each result with a counterexample", but
  Table VII shows that most results are proved on paper only.
  - The abstract should say what is machine-checked (bounded TLC, including the refinement) and what is
    not (the parameterized invariant).
- **B4.** TLAPS was not re-run on the final toolchain because of a hash-pin mismatch (README). The
  obligation counts in RQ4 must be labeled with the TLAPS version that produced them.

**Minor**

- **B5.** §IV opens with Table III (state) before the reader has seen the transition rules.
  - A one-sentence roadmap would help.
- **B6.** Remark on P=∅ is fine. Proposition 11 (feedback epochs) states a bound whose policy
  assumption is not tested by any RQ5 run (no conflicts occurred).

---

## Reviewer C: empirical SE and LLM evaluation

| Novelty | Rigor | Relevance | Verifiability | Presentation |
|---|---|---|---|---|
| 3 | 2 | 4 | 4 | 2 |

**Major**

- **C1.** §VII-G and §VII-H (RQ5, RQ6) consist of the word "Pending".
  - The abstract and discussion already cite their numbers. The paper cannot be assessed without them.
- **C2.** The proportions in RQ5 and RQ6 have no uncertainty.
  - Examples: 47 of 47 old-valid late replies wrong; 12.9% wrong among accepted.
  - With 6 trials per model in RQ5, per-model rates are anecdotal.
  - *Request:* report 95% confidence intervals for the headline proportions, and avoid between-model
    claims.
- **C3.** Design first-attempt acceptance is 0% for six of seven models.
  - The call logs show that 701 of the first-attempt design rejections have the same cause: the
    operation list.
  - The requirement text says "Updating (put)". Models answer `update`, but the validator demands the
    exact name `put`, which the design contract never states.
  - This is an underspecified contract, not a model weakness. It must be disclosed, and the
    first-attempt numbers must be interpreted as such.
  - It also shows the value of validator feedback, which repaired it.
- **C4.** The stale-reply experiment flips R03 0.5 s after dispatch, so every reply is late by design.
  - Fine as a construct. However, the abstract says "the guard discarded every reply that arrived after
    its question changed", which reads as a field observation.
  - Rephrase as a controlled experiment.
- **C5.** In the RQ5 cost runs, the exact strategy is not dominant on *outcome*.
  - For mistral-small, exact keys published after 5/8 changes and full regeneration after 7/8.
  - Fewer requests also mean fewer chances for a stochastic model to succeed.
  - This trade-off must be discussed, not hidden behind request ratios.
- **C6.** Two of seven models (qwen2.5-coder:7b, llama3.1:8b; also gemma2:9b) never published a
  workspace.
  - The paper should say clearly that the controller makes such failures explicit but cannot fix them.

**Minor**

- **C7.** RQ6 "First correct" and "Accepted & correct" mix two effects: retries and the validator.
  - Add a sentence that the difference is the contribution of validator-guided retry.

---

## Reviewer D: presentation, artifact and replication

| Novelty | Rigor | Relevance | Verifiability | Presentation |
|---|---|---|---|---|
| — | — | — | 4 | 2 |

**Major**

- **D1.** Figure quality.
  - Fig. 2: wrapped listing (see B2).
  - Fig. 5: overlapping labels (see B1).
  - Fig. 4: the annotation "only if nothing stale or pending and G holds" runs into the Editor lifeline,
    and the "discarded" label floats.
  - Fig. 3: the controller's caption text sits on top of the Commit-guard box. Arrows 4 and 8 cross the
    box row. Numbered steps are hard to follow because step 7 points upward from below.
- **D2.** The paper has 16 tables and 8 figures in 29 pages. Several tables could become supplementary
  material without loss: the scenario table, the full TLC baseline table and the glossary detail.
  - At minimum, every table must be referenced and discussed where it appears.
- **D3.** The abstract has seven numeric macros in four sentences. Two or three headline numbers would
  read better.

**Minor**

- **D4.** The README states that TLAPS needs re-pinning. The paper's data-availability statement should
  name the tag and say that the TLAPS logs are from the pinned toolchain.

---

## Meta-review

The revision answers the MAS-literature and terminology concerns of the first round. It adds
substantial new evidence: an extended TLC campaign with a checked refinement, coupled and scheduling
experiments, and two LLM studies.

It is **not ready for submission** in its current form, for three reasons:

1. The LLM sections are missing (C1).
2. The figures that carry the core concepts are hard to read (B1, B2, D1).
3. Several headline claims are stated more strongly than the data support (A3, B3, C3, C4, C5).

None of these requires new experiments. All require writing and redrawing.

---

## Resolution log

| ID | Action taken | Where |
|---|---|---|
| A1 | New paragraph "What is new relative to concurrency control for agents" in §I | §I |
| A2 | Contribution 2 rewritten: four core results named; bookkeeping lemmas grouped | §I |
| A3 | Abstract and §I say that F2 was not observed with real models; evidence is adversarial and model checking | Abstract, §I, §VII-G |
| A4 | Forward reference added | §I |
| B1 | Fig. 5 redrawn: states on a line, labels placed on separate edges, no crossings | §IV-E |
| B2 | Fig. 2 converted to a two-column table figure with the running example | §II-A |
| B3 | Abstract states which results are machine-checked | Abstract |
| B4 | RQ4 states the TLAPS version of the reported counts | §VII-F |
| B5 | Roadmap sentence at the start of §IV | §IV |
| C1 | RQ5 and RQ6 written from the data, with answers | §VII-G, §VII-H |
| C2 | Wilson 95% intervals generated for headline proportions; no between-model claims | §VII-G/H, generator |
| C3 | Contract ambiguity disclosed; first-attempt rates interpreted as contract clarity; threats updated | §VII-G, §VIII |
| C4 | Abstract and RQ5 describe the stale trials as a controlled experiment | Abstract, §VII-G |
| C5 | Cost/outcome trade-off discussed | §VII-G |
| C6 | Explicit statement on models that never published | §VII-G |
| C7 | Sentence on retry contribution | §VII-H |
| D1 | Figs. 3 and 4 re-laid out | §III |
| D2 | Coupled table condensed from 35 rows to 5; full per-change-type table and the original one-job TLC table moved to `supplement.tex` (Tables S1, S2); page count 32 → 31 | §VII, supplement |
| D3 | Abstract reduced to headline numbers | Abstract |
| D4 | TLAPS build and checksum situation stated in RQ4 | §VII-F |
