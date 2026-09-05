# Failure frames

**NOTHING HERE HAS EVER CAPTURED THE JUKEBOX LEG'S OWN FAILURE.** Two
successive attempts both produced frames that look authoritative and describe
something else. Check what moment a frame captures before reasoning from it.

## Attempt 1 — captured too LATE (frames in `../failframes_prerecovery/`)

Captured AFTER `recover_to_node` ran, so they show where the recovery FAN left
the character, not where the leg did. Six of them sit at bearing 98.1-105.8
against the leg's commanded 2.1 — a ~100 degree offset that is exactly the fan
walking back at +180 after its -80 offset. Six of six.

The fan also travels FURTHER than the leg it is rescuing (~7x cumulatively),
which is why two rich frames from it are 423px apart and do not recognise each
other. A confident diagnosis was built on these frames and was wrong.

They remain valid as CLASSIFIER data — a wedged frame looks like a wedged frame
whatever put the character there — and invalid as evidence about the leg.

## Attempt 2 — captured too EARLY (the four `fail_bar_jukebox_*.jpg` here)

Captured BEFORE the whole attempt, because `follow_verified` took `before =
capture()` ahead of `go_to_node_verified`, which walks the entire leg. So they
photograph the PREVIOUS node's successful arrival.

The tell: all four identify as **`bar_pool_room` at 506-734 matches, ratio
4.27-5.48**, at bearing 284.8-288.3 — the INBOUND heading of the previous leg
(which commands 286.6 / 292.2 / 285.6 / 287.6). A frame of the failing leg would
not confidently identify as the node the leg departs from.

They are also all from one 27-minute window in which both arms of an A/B
collapsed together while chiaki logged 32,388 decoder-overflow lines — an
environmental failure, not a navigation one.

## What is correct

`follow()` already saves at the right moment — its `at_<node>.jpg` write sits
BEFORE the `recover_to_node` call, not after. (Line numbers are deliberately
omitted: the pair quoted here was wrong within a day of being written, and
graph_walk.py is 1600+ lines.) `shots` is now threaded down through
`go_to_node_verified` so that path is used, writing `at_<node>.jpg`.

**Unverified live as of 2026-09-04.** The first run that passes `shots=` will
say whether it works — and the check is the bearing: a real jukebox-leg failure
frame should NOT read ~286 and should NOT identify as `bar_pool_room`.
