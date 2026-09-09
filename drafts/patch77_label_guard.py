"""patch77 -- a template is never cut from a label the local reader confidently contradicts.

WHY. On 2026-09-09 the paid vision model read three PITCHER cards of power 6 as 5s. The
user confirmed the frame by eye: one Fielding Play, one Pitch Focus, and three pitchers at
6. A template cut from that hand under the paid label would be a 6 filed as a 5, matching
its own source crop at correlation 1.0000 and reading it wrong forever after -- which is
precisely how six bad templates got into the bank earlier the same day.

The audit over the whole corpus: 3 disagreements in 368 player slots, all in that one hand,
all at local score 0.99. So the corpus is 99.2% clean AND it is not clean enough to cut
from blindly.

THE GUARD IS DELIBERATELY SYMMETRIC AND DUMB. It does not decide who is right. When the
local reader names a digit at CONFIDENT_DISAGREE or above and the paid model names a
different one, the slot is SKIPPED and printed. Neither label is trusted, nothing is
inferred, and the count of skips is reported so silence cannot hide a growing rift.
"""
import io

P = "tools/build_tactics_templates.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = '''    for line in open(CORPUS):'''
assert s.count(ANCHOR) == 1, f"loop anchor x{s.count(ANCHOR)}"

GUARD = '''    # A LABEL THE LOCAL READER CONFIDENTLY CONTRADICTS IS NOT A LABEL.
    # The paid model read three 6s as 5s on 2026-09-09 (confirmed by the user against the
    # frame), and a template cut under that label matches its own source crop at 1.0000 and
    # reads it wrong forever. This does not adjudicate -- it SKIPS, and it counts.
    CONFIDENT_DISAGREE = 0.95
    skipped = []

    def _contradicted(rows, cards):
        """Slot indices where local names a digit >= CONFIDENT_DISAGREE that paid denies."""
        out = set()
        for i, (x, c) in enumerate(zip(rows, cards)):
            if c.get("kind") != "player" or x.get("digit") is None:
                continue
            if x.get("score", 0.0) >= CONFIDENT_DISAGREE and \\
                    str(x["digit"]) != str(c.get("power")):
                out.add(i)
        return out

    for line in open(CORPUS):'''
s = s.replace(ANCHOR, GUARD, 1)

OLD_INNER = '''        for i, (x, c) in enumerate(zip(rows, r["vision"])):
            if c["kind"] == "tactics" and c.get("type"):'''
assert s.count(OLD_INNER) == 1, "inner loop anchor"
NEW_INNER = '''        bad = _contradicted(rows, r["vision"])
        if bad:
            skipped.append((r.get("crop"), sorted(bad)))
            continue
        for i, (x, c) in enumerate(zip(rows, r["vision"])):
            if c["kind"] == "tactics" and c.get("type"):'''
s = s.replace(OLD_INNER, NEW_INNER, 1)

OLD_END = '''    print(f"{len(items)} located tactics cards in {len({i['group'] for i in items})} hands")'''
assert s.count(OLD_END) == 1, "report anchor"
NEW_END = '''    if skipped:
        print(f"SKIPPED {len(skipped)} hand(s) whose paid label the local reader "
              f"confidently contradicts -- neither label is trusted:")
        for crop, slots in skipped:
            print(f"    {crop}  slots {slots}")
    print(f"{len(items)} located tactics cards in {len({i['group'] for i in items})} hands")'''
s = s.replace(OLD_END, NEW_END, 1)
io.open(P, "w", encoding="utf-8").write(s)
import ast; ast.parse(s)
print("tools/build_tactics_templates.py: contradicted labels are skipped and reported")
