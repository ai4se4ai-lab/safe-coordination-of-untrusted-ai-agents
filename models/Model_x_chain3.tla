---- MODULE Model_x_chain3 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {1} [] 3 = j -> {2}]
====
