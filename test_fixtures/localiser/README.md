Arrival frames from live navigation runs on 2026-09-01, each labelled with the
room I confirmed BY EYE by comparing it against that room's reference frame
(matching the pool table and wall clock, the jukebox and dartboard, the framed
portraits and rug, the dealer and his prompt).

They are HELD-OUT test data: the localiser's references come from the recorded
demo, and none of these frames is a reference. They exist because the failure
that matters is not "does a reference recognise itself" but "does a frame taken
where the executor ACTUALLY stops, with the NPCs wherever they wandered to,
still get recognised". The edge descriptor managed 1 of 5 on these; keypoint
matching gets 5 of 5.
