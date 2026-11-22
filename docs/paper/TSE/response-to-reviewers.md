# Response to the Associate Editor and Reviewers

**Manuscript:** *Safe Coordination of Untrusted AI Agents*, IEEE Transactions on Software Engineering, revision R1.

We thank the Associate Editor and the reviewer for their careful and constructive reports. They identified real gaps: the missing grounding in three decades of multi-agent systems (MAS) research, unnecessary private terminology, an unclear division of labor, a logical gap in the terminal-outcome theorem, under-powered model checking, and an evaluation without real language models. We took every point seriously. The revision rewrites most of the manuscript and adds four experiments with real LLMs and standard benchmarks, an extended model-checking campaign with a machine-checked refinement mapping, and a new theorem.

Throughout, *AE* refers to the Associate Editor's comments and *R-x.y* to item *y* of the reviewer's section *x*: 1 = framing and literature, 2 = formal semantics, 3 = case study and verification, 4 = evaluation. Section numbers refer to the revised manuscript. A summary of the main changes comes first, followed by point-by-point responses.

---

## Summary of main changes

| Concern | Change in the revision | Where |
|---|---|---|
| Missing MAS literature (AE; R-1.1) | New background section on artifact-mediated coordination; the controller is positioned as an A&A coordination artifact / institutional governor; a rewritten related-work section covers coordination models (Linda, tuple centres, A&A, CArtAgO/JaCaMo), dependencies (Malone & Crowston), commitments and information protocols (Singh, Yolum & Singh, BSPL, Clouseau), electronic institutions and normative MAS, MAS verification (MCMAS, MABLE, AJPF, Dastani et al.), LangGraph/MCP and TraceFix. Each subsection states what we inherit and what generated proposals add. | §I, §II-B, §III-A, §IX |
| Novelty, "reinventing the wheel" (AE) | Literature search across SE, ML/NLP, MAS, DB/PL/systems venues, plus concurrent preprints to Nov. 2026; ~50 new references, including transactional and runtime-enforcement work for LLM agents. New positioning table, "What Is Borrowed and What Is New", and an evaluation discussion that states for each theorem what the evidence adds beyond its ancestor mechanism. | §IX, Table XIX, §VII-I |
| Terminology (AE; R-1.2) | Running example moved to the start of §II, with a concrete listing of one job (match key, target, read set, observation JSON, key, request, record). New glossary maps every term to its MAS/database/build-system counterpart. Removed or replaced: "shape of the system", "intake view", "effective observation", "footprint" (now *read set*), "signature" (now *dependency key*), "stamp" (now *validated key*). The generation contract is defined once, per job, including validator environment and owner. | §II-A, Table I, Def. 1 |
| Who writes the specifications? Practical value (AE; R-1.3) | New subsection and table on the division of labor. TLA+ is written once by framework builders for the generic kernel; workflow authors write ordinary Python declarations, measured at 22 lines plus 43 lines of validators for the RQ5 workflow and 17 lines for the benchmark workflow. Scope is stated explicitly (artifact-centric, feed-forward workflows). Coordination guarantees are separated from behavioral correctness. | §I, §III-B, Table II, §X |
| Logical gap in Theorem 8 / deferred structural checks (R-2.1) | Diagnosed as a semantic flaw and fixed in the semantics and the code. Commit-time checks now cover all *configured* consumers (reviewer's option (a)), and edits invalidate instead of refusing (option (b)). New Lemma 9 ("reactivation cannot fail on committed values"); Theorem 10 and Algorithm 1 corrected. RQ1 now quantifies the hazard under the original semantics. | §IV-B, §V-E, RQ1 |
| Near-tautological theorems (R-2.3) | Exact invalidation is now a lemma; isolation and observational extension are remarks. We state explicitly which results hold by construction. **New Theorem 7 (single-episode repair):** with the upstream gate, repair cost is independent of the asynchronous interleaving; Proposition 8 shows a tight schedule-dependent lower bound without the gate, confirmed experimentally. | §V intro, §V-D |
| Formal precision (R-2.4) | Typed state table; owner part of the contract; explicit reconciliation operator ℛ (Eq. 5); retained evidence as a one-entry cache with restore rule; nonce rollback for discarded candidates; explicit refinement mapping α (Eq. 8); remark on why P=∅ is implied; Fig. 5 corrected. | §IV-D/E/F, §V-B |
| Restrictive assumptions, cycles (R-2.2) | Scope stated; new Proposition 11 (bounded feedback epochs) admits test-and-fix loops. It is exercised by the adversarial campaign; no barrier conflict arose with real models in RQ5, so no feedback epoch was triggered there. | §I, §V-F, §X |
| Circular finite-language validator (R-3.1) | Reframed explicitly as the extreme point where the validator *is* the specification. The new LLM workflows use validators that contain no solution (property-based checks against a 43-line abstract model; mutation-adequate test validators), and we measure how many distinct programs are accepted. | §VI-B, §VI-D |
| Model-checking scale; unmechanized refinement (R-3.2) | Extended TLC campaign: up to 5 jobs, environmental changes m ≤ 2, budget k ≤ 2, all nine mutants on 2-/3-job chains and a 4-job diamond, up to **718,672** distinct states (was 1,028). **The refinement mapping of Theorem 4 is now machine-checked by TLC** on all 14 baselines, and the check is shown to be non-vacuous. Technical barriers to a parameterized TLAPS proof are explained. | §VI-C, RQ4, Table XIV |
| TLAPS obligation counts; pre-fix reproduction (R-3.3) | Explained (split proof steps changed the generated obligation count from 21 to 25). All stages re-run on the revised code, and the original TLC state counts reproduce identically with the current TLC release. | RQ4 |
| No real LLMs; early cutoff and outcome equivalence (R-4.1) | **RQ5:** seven open LLMs coordinate a design → code → tests workflow (stale-reply trials, early cutoff under stochastic generation, cost with tokens and wall-clock). **RQ6:** HumanEval+ and MBPP+ with five LLMs. Outcome equivalence is restricted to deterministic providers. Key results:

- All 77 controlled late replies were rejected, and all 47 that passed their original validator were wrong for the new requirement (95% CI 92–100%).
- Exact keys used 4.0× fewer requests than full regeneration.
- 12.9% of base-test-accepted benchmark solutions failed the plus tests (95% CI 12–14%).
- Only 28% of regenerated functions were equal values, against 94% behaviorally equal. | RQ5, RQ6, Tables XV–XVIII |
| Uncoupled N-document topology (R-4.2) | The topology is now stated as independent by construction. A new coupled-workspace benchmark varies fan-out to shared data models (0–8). | RQ2, Table X |
| RQ1/RQ3 framing (R-4.3) | Reframed as mutation-based guard-necessity checks and conformance tests. | §VII-A, RQ1, RQ3 |

---

## Associate Editor

> **AE-1.** *The literature on multiagent systems and multiagent coordination is extremely rich … The article does not show any knowledge (or any recognition) of the literature … protocols, commitments, shared artifacts, dependencies and delegation … [Omicini et al. 2013; Singh 1998; Lomuscio et al. 2017; Dastani et al. 2010; Wooldridge et al. 2002].*

We agree, and we thank the editor for the starting references. The original framing presented as new several ideas that have long been studied in MAS. The revision engages this literature in four places.

1. **Introduction (§I, "Coordination is not a new problem").** The paper now opens its approach by placing the work in the MAS coordination lineage: coordination models and tuple centres, the A&A meta-model, commitment and information protocols, and electronic institutions with governors. It states that our controller *is* a coordination artifact in the A&A sense, acting as an institutional governor. It then names the three properties of LLM agents that the classical models were not designed for: generated content whose validity is relative to what the agent saw, costly nondeterministic generation that needs minimal invalidation, and opaque agents.
2. **Background (§II-B, new).** A dedicated subsection introduces objective vs. subjective coordination [Omicini et al. 2001], Linda and tuple centres [Gelernter 1985; Gelernter & Carriero 1992; Omicini & Denti 2001], A&A artifacts and environment programming [Omicini, Ricci & Viroli 2008; Weyns et al. 2007; Ricci et al. 2011; Boissier et al. 2013], commitment and information-based protocols [Singh 1998; Yolum & Singh 2002; Singh 2011 (BSPL); Chopra et al. 2020], and electronic institutions and normative MAS [Esteva et al. 2001; Arcos et al. 2005; Boella et al. 2006].
3. **Design principles (§III-A).** Each principle is now attributed to its origin: objective coordination, OCC, institutional governors, content-addressed builds.
4. **Related work (§IX, rewritten).** New subsections, "Coordination models and artifacts", "Protocols, commitments and institutions" and "Verification of multi-agent systems", state precisely what we inherit and what is new. Dependencies (Malone & Crowston), commitments and conventions (Jennings) and GPGP (Decker & Lesser) are related to our prerequisites, owned slots and atomic transactions. BSPL's keys are related to our request identities and dependency keys. Institutional governors and normative obligations are related to our commit guard and outstanding obligations. The difference we claim is narrow: classical guards decide whether an *action* is admissible *now*, while ours must also decide whether the *content* of a reply was computed from inputs that are still current. That requires recorded observations, exact dependency keys, episodes and minimal invalidation with early cutoff.

The MAS verification references (MCMAS, MABLE, Dastani et al.) are discussed under AE-3 and R-1.1 below.

**On "reinventing the wheel".** We take this point beyond the MAS literature. For the revision we searched the main venues of every community whose mechanisms the controller uses: software engineering (ICSE, FSE, ASE, ISSTA, TSE, TOSEM); machine learning and NLP (NeurIPS, ICML, ICLR, ACL); multi-agent systems (AAMAS, JAAMAS, EMAS, EUMAS); and databases, programming languages and systems (SIGMOD, VLDB, PLDI, NSDI). We also covered preprints up to November 2026, marked as concurrent work. The related-work section (§IX) now has four parts.

- **Coordination in MAS:** tuple centres, A&A, protocols, institutions, MAS verification, and the EUMAS 2025 Agent Toolkits report relating these abstractions to LLM-based agents.
- **LLM-based agents and their coordination:**
  - multi-agent SE: Self-collaboration (TOSEM 2024), AgentCoder, MapCoder (ACL 2024), CAMEL, AgentVerse, OpenHands (ICLR 2025), AutoCodeRover (ISSTA 2024), Agentless (FSE 2025), and the TOSEM surveys;
  - workflow orchestration and optimization: LangGraph, DSPy (ICLR 2024), GPTSwarm (ICML 2024), AFlow (ICLR 2025);
  - feedback and self-repair: Self-Refine, Reflexion, Self-Debugging, CodeT, TestPilot (TSE 2024);
  - empirical failure studies: MAST (NeurIPS 2025), CooperBench (ICLR 2026), "Passes Alone, Fails Together" (EXPRESS 2026).
- **Guarding, transacting and verifying LLM agents:**
  - runtime enforcement: AgentSpec (ICSE 2026), ShieldAgent (ICML 2025), Agent-C, CaMeL, AgentDojo (NeurIPS 2024);
  - transactions and concurrency control for LLM agents: the ICML 2026 position paper by Yang et al., SagaLLM, CoAgent, State Footprints, MemTX, PlanFence;
  - verified agent protocols: TraceFix, Lean4Agent (NeurIPS 2026);
  - semantic caching: GPTCache, vCache (ICLR 2026);
  - LLM nondeterminism: Ouyang et al., TOSEM 2025;
  - specifications for LLM systems: Stoica et al., SpecGen (ICSE 2025), nl2postcond (FSE 2024), an evaluation of LLM-written TLA+ (ICSOFT 2026).
- **Foundations:** consistency management; incremental computation (Adapton, DRed, Shake, Pluto); transactions (OCC, isolation levels, sagas, CRDTs); dynamic change; refinement.

A new positioning table (Table XIX) compares ten families of prior work along the five properties the controller combines. A closing subsection, "What Is Borrowed and What Is New", lists each borrowed mechanism and its source, then states four contributions narrowly:

1. Admissibility of *content* relative to the recorded observation.
2. Early cutoff that stays sound with nondeterministic producers.
3. Per-episode budgets and the upstream gate, which give a terminal outcome and single-episode repair.
4. A task-independent kernel that is verified once.

The transactional proposals for LLM agents are the closest concurrent work, and we discuss each of them in turn. PlanFence is the closest single mechanism. We state four concrete differences:

1. Staleness is judged by the trusted controller over keys that include the instruction, validator and selected context.
2. Early cutoff.
3. Per-episode budgets with a proved terminal outcome.
4. No compensation is needed before the barrier; the kernel is proved and partly mechanized.

We also added a discussion subsection to the evaluation (§VII-I, "What the Evidence Adds"). For each theorem, it names the ancestor mechanism and states what our data show beyond it, and where they show nothing. Examples:

- **RQ1:** version checks over the data read are not enough for generated content.
- **RQ5/RQ6:** they quantify how much of the early-cutoff ceiling survives stochastic generation.
- **RQ5:** the global barrier never fired with real models in our workflow, so its evidence comes from the adversarial campaign and model checking only.

> **AE-2.** *I find the article largely unintelligible, due to the over-reliance on hard-to-grasp terms … dependency signature, shape of the system, source footprint, pre-episode budget, intake, contract identity (also applied to requests, by the way) … no examples are provided in Section II.*

We accept this criticism. The revision makes three changes.

* **Example first.** §II now *begins* with the running example (§II-A, Fig. 1). A new figure (Fig. 2, a two-column table) shows one job of the example exactly as the controller stores it: match key, target, owner, read set, the observation as JSON, the dependency key, the request identity and the record after commit. Every later definition refers back to it.
* **Fewer and standard terms.** We removed "shape of the system", "intake view" (now *requirements view*) and "effective observation". We replaced "source footprint" with **read set**, "dependency signature" with **dependency key**, and "stamp" with **validated key**, the standard OCC and build-system terms. A new glossary (Table I) gives, for every remaining term, its meaning *and its standard counterpart* in MAS coordination, databases or build systems (for example, episode ≈ invalidation epoch with a retry budget; request identity ≈ message identifier / BSPL key; controller ≈ coordination artifact / governor).
* **Contract defined once.** The generation contract is now defined once, as a property of the *job* (Definition 1). It comprises instruction, schema, validator and its environment, generation settings and owner, and each request records the contract of its job at dispatch. This removes the inconsistency between §II-A and Table I that the editor and the reviewer both noted.

> **AE-3.** *The practical value, or significance, of the article is questionable … who will create these specifications? Perhaps the theoretical contribution could be of interest to formal methods venues, but I do not find it of value for the broad SE community.*

This is an important question, and the original manuscript did not answer it. The revision answers it in three ways.

1. **Who writes what (§III-B, Table II, new).** The TLA+ model, refinement mapping and proofs concern the *generic* coordination protocol. Framework builders write and verify them once, as for any concurrency-control algorithm. A workflow author never writes TLA+. They declare jobs in ordinary code (stage, prerequisites, owner, read-set function, context selector, contract, validator). We measured this effort for the two new LLM workflows: 22 lines of Python declarations plus 43 lines of validators (and a reusable sandboxed property checker) for the design/code/test workflow, and 17 lines for the benchmark workflow. The real cost of a workflow is its validators, which teams that test their software already write.
2. **Two kinds of guarantee (§I, Corollary 3, RQ6).** We now distinguish *coordination guarantees*, which hold for any agent and any validator, however weak (no stale or unauthorized commit, exact invalidation, bounded retries, honest completion), from *behavioral correctness*, which is exactly as strong as the validators. RQ6 measures the gap on standard benchmarks.
3. **Evidence with real LLMs for the SE community (RQ5, RQ6, new).** With seven open LLMs coordinating designs, code and tests, the commit guard rejected all 77 replies delivered after a controlled requirement change. All 47 of those that passed the validator of their original question were wrong for the new one (RQ5). On HumanEval+ and MBPP+ (542 tasks, five models, 14,069 calls), 12.9% of solutions accepted by the base tests failed the plus tests: 7.1% on HumanEval+ and 15.5% on MBPP+ (RQ6). Section VII-J turns the results into seven rules for builders of agent frameworks, each implementable as a commit policy in orchestrators such as LangGraph.

We have also narrowed the claimed scope (§I, §X) to artifact-centric, feed-forward workflows whose structure can be declared, such as model-driven pipelines, schema-driven configuration and interface synthesis, compliance documentation and CI-gated code/test generation. The paper does not target open-ended repository refactoring.

---

## Reviewer — 1. Problem framing, terminology, practicality

> **R-1.1** *Omission of foundational MAS coordination and verification literature; contrast with stateful graph orchestrators (LangGraph); justify TLA+/TLC relative to dedicated MAS model checkers and TraceFix.*

* **MAS coordination, commitments and institutions:** see AE-1 above (§I, §II-B, §III-A, §IX).
* **Verification (§IX, "Verification of multi-agent systems").** MCMAS, MABLE and AJPF verify temporal, epistemic or strategic properties of *agent programs or interpreted systems*. In our setting the agents are opaque, nondeterministic environment components. The object of verification is a single deterministic coordinator with data-rich state (unbounded identifiers, keys, request sets and histories), and its properties are state invariants plus a refinement between an asynchronous and an atomic machine. TLA+/TLC/TLAPS were designed for exactly these properties. We also note that an epistemic formulation in MCMAS would be a natural complement but would require a finite abstraction of keys and identities.
* **TraceFix (Xia et al., arXiv:2605.07935).** TraceFix synthesizes and repairs a *task-specific interaction protocol* with TLC counterexamples and monitors agents against it. We verify a *task-independent* kernel once and govern the generated *content*. We discuss how the two compose.
* **LangGraph and MCP (§I, §IX, §VII-J).** These provide the *mechanisms* our controller needs (typed shared state, reducers, checkpoints, tool access) but leave the *policy* to the application. A reducer applies whatever update arrives. Nothing records the observation an update was computed from, rejects updates whose inputs changed, invalidates exactly the affected state, or bounds retries per episode. Each rule of §VII-J can be implemented as such a reducer policy.

> **R-1.2** *Proliferation of bespoke terminology; delayed concrete grounding; inconsistent scoping of "generation contract".*

See AE-2 above. All three suggested improvements were implemented: example first with a concrete listing of a job, a terminology table mapped to standard terms, and a single job-level definition of the contract that includes the validator environment and the owner.

> **R-1.3** *Practicality of the division of labor; specification and validator bottleneck; structural rigidity; scope.*

See AE-3 above. In addition:

1. **Framework builder vs. workflow author** (§III-B, Table II). The read set is *exact by construction* for the agent, because prompts are rendered only from the observation (§III-A, principle 2). What remains to be established is that the *validator* judges the right relation (Definition 5, now called read-set adequacy). Automatic derivation of read sets from import/call graphs, and recording the inputs a prompt renderer actually reads, are discussed as future work (§X).
2. **Coordination hygiene vs. behavioral correctness:** stated in the abstract, §I, §V-A (after Corollary 3), §VII-J (rule 7) and §X, and measured in RQ6.
3. **Structural rigidity** (§X, new paragraph). We explain how structural proposals can be admitted through the structured-ingress extension: a planning agent proposes a typed source delta such as a new endpoint, which the controller checks as an untrusted edit and normalizes into new slots. We also state the scope explicitly in §I.

> **Minor 1.** Nguena-Timo; *TOPLAS* page range; archival identifier.

All corrected. The Foster et al. entry now reads "Article 17" with its DOI. The repository reference names the revision tag `tse-r1`, and the Data Availability section commits to a Zenodo DOI upon acceptance.

## Reviewer — 2. Formal semantics and guarantees

> **R-2.1** *Logical gap in Theorem 8, Algorithm 1 and reactivation liveness due to deferred structural checks across suspended stages.*

The reviewer is correct, and we are grateful for this precise analysis. We had listed the behavior as a limitation but had not recognized that it falsifies the inductive step and the sufficiency claim of the terminal-outcome theorem. The revision fixes the semantics, the theorem and the implementation.

* **Semantics (§IV-B "Deferred structural checks", new; assumption A1).** We implement both of the reviewer's options (a) and (b). (a) The commit guard evaluates, on the candidate, the structural expressions of all *configured* consumers that read the slot, whether or not they are currently enabled. (b) If an edit makes a structural expression fail *because of an already committed generated value*, the edit is not refused. The value is demoted to history (its job becomes stale), and normalization is retried; only failures caused by the inputs themselves reject an edit.
* **Theorem.** New Lemma 9 ("Reactivation cannot fail on committed values") closes the gap in the inductive step. Theorem 10 (terminal outcome) now cites it, and its proof states explicitly what was missing in the original. Algorithm 1 annotates the normalization step accordingly.
* **Implementation and evidence.** The reference controller now checks configured consumers (`_check_structure`). The regression test that encoded the old behavior was replaced by one asserting the new one. RQ1 adds the original semantics as a variant and a liveness property L1 ("no authorized change refused because of a committed generated value"): under the original semantics, 22 authorized changes were refused in 14 of 300 runs, and under the revised semantics none were.

> **R-2.2** *Restrictiveness of A0, A4, A5, A7; cyclic test–debug–fix loops; idealized validators.*

* **Scope.** §I and §X now describe the formalism as a feed-forward, artifact-centric discipline. Its coordination guarantees hold for any validator, and its correctness guarantees are validator-relative.
* **Cycles.** New §V-F and Proposition 11 (bounded feedback epochs) follow the reviewer's suggestion. Downstream diagnostics of epoch *t* are promoted by a deterministic policy to authoritative context of epoch *t+1*, with an epoch bound K_ep. Each epoch is acyclic, so termination and safety follow from the existing theorems. RQ5 uses one feedback epoch, promoting a barrier conflict to a workspace convention. Within an episode, validator diagnostics are also returned to the next attempt as *feedback*. Feedback is not part of the observation, so it changes neither keys nor validity.
* **Weak validators.** RQ6 now measures exactly this situation (base tests as validator, plus tests as ground truth). The counterexample with an under-specified read set remains in Table VI.

> **R-2.3** *Near-tautological construction of Theorems 2, 5, 7, 9, Corollary 3 and Propositions 6 and 10.*

We agree that several results follow almost directly from the guard definitions. The revision makes three changes.

* We now say so explicitly at the start of §V. We keep these results as theorems because each is a contract an implementation must preserve and that the evaluation tests; the substance lies in the *sufficiency* of the guard set (proofs) and the *necessity* of each guard (counterexamples, RQ1).
* Exact invalidation is now **Lemma 5**, with a paragraph explaining that its content lies in *what must be inside the observation*. Observation-relative isolation and the observational extension are now remarks (in §V-C and §V-H).
* Following the reviewer's suggestion, we added a genuinely multi-step protocol result. **Theorem 7 (single-episode repair):** in a stable revision with the upstream gate, every job starts at most one stale episode *for every interleaving* of dispatches, deliveries, timeouts and discards. This bounds the number of downstream episodes that a single edit can induce under asynchronous scheduling, which is the reviewer's specific concern about Theorem 7 of the original. **Proposition 8** shows that without the gate an adversarial schedule makes one job incur *w* episodes for fan-in *w*. RQ2 confirms both on lattices of depth up to 6 and width up to 4. The gated scheduler always needed exactly one request per affected job, while the ungated one needed up to 3.6× the requests and up to 7 episodes for a single job, with no makespan benefit.

> **R-2.4** *Cache restoration; owner identity in observations; formal definition of ℛ and nonce rollback; α(S) and abstract Publish.*

* **Cache restoration (§IV-E).** The retained accepted triple is now explicitly a *one-entry cache*, with a precise restore rule: a retained value is usable again iff its validated key equals the new key. This covers early cutoff and reactivation with an unchanged observation, but not reversion o₀→o₁→o₀ after a commit at o₁. A multi-entry memo table (as in Shake) is noted as an optional extension. Fig. 5 now shows the cutoff transitions (Dirty→Fresh and Fresh→Fresh when the validated key equals the new key).
* **Owner identity (Eq. 1, Definition 1, A2).** The owner is now part of the contract η and therefore of the key, matching the implementation. Revoking or reassigning ownership changes the key of every affected job.
* **ℛ and nonce rollback (§IV-E, Eq. 7).** Reconciliation is now defined by an explicit equation. Candidate states are private, nonces allocated in a discarded candidate are discarded with it, and request identities are only ever exposed from committed states.
* **α and abstract Publish (§V-B, Eq. 9; Remark 1).** α is now an explicit projection. Remark 1 shows that, with cancellation, a non-empty request set implies an outstanding obligation, so P = ∅ is implied by O = ∅ and abstract Publish needs no separate pending condition. An abstract Attempt leaves the job dirty, so the abstract machine cannot publish after an Attempt without a corresponding Accept or Fail, consistent with R3.
* **State types.** New Table III gives a type for every state component and separates operational from audit state.

> **Minor (§2).** All corrected: subscripts on validated keys and episodes (a_j, e_j, n_j); consistent `Publishable` notation (Table I now points to Eq. 7); the configuration subscript C is explained once after Eq. 1; spacing in match keys; inline binding of state symbols (Table III); "reject / timeout" labels in Fig. 5; the request record now written "u = (j, e, n) with (σ_j, o_j, ω_j)"; the proof of the generation bound reads "neither decrement nor reset"; the alternating observations are written o₀, o₁ (the a, b, a, b example was removed); and Algorithm 1 writes "guarded Resolve(u_j, v)".

## Reviewer — 3. Case study, validator and verification scope

> **R-3.1** *Circularity of the finite-language validator; use a domain where checking is simpler than synthesis; supplement scripted stubs with real LLMs.*

We agree that the validator of the finite language contains the solution. The revision states this openly (§VI-B): the construction is the *extreme point* at which the validator is the specification and Corollary 3 can be fully discharged. It is not a model of practice. The new workflows take the opposite position.

* **RQ5 workflow (§VI-D).** Agents write *free-form Python code* for a document store and *free-form test suites*. Code is validated by property-based testing (120 seeded random operation sequences, including invalid and path-traversal identifiers) against a 43-line *abstract model* of the clauses, with counterexamples shrunk by delta debugging and returned as feedback. Tests must pass on the abstract model and on the accepted implementation and kill at least three of four seeded mutants. Neither validator contains an implementation; the paper reports how many *structurally distinct* implementations were accepted.
* **RQ6 (HumanEval+ and MBPP+).** The declared validator is the base test suite, which does not determine the solution; the hidden plus tests measure correctness.

> **R-3.2** *Calibration of formal assurance claims; disconnected kernel and abstract value relation; tiny TLC instances (m = 0 for J ≥ 3; mutants only on J = 1).*

* **Extended TLC campaign (RQ4, Table XIV, new).** There are 14 baselines: chains of 2–5 jobs, a 3-job fan-out and a 4-job diamond, with up to m = 2 environmental changes and k = 2. They reach **718,672 distinct (7.5 million generated) states**, against at most 1,028 in the original, and no instance with J ≥ 3 has frozen inputs anymore. All nine mutants are checked on 2- and 3-job chains and the 4-job diamond (27 configurations): 21 violate their target property and the 6 single-defense removals survive, as predicted.
* **Refinement now machine-checked (bounded).** The new module `Refinement.tla` instantiates `AtomicController` under the projection α. TLC verifies "AsyncController implements AtomicController" on all 14 baselines. With both obsolete-reply defenses removed, TLC finds a refinement violation, so the check is not vacuous. Table VII now marks Theorem 4 as TLC-checked (◦) and states the remaining parameterized obligation.
* **Framing and barriers (§VI-C).** The text now says explicitly that the TLAPS modules are single-step lemmas, not the inductive invariant. It also explains the technical barriers to a parameterized TLAPS proof: `RECURSIVE` operators are unsupported by the TLAPS back ends, cardinality reasoning over history sets is hard for the SMT back ends, and reconciliation updates seven nested record fields at once.
* **Abstract value relation.** We explain why the abstraction "valid iff equal to the observed source" suffices: the protocol properties quantify over the validator, so any total validator yields the same transition structure. The disconnect between the typed kernel and the protocol model remains listed as an open obligation (Tables VII and §X).

> **R-3.3** *Discrepancy in TLAPS obligation counts (21 vs. 25); reproduction only on pre-fix snapshots.*

* **Obligation counts (RQ4).** The repaired modules split the failing proof steps and cite construction and type assumptions explicitly, which changed the number of obligations TLAPS generates from 21 to 25. Counts are therefore comparable only within one version of a module. The first-trial sources were not archived; every run now archives its sources.
* **Post-revision reproduction.** All stages that the code fix could affect were re-run on the revised code: tests, scenarios, trace conformance, the RQ1/RQ2 campaign, and SANY, TLC baselines, mutants and witnesses. All nine baselines, nine mutants and five witnesses reproduce *exactly* the original state counts and counterexample lengths with the current TLC release. The TLAPS sources are unchanged since the archived run. Re-running TLAPS for the revision is blocked by toolchain drift. The pinned pre-release archives of both `tla2tools.jar` and `tlapm` have since been replaced upstream; our bootstrap refuses unpinned bytes by design, and re-pinning requires an explicit decision. We report the TLC version and the hash of the jar actually used.

> **Minor (§3).** The proof of the policy theorem now writes f_{h=1} and covers archive from open. Table VII now lists the remaining obligation for every partial row (the isolation row was removed when isolation became a remark). Spelling is consistently American ("defense").

## Reviewer — 4. Evaluation

> **R-4.1** *External validity of omitting real LLMs; early cutoff and outcome equivalence under stochastic generation; latency and retries.*

We agree; this was the most important gap. Two new research questions use real models, run on our own GPUs and on the Digital Research Alliance of Canada clusters. Every call is logged with its full response, token counts, latency, seed and model digest.

* **RQ5 (seven open models).** This covers completion of four-service workspaces with validator feedback and a feedback epoch, and stale-reply trials in which R03 changes while the model is generating. It also covers early cutoff after a reworded contract at temperatures 0 and 0.7, measured at four levels: raw text, slot value, AST and semantic equality. The reviewer's points (a)–(c) are answered by this question's tables: how often exact vs. AST/semantic early cutoff occurs, how often local and global validators reject, and token and wall-clock cost per strategy.
* **RQ6 (HumanEval+, MBPP+; five models).** This measures validator-relative correctness and the early-cutoff rates at scale (byte, value, AST, behavior on plus inputs).
* **Results, including the unfavorable ones.**
  - 16 of 42 workspaces were published. The three models below 10B parameters published none; the controller reports such failures explicitly but cannot repair them.
  - Validator feedback recovered 73% of rejected first attempts (95% CI 68–78%).
  - Early cutoff fired for canonical JSON designs (94% value-equal) but rarely for free-form code: 15% in RQ5 and 28% in RQ6, against 94% behavioral equality.
  - In the cost runs, exact keys used 4.0× fewer requests than full regeneration. However, they published after fewer changes for one model (5/8 vs. 7/8): a failed verdict is retained for an unchanged episode, whereas full regeneration re-samples every job. §VII-G discusses this trade-off.
  - The barrier conflict (F2) never occurred with real models, so its evidence remains the adversarial campaign and model checking.
  - An underspecified design contract (the operation name `put`) depressed first-attempt design acceptance. We disclose it in RQ5 and the threats section.
* **Qualifications in the text.** RQ2 now states that outcome equivalence holds because providers are deterministic. The 11.9× and 2.3× savings are now explicitly attributed to the independent topology. With real models we report *publication validity*, not equality, as the outcome criterion.

> **R-4.2** *Artificial workspace partitioning behind the 11.9× and 8.1× claims.*

The revision states that the N documents are independent by construction and that the ratios grow with N for that reason (RQ2, caption of Table IX). A **new coupled benchmark** (Table X) has 32 modules whose designs read f ∈ {0, 1, 2, 4, 8} of 8 shared data-model components, with semantic and cosmetic edits of shared components. Exact keys pay exactly for the affected subgraph: a semantic shared edit costs 2 requests at f = 0 and 98 at f = 8, and in every run every exact request was caused by a changed observation. Early cutoff pays off for cosmetic shared edits (2 vs. 98 requests at f = 8). At the highest coupling, full regeneration still needs 6.5× the requests of exact keys, the whole-workspace strategy 5.5× and no-early-cutoff 1.9×. Table IX also gains a "total kB per change" row, so the 52× and 9× byte ratios can be checked directly from the table (Minor 4.1).

> **R-4.3** *Methodological circularity in RQ1 ablations and RQ3 scenarios.*

We agree with the characterization. §VII-A now states that RQ1 and RQ3 are verification activities: mutation-based guard-necessity checks and conformance tests. RQ1 notes that violation rates are a property of the action generator, and RQ3 that the expectations were written by the author. Empirical claims about multi-agent practice are confined to RQ5 and RQ6.

---

## Additional changes not requested

* A second, generic implementation of the kernel (`src/vgc/graph.py`) for arbitrary job graphs, with optimistic validation outside the lock and recheck at commit. It was differentially tested against the reference controller on 150 change streams (6,000 changes, five strategies), with identical request counts and accepted values after every change.
* The cluster tooling (`hpc/`) and all new drivers are part of the replication package, and every number in the paper is regenerated from raw results by `experiments/tse_paper.py` and `experiments/revision_paper.py`.
