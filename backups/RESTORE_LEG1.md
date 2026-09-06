# Original leg 1 — how to put it back

`office_corridor -> office_door` as it walked before 2026-09-05.

## What the original was

The RECORDED STEPS were never edited. `world_map.json` still holds leg 1 exactly
as recorded: 7 steps, bearings 270.10-270.42, dur 0.78-0.79s, speed 0.21-0.23,
5.13s, 1.1676 walk-units. Nothing to restore there.

Only three flags in `graph_walk.py` changed how those steps are EXECUTED:

    LEG_SPEED_BY_LEG      = {}            # was empty  -> now {("office_corridor","office_door"): 3.0}
    MERGE_STEPS_BY_LEG    = set()         # was absent -> now {("office_corridor","office_door")}
    MERGED_TURN_TOLERANCE                 # was absent -> now 1.0

## To restore, exactly

    .venv/bin/python backups/restore_leg1.py

or by hand: set LEG_SPEED_BY_LEG back to {} and MERGE_STEPS_BY_LEG to set().
MERGED_TURN_TOLERANCE then applies to nothing and is harmless.

## What each one does, so a partial revert is possible

| flag | effect | measured |
|---|---|---|
| `LEG_SPEED_BY_LEG` 3.0 | 7 pushes of 0.79s@0.21 -> 7 of 0.26s@0.64 | 5.13s -> 1.95s of walking. **Walks the leg SHORT**: a 0.26s push is mostly acceleration, so arithmetic distance is preserved and physical distance is not. |
| `MERGE_STEPS_BY_LEG` | 7 pushes -> 1 push of 1.95s | removes 6 of 7 SETTLE_SEC pauses (2.45s -> 0.35s) and 6 of 7 accelerations. **This is what fixes the short walk.** |
| `MERGED_TURN_TOLERANCE` 1.0 | the single turn aims to 1.0 deg not 4.0 | turn error 3.7 deg -> 0.7 deg. Needed because a merged leg walks its whole distance on one heading. |

## Why they are coupled

Speed WITHOUT merge walks short (measured, and visible on the stream).
Merge WITHOUT the tight turn carries the full heading error the whole way
(measured: 3.7 deg over 1.168 units, ~0.075 units of drift).
So revert all three together, or none.

## Git

The pre-change state is commit 2fb1ae6 and earlier:

    git show 2fb1ae6:graph_walk.py > /tmp/graph_walk_before_leg1.py
