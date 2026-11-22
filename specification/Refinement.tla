------------------------- MODULE Refinement -------------------------
\* Bounded machine check of Theorem 4 (forward simulation): every behaviour of the
\* asynchronous controller, projected through Alpha, is a behaviour of the atomic
\* specification AtomicController (allowing stuttering). Alpha erases remote requests,
\* delivery history, commit records and per-request evidence, and keeps every semantic
\* and budget component, exactly as in the paper.
EXTENDS AsyncController
Alpha == [s EXCEPT !.pending = {}, !.history = {}, !.commits = {},
                   !.evidence = [j \in Jobs |-> None]]
A == INSTANCE AtomicController WITH a <- Alpha
AtomicRefinement == A!Spec
=============================================================================
