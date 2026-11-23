---- MODULE Model_s_fanin4 ----
EXTENDS Refinement
ModelParent == [j \in Jobs |-> CASE 1 = j -> {} [] 2 = j -> {} [] 3 = j -> {} [] 4 = j -> {1,2,3}]
====
