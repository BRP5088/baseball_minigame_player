Reference frames REMOVED from places/ on 2026-09-01, kept rather than deleted.

All three are near-featureless dark frames from the beside_dealer_table sweep.
places.descriptor() divides by the vector norm, so a frame with almost no
structure becomes mostly the vignette/letterbox component that EVERY frame
shares — measured, 88-89% of each of these descriptors is that shared
component, against 51-53% for the dealer_table references.

The consequence was a confident false positive on a completely different floor:
demos/walk3_full_20260828_050731/f_0016.06.jpg — the character standing at a
closed office door UPSTAIRS, 45s before reaching the bar — identified as
beside_dealer_table at score 0.906 / margin 0.366, HIGHER than any genuine
live match in the corpus (real arrivals score 0.51-0.78). No score threshold
can fix that, because the spurious match outscores the real ones.

Removing these three was necessary but NOT sufficient: the same frame still
matched beside_dealer_table at 0.80/0.26 afterwards, which is why the node set
was rebuilt from the recorded route (build_world_map.py) rather than patched.

Do not put them back. If beside_dealer_table needs more references, capture
them somewhere with structure in view.

## legacy/ — labels that are not graph nodes (2026-09-01)

`beside_dealer_table` (12 frames) and `bar_exit_corner` (1 frame) predate the
graph and are not nodes in world_map.json, so nothing can route from them. They
were not merely useless, they were ACTIVELY HARMFUL: on the first live walk the
executor arrived correctly at the portrait room and identify() answered
`beside_dealer_table` at 0.621, because two of its dark sweep frames scored
0.597 and 0.591 against that room while the true portrait_room reference did
not reach the top eight. The walk had worked; the label set failed it.

`bar_exit_corner` had one frame and was itself confidently misidentified as
beside_dealer_table (0.619 / margin 0.306) in leave-one-out.

places/ should hold exactly the graph's seeded nodes. A label that cannot be
routed from can only outvote one that can.
