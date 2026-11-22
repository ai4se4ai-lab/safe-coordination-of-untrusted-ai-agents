---- MODULE Model_s_chain4 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {1} [] 3 = j -> {2} [] 4 = j -> {3}]
====
