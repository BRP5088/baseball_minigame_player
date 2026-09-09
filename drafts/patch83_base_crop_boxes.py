"""patch83 -- first_base and third_base are cut too low. Shift them up by the measured amount.

THE USER SAW IT FIRST, twice: "the runners on first base are slightly cropped, you have
more of the bottom then you might need. Like the crop box should be shifted up", then
"third base has the same problem as first base. it sits a little low." Both are right, and
CLAUDE.md has recorded these two boxes as wrong since 2026-09-08 without anyone measuring
by how much.

MEASURED on recorded frames rather than on the crops -- a box cut too low shows a truncated
card and says nothing about what lies above it. Bright card-sized components near each
base, over 5 frames where the paid model reported a runner:

    first_base   the CARD sits at y 0.299 .. 0.494
                 the BOX is        y 0.320 .. 0.530
                 -> the top 0.021 of the card is OUTSIDE the box, and 0.038 of the box is
                    empty table below it

A frame with all three bases loaded (run patch80_compare, frame 18735) shows the same on
THIRD: the BATTER banner and the power disc sit above the red box while the box runs into
bare table. second_base fits cleanly and is NOT touched -- the user confirmed it
independently ("second base looks pretty good") and it is the one box with a different
vertical placement.

THE FIX IS THE MEASURED SHIFT, -0.030 in fractional height, applied to both lower bases:

    third_base   y 0.320..0.530  ->  0.290..0.500
    first_base   y 0.320..0.530  ->  0.290..0.500

The height is unchanged, so nothing downstream that assumes a crop size moves. Only the
window slides up onto the card.

WHY IT MATTERS MORE THAN THE ABSTENTIONS IT FIXES. The reader abstained on only 1.4% of
turns, which I had judged not worth fixing. The user pushed back, and they were right for a
reason I had missed: it also calls first base occupied 63 times in 360 and third base 20
times, CONFIDENTLY. A clipped card is exactly what makes a disc reader confident and wrong,
and "runners on base" changes which pitcher gets played.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''    "third_base": (0.3225, 0.320, 0.4375, 0.530),
    "first_base": (0.550, 0.320, 0.665, 0.530),'''
assert s.count(OLD) == 1, f"region anchor x{s.count(OLD)}"
NEW = '''    # MEASURED 2026-09-09 from recorded frames, not from the crops: a base CARD sits at
    # y 0.299..0.494 while these boxes started at 0.320, so the card's top -- its banner
    # and its power disc -- fell OUTSIDE and 0.038 of the box was bare table below. The
    # user spotted it by eye on both bases before it was measured. second_base is not
    # touched: it has a different vertical placement and reads correctly.
    "third_base": (0.3225, 0.290, 0.4375, 0.500),
    "first_base": (0.550, 0.290, 0.665, 0.500),'''
io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
print("orchestrator.py: third_base and first_base shifted up 0.030")
