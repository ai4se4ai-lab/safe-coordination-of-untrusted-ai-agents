---- MODULE Model_s_chain6 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {1} [] 3 = j -> {2} [] 4 = j -> {3} [] 5 = j -> {4} [] 6 = j -> {5}]
====
