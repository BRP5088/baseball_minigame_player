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
