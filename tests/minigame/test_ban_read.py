"""THE BAN SCREEN'S DECISIONS, which nothing could test until today.

affected_tests.py said it plainly when the viewer changed: "state_viewer.py -> NO TEST
IMPORTS IT. Nothing here can prove this change; the full suite cannot either." A Tk window
is built at import, so the file was untestable by construction, and a day's worth of
decisions lived inside it. ban_read.py is those decisions with the GUI left behind.

Every check here is against a LITERAL, never against the constant it guards (10.11).
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import ban_read as br

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


class Card:
    """Stands in for a roster PlayerCard."""
    def __init__(self, power, secondary):
        self.power, self.secondary = power, secondary


print("1. THE LATCH: a new answer must be seen TWICE before it replaces a held one")
S = {}
check(br.latch(S, "k", "batter", "g0") == "batter",
      "the first answer shows at once — there is nothing held to protect")
check(br.latch(S, "k", "batter", "g0") == "batter", "...and repeating it changes nothing")
check(br.latch(S, "k", "pitcher", "g0") == "batter",
      "a DIFFERENT answer seen once does NOT replace it — this is the whole rule")
check(br.latch(S, "k", "pitcher", "g0") == "pitcher",
      "...and seen twice running, it does")

print("2. AN ABSTENTION NEVER REPLACES ANYTHING")
S = {}
br.latch(S, "k", "batter", "g0")
check(br.latch(S, "k", None, "g0") == "batter",
      "None leaves the held answer standing — the frames differ, not the reader")
check(br.latch(S, "k", None, "g0") == "batter", "...twice running, still standing")
check(br.latch(S, "k", None, "g0") == "batter", "...and a third time")
S2 = {}
check(br.latch(S2, "k", None, "g0") is None,
      "with nothing held, None is still None rather than a manufactured answer")

print("3. A FLICKER BETWEEN TWO ANSWERS SETTLES, it does not oscillate")
S = {}
br.latch(S, "k", "A", "g0"); br.latch(S, "k", "A", "g0")
out = [br.latch(S, "k", v, "g0") for v in ("B", "A", "B", "A", "B", "B")]
check(out[:5] == ["A", "A", "A", "A", "A"],
      f"alternating answers never dislodge the held one ({out[:5]})")
check(out[5] == "B", f"...until one of them arrives twice in a row ({out[5]})")

print("4. SCROLLING CLEARS EVERYTHING — a held name over a new card is the worst answer")
S = {}
br.latch(S, "k", "batter", "g0"); br.latch(S, "k", "batter", "g0")
check(br.latch(S, "k", None, "g1") is None,
      "a new scroll key drops the held value instead of carrying it onto another card")
check(br.latch(S, "k", "pitcher", "g1") == "pitcher",
      "...and the new page's first answer shows at once")

print("5. rowkey CHANGES WHEN THE GRID MOVES AND NOT OTHERWISE")
a = [{"top": 0.281}, {"top": 0.609}]
b = [{"top": 0.2814}, {"top": 0.6088}]       # same position, capture noise
c = [{"top": 0.230}, {"top": 0.558}]         # scrolled
check(br.rowkey(a) == br.rowkey(b),
      "two hundredths of a percent of jitter is the same position, not a scroll")
check(br.rowkey(a) != br.rowkey(c), "a real scroll is a different key")
check(br.rowkey(None) is None and br.rowkey([]) is None, "no rows, no key")

print("6. KIND: unknown is its own answer and must never become 'player'")
check(br.kind_of(("tactics", "SPEED BOOST")) == "tactics", "a tuple is a tactics card")
check(br.kind_of("batter") == "player" and br.kind_of("pitcher") == "player",
      "a string is a player card")
check(br.kind_of(None) is None,
      "and None is None — it fell through to 'player' once and painted four player "
      "windows over a tactics card")

print("7. THE BOXES FOLLOW THE KIND, and an unknown kind gets NONE")
check(br.boxes_for("player") == ("name", "type", "power", "shield"),
      f"a player card gets its four ({br.boxes_for('player')})")
check(br.boxes_for("tactics") == ("tac_label", "tac_bonus"),
      f"a tactics card gets its two ({br.boxes_for('tactics')})")
check(br.boxes_for(None) == (),
      "an unknown card gets NOTHING — drawing a guess is drawing a lie about where the "
      "reader is looking")
check(set(br.boxes_for("player")).isdisjoint(br.boxes_for("tactics")),
      "and the two sets share no box, because the two layouts share no geometry")

print("8. WHERE A VALUE COMES FROM: roster, then bank, then OCR")
check(br.values_for(card=Card(7, 1), bank=(5, 3), ocr_power=9) == ("7", "1", "roster"),
      "the ROSTER wins over both — on all 12 measured disagreements the crop showed the "
      "roster's digit, never the reader's")
check(br.values_for(card=None, bank=(6, 2), ocr_power=9) == ("6", "2", "bank"),
      "the BANK wins over OCR when the name did not read")
check(br.values_for(card=None, bank=(None, None), ocr_power=6) == ("?6", "-", "ocr"),
      "OCR is the last resort and is marked with a '?' because it is 84% right")
check(br.values_for(card=None, bank=(None, None), ocr_power=None) == ("-", "-", "ocr"),
      "and when nothing reads, nothing is claimed")

print("9. A SHIELD IS ONLY REPORTED WHEN THE POWER CONFIRMED A CARD IS THERE")
check(br.values_for(card=None, bank=(None, 0))[1] == "-",
      "a shield 0 with NO power is refused — the bank cannot tell 'no badge' from 'this "
      "window is not on a card' (0.40 vs up to 0.564, one population)")
check(br.values_for(card=None, bank=(5, 0)) == ("5", "0", "bank"),
      "...and with a power beside it, the same 0 is a real answer")

print("10. THE RANGE RULES, pinned as LITERALS")
check([d for d in range(0, 12) if br.power_ok(d)] == [4, 5, 6, 7, 8, 9],
      f"power is 4..9 and nothing else ({[d for d in range(12) if br.power_ok(d)]})")
check(not br.power_ok(3) and not br.power_ok(1) and not br.power_ok(2),
      "1, 2 and 3 are misreads: no card in the game has them")
check(br.bonus_ok(1) and br.bonus_ok("2") and not br.bonus_ok(3) and not br.bonus_ok(0),
      "a tactics bonus is 1 or 2 — a +3 does not exist, and the paid model invented eleven")
# +2 EXISTS ON EXACTLY ONE CARD. Over 299 hand-labelled tactics cards POWER SWING is +1 60%
# / +2 40% and the other three are +1 on every card between them. The viewer showed
# "Speed Boost +2" on a live screen, which the census says cannot happen.
check(br.bonus_ok("2", "POWER SWING"), "a POWER SWING may be +2")
check(not br.bonus_ok("2", "SPEED BOOST"), "a SPEED BOOST may NOT — it is +1 on all 132")
check(not br.bonus_ok("2", "PITCH FOCUS") and not br.bonus_ok("2", "FIELDING PLAY"),
      "...nor a PITCH FOCUS or a FIELDING PLAY")
check(br.bonus_ok("1", "SPEED BOOST") and br.bonus_ok("1", "POWER SWING"),
      "every one of them may be +1")
check(br.bonus_ok("2"), "and with NO label the loose rule stands — refusing a real "
                        "POWER SWING +2 for want of a label would be the worse error")
check(not br.power_ok(None) and not br.power_ok("x") and not br.bonus_ok(None),
      "and a non-digit is refused rather than raising")

print("11. CONTROL: the viewer really does use these, not private copies")
src = open(_os.path.join(_ROOT, "tools", "state_viewer.py"), encoding="utf-8").read()
check("import ban_read" in src or "from ban_read" in src,
      "tools/state_viewer.py imports ban_read — without this the module could be perfect "
      "and the viewer still wrong, which is the whole failure this file exists to stop")
# The viewer keeps two-line wrappers so its own call sites stay readable; what matters is
# that they DELEGATE rather than reimplement, because a private copy is exactly how the
# tested code and the running code drift apart with the suite green (CLAUDE.md 10.25).
for call in ("br.latch(", "br.rowkey(", "br.kind_of(", "br.boxes_for(", "br.values_for(",
             "br.power_ok(", "br.bonus_ok("):
    check(call in src, f"...and calls {call}) rather than keeping its own copy")
check("_STABLE[\"held\"]" not in src and "_STABLE.get(" not in src,
      "...and no longer reaches into the latch's state itself")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
