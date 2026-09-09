"""Record 10.22 in CLAUDE.md: a matching COUNT does not prove correspondence."""
import io
P = "CLAUDE.md"
s = io.open(P, encoding="utf-8").read()
ANCHOR = '''into the import path waits. "It is a small edit" is not an exception — the
child does not know how small it was.
'''
assert s.count(ANCHOR) == 1, f"anchor x{s.count(ANCHOR)}"
NEW = ANCHOR + '''
**22. A MATCHING COUNT IS NOT CORRESPONDENCE, AND SCORING ON IT MANUFACTURES A
CLEAN RESULT OUT OF TWO ERRORS.** 2026-09-09: the local hand reader's accuracy
was scored by lining its rows up with the paid model's cards BY POSITION on
every hand where the two counts matched. The reader can miss one card and
invent another in the same hand — the count still matches, and every column
after the first error is compared against the WRONG card. The table that came
out looked like a finding: 4 read at 90%, 5 at 88%, but 6 at 31%, 7 at 33% and
9 at 0%, tracking template counts so neatly that the diagnosis wrote itself.
It was an artefact. A contact sheet of the "missed 6s and 7s" showed FIELDING
PLAY cards.

Re-scored with correspondence PROVEN — the counts match AND the set of slots
each side calls tactics matches — only **10 of 57 hands could be compared at
all**. The real defect was never the templates; it was that the reader did not
agree with the model about POSITIONS on 47 of 57 hands.

It also corrupts what is built on it: 79 templates were cut using that
alignment, and six were wrong — three labelled one card off (a 6 labelled 7, a
5 labelled 6, a 4 labelled 7) and three that are not digits. Each matched its
own source crop at correlation 1.0000, so it read that crop wrong forever
after, confidently, at score 1.000.

And it hides itself in the metric: the old reader scored **41 of 41 = 100%** on
its 10 aligned hands, and two of those hands were two errors cancelling — a
mouse's nostril padded the count and read "5" where the missing card's power
was 5. **A pipeline whose own output defines the alignment cannot be scored on
that alignment.** Require an independent agreement — here, the kind pattern —
and report how many samples were excluded, never just the rate.

'''
io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, NEW, 1))
print("CLAUDE.md 10.22 added")
