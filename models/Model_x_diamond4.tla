---- MODULE Model_x_diamond4 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {1} [] 3 = j -> {1} [] 4 = j -> {2,3}]
====
