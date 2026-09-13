"""THE DIAMOND READER LIES ON A BAN SCREEN, AND NO THRESHOLD FIXES IT.

read_base's rule is "a power disc and no diamond coin = a card is standing on this base".
On a BAN SCREEN the three base crops land on the GRID'S CARDS, which are exactly that: a
power disc, no coin. So it reports a runner, and then reads a REAL shield badge off the
wrong card and calls it that runner's speed. It is CLAUDE.md 10.23 -- a reader handed the
wrong crop -- not a weak recogniser, which is why the answer is context and not a constant.

WHY NOT JUST RAISE SHIELD_MIN. Measured over the frames read_ban_counter labels as ban
screens (a DIFFERENT detector from the one under test, so this is not 10.31): 133 ban
frames, 62 of 399 base crops called occupied, 25 returning a confident speed, worst 0.782.
The true-runner population's p05 is 0.857. That leaves a 0.075 band with a real 5% tail
already inside it -- moving the gate buys this at the price of live runners, and 10.4 wants
a threshold between two populations, not inside one.

WHICH READER IS THE GATE. Over those ban frames the hand reader returned a hand ZERO times,
against 116 of the 255 non-ban frames beside them; read_phase measures identically (0 and
112). Either would work. The hand reader is chosen because local_game_state's own ladder
reaches screen="turn" through it, so a diagnostic and the live path cannot disagree about
what a turn screen is -- and section 4 pins exactly that coupling.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, ast, io, contextlib
os.environ["BASEBALL_TEST_RUN"] = "1"
from PIL import Image
import orchestrator as o, local_state as ls, local_hand

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def F(*parts):
    return _os.path.join(_ROOT, "test_fixtures", *parts)


# Ban screens and turn screens, named rather than globbed -- CLAUDE.md's rule that a test
# must never glob a directory a live run writes to.
BAN = [F("screens", "ban_screen__0.jpg"), F("screens", "ban_screen__1.jpg"),
       F("screens", "ban_screen__2.jpg"), F("ban_screen", "ban_0of3_1920x1080.jpg"),
       F("ban_screen", "ban_0of3_2000x1125.jpg"), F("ban_scan", "20260828_140315_271.jpg"),
       F("ban_ocr", "20260828_140320_608.jpg"), F("give_up", "negative_ban_screen.jpg"),
       F("harvest", "f0011.jpg"), F("harvest", "f0035.jpg")]
TURN = [F("give_up", "negative_gameplay_turn.jpg"),
        F("prompt_detector", "20260828_140623_689.jpg"),
        F("prompt_detector", "20260828_140652_622.jpg"),
        F("prompt_detector", "20260828_140708_034.jpg"),
        F("reveal_episode", "facedown_t0110.46.jpg"),
        F("reveal_trigger", "facedown_runner_on_first.jpg")]


def sub(im, name):
    x0, y0, x1, y1 = o.GAMEPLAY_REGIONS_FRAC[name]
    w, h = im.size
    return im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


_quiet = io.StringIO()

print("0. the fixtures are all present and are full frames")
missing = [p for p in BAN + TURN if not _os.path.exists(p)]
check(not missing, f"every named fixture exists (missing: {missing})")
if missing:
    raise SystemExit(1)
check(len(BAN) >= 8 and len(TURN) >= 5,
      f"and the populations are not empty ({len(BAN)} ban, {len(TURN)} turn) — a census "
      f"of nothing passes every check below")

print("1. the gate REFUSES a ban screen")
with contextlib.redirect_stdout(_quiet):
    ban_open = {p: Image.open(p).convert("RGB") for p in BAN}
    turn_open = {p: Image.open(p).convert("RGB") for p in TURN}
    ban_verdict = {p: o.on_turn_screen(sub(im, "hand")) for p, im in ban_open.items()}
    turn_verdict = {p: o.on_turn_screen(sub(im, "hand")) for p, im in turn_open.items()}
leaks = [_os.path.basename(p) for p, v in ban_verdict.items() if v]
check(not leaks, f"on_turn_screen is False on every ban fixture (leaked: {leaks})")

print("2. THE CONTROL: it is a gate, not a wall")
blocked = [_os.path.basename(p) for p, v in turn_verdict.items() if not v]
check(not blocked,
      f"on_turn_screen is True on every real turn fixture (wrongly blocked: {blocked}) — "
      f"without this, 'always False' passes section 1 perfectly")

print("3. ANTI-VACUITY: the hole is real, and these fixtures exercise it")
# If no ban fixture actually produced a false speed, sections 1-2 would pass while
# guarding nothing. This is the defect, reproduced.
false_speeds = []
with contextlib.redirect_stdout(_quiet):
    for p, im in ban_open.items():
        for b in ("third", "second", "first"):
            rb = ls.read_base(sub(im, f"{b}_base"), b)
            if rb["occupied"] and rb["speed"] is not None:
                false_speeds.append((rb["speed_score"], rb["speed"], b, _os.path.basename(p)))
false_speeds.sort(reverse=True)
check(len(false_speeds) >= 3,
      f"read_base still invents runner speeds on these ban fixtures ({len(false_speeds)} "
      f"of {len(BAN) * 3} base crops) — this is what the gate is for")
worst = false_speeds[0][0] if false_speeds else 0.0
# LITERALS, not the constant under discussion (CLAUDE.md 10.11). 0.70 is below the worst
# measured false read (0.765 on these committed fixtures, 0.782 over the full 133-frame
# ban census) and comfortably above the empty-base maximum of 0.592.
check(worst >= 0.70,
      f"...and the worst of them scores {worst:.3f}, well inside the CONFIDENT band")
check(local_hand.SHIELD_MIN == 0.69,
      f"SHIELD_MIN is still 0.69 ({local_hand.SHIELD_MIN}) — if this changed, the band "
      f"above was re-derived somewhere else and this file needs re-measuring, not editing")

print("4. the gate is the SAME reader the live ladder uses to say screen='turn'")
# The point of this section is the COUPLING, not the reader. If on_turn_screen is ever
# re-based on some other evidence, a tool can call a frame a turn screen that
# local_game_state would not (or the reverse), and the sheet stops describing the run.
_src = io.open(_os.path.join(_ROOT, "orchestrator.py"), encoding="utf-8").read()
_tree = ast.parse(_src)
_fns = {n.name: n for n in ast.walk(_tree) if isinstance(n, ast.FunctionDef)}
check("on_turn_screen" in _fns and "local_game_state" in _fns,
      "both functions exist to compare")


def _calls(fn):
    return {getattr(n.func, "attr", getattr(n.func, "id", ""))
            for n in ast.walk(fn) if isinstance(n, ast.Call)}


check("local_hand_cards" in _calls(_fns["on_turn_screen"]),
      "on_turn_screen decides with local_hand_cards")
check("local_hand_cards" in _calls(_fns["local_game_state"]),
      "...and local_game_state reaches screen='turn' through the same call")
# ...and read_phase abstains on a ban screen too, recorded so nobody re-derives it as a
# 'better' gate. This is a measurement, not a preference.
with contextlib.redirect_stdout(_quiet):
    phase_confident = [p for p, im in ban_open.items()
                       if ls.read_phase(sub(im, "hand"))[0] is not None]
check(not phase_confident,
      f"read_phase also abstains on every ban fixture ({len(phase_confident)} answered) — "
      f"both readers refuse; the hand one is used for the coupling above")

print("5. the three diagnostics consult the gate")
TOOLS = ["tools/state_viewer.py", "tools/match_crawl.py", "tools/crawl_sheet.py"]
for rel in TOOLS:
    path = _os.path.join(_ROOT, rel)
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    called = any(isinstance(n, ast.Call) and
                 getattr(n.func, "attr", getattr(n.func, "id", "")) == "on_turn_screen"
                 for n in ast.walk(tree))
    check(called, f"{rel} calls on_turn_screen()")
check(len(TOOLS) == 3, "and all three were scanned — an empty list passes vacuously")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
