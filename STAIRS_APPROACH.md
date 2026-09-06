# The stairs approach, measured 2026-09-06

Derived live with the user watching the stream. Every number here was checked on
the console, not inferred. It replaces guesswork about how leg 2 should start.

## The pose that works

    position   where leg 1 now lands (one merged 1.95s push, aimed to <1 deg)
    bearing    ~3.7-4.5   COMMANDED WITH tolerance 0.5, NOT the 4.0 default
    pitch      home DOWN to the floor stop, then 22 presses UP

From that pose, five pushes of speed 0.35 for 0.80s descend the stairs and reach
the doorway. Bearing held 6.7 / 6.6 / 6.7 / 6.7 / 6.7 across all five — no drift.

## Why each part is stated that way

**Bearing needs the tight tolerance or it cannot be commanded at all.** With the
default 4.0, asking for 1.0 deg from 2.7 sent NOTHING, and asking for 5.0 landed
on 7.8. Two of five panels in a sweep came out identical for this reason. With
tolerance 0.5 the same targets landed within 0.2 deg: 3.5 -> 3.7, 4.5 -> 4.5,
5.5 -> 5.7, 6.5 -> 6.7.

**Pitch is expressed from the FLOOR stop because that is the only detectable
end.** home_pitch reads 24.18 against a 1.29 noise floor going down; the
docstring records that going up "gave a flat 6-10 delta for all 14 presses and
never settled". Verified two independent ways that agree: 14 presses down from
the ceiling and 22 up from the floor land on the same aim, and 14 + 22 = 36,
which is the full ceiling-to-floor range measured.

## THREE NUMBERS ABOUT PITCH CONTRADICT EACH OTHER

    level_pitch docstring   4 positions across the whole range
                            (+0 floor, +1 furniture, +2 LEVEL, +3 ceiling)
    PITCH_STEPS_FROM_BOTTOM 14 steps from the bottom to level
    measured 2026-09-06     36 presses from ceiling to floor,
                            22 from the floor to the doorway aim

At least two of those are wrong. `+20` presses up from the floor is the CEILING,
with the doorway not in frame at all, so the docstring's four-position range
cannot be right in the same units. Nobody currently knows how to command a
specific pitch, and PITCH_STEPS_FROM_BOTTOM would put the camera in the ceiling
if anyone wired level_pitch into the live path.

## PITCH IS UNCONTROLLED IN PRODUCTION

`level_pitch` has ONE caller: walk_route_v2.py, the routing generation
graph_walk replaced. graph_walk never touches pitch. The user reports that a
reset restores pitch to a baseline, so it is deterministic rather than random —
but nothing verifies that, and an off-baseline pitch would depress identify()
scores on every frame of every leg while looking like "the localiser is marginal
here". Tonight's runs produced arrivals scoring 138, 153, 91 and 24 against
clean arrivals of 500-700.

## What this does NOT settle

- Whether pitch changes where the character WALKS or only what the camera sees.
  Untested, and it decides whether levelling pitch is a real fix or cosmetic.
- The exact bearing. 3.7 or 4.5; at 6.7 the reticle sits on the right-hand door
  frame and the opening is to its left.
- Whether leg 2's recorded steps should be re-cut or replaced. Its opening
  bearing of 338.11 is ~30 deg off from where leg 1 now lands, and its first
  five steps rotate toward 8.57 — the heading the character already needs
  immediately. That is the signature of an opening that duplicates ground leg 1
  now covers.

## The compass abstains at the bar doorway, and why (2026-09-06)

`test_fixtures/compass/bar_doorway_abstains_1920.png` is a LOSSLESS capture of
the exact pose where the route must turn toward Wanda. `read_bearing` returns
None on it, and the turn toward Wanda therefore cannot execute at all: turn_to
is a closed loop, so with no heading it computes no error and sends nothing.
Five sweep targets in a row produced an identical frame.

**IT IS NOT THE RECOGNISER.** Traced exit by exit:

    find_bar            (64, 608, 1325)      strip located
    blobs               5 at thr 110, 3 at 120, 2 at 130-155
    letters recognised  W and N, correctly, at thresholds 130/140/155
    spacing_consistent  both survive, pitch 291.9
    TICK SNAP           REJECTED

The pooled loop breaks at the FIRST threshold yielding two letters, and that is
the noisiest one — it admits the most blobs, so neighbouring ink pulls a
letter's centroid off:

    threshold 110 (first to give two)   W at 702, N at 985
    threshold 140                       W at 692, N at 983

Ten pixels at 291.9 px per 90 degrees is 3.1 degrees, and TICK_SNAP_MAX_DEG is
3.0. Snap errors are [3.40, 0.66] at 110 against [0.32, 0.04] at 140, and the
frame reads 352.8 from the cleaner centroids. So a perfectly readable frame is
discarded for having searched too little.

**A FIX WAS TRIED AND REVERTED, and the reason is the useful part.** Sweeping
two thresholds FURTHER before breaking made the doorway frame readable and one
other, but LOST `explore/20260904_152521_bar_area/00068.jpg`, whose old read of
117.6 was CORRECT — 0.7 deg from the 45-degree sweep arithmetic, an oracle that
knows nothing about OCR. Net +2/-1 on 161 frames.

Pooling MORE thresholds accumulates blobs and moves the centroids for frames
that were already fine, so it cannot be the answer. The diagnosis stands and the
design does not: evaluate each threshold's reading INDEPENDENTLY and keep the
one the tick lattice agrees with most closely. The lattice is fitted to 0.2px
and knows nothing about which threshold produced a centroid, so it is a fair
judge between them. Not implemented.

**Until then the turn at the doorway must be OPEN-LOOP**, driven by
turn_curve's measured rate rather than by turn_to's closed loop.
