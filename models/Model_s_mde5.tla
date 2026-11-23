---- MODULE Model_s_mde5 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {1} [] 3 = j -> {1} [] 4 = j -> {1,2,3} [] 5 = j -> {3,4}]
====
