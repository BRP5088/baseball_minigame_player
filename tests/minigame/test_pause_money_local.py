"""THE MONEY, READ WITHOUT THE PAID MODEL.

read_balance_from_pause_menu() calls client.messages.create, and the paid model is OFF --
so the tracked balance, which is the money guard, had NO WAY to be checked against the game
at all. A guard nothing can verify is the shape this project keeps finding.

Two real frames, two capture geometries, both named. And the negative is the one that
matters: CLAUDE.md records a gameplay frame facing a blown-out white wall passing for a
pause menu, on a screen whose only number is the HEALTH coin -- which has been misread as
money three times and once reported the bankroll collapsing from $246 to $100.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import glob
import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

from PIL import Image
import pause_menu as pm

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def F(n):
    return _os.path.join(_ROOT, "test_fixtures", "pause_menu", n)


# NAMED, never globbed (CLAUDE.md section 2).
LIVE = F("money_196_2000x1125.png")        # captured live 2026-09-13, wallet 196
SAVE = F("load_last_save_selected.png")    # 1867x1050, wallet 246
WALL = F("gameplay_bright_wall.png")       # NOT a pause menu: a blown-out white wall

print("0. fixtures")
missing = [p for p in (LIVE, SAVE, WALL) if not _os.path.exists(p)]
check(not missing, f"all three present (missing: {[_os.path.basename(m) for m in missing]})")
if missing:
    raise SystemExit(1)
imgs = {p: Image.open(p).convert("RGB") for p in (LIVE, SAVE, WALL)}

print("\n1. IT READS THE MONEY, on BOTH capture geometries")
check(pm.read_money(imgs[LIVE]) == 196,
      f"the live 2000x1125 frame reads 196 (got {pm.read_money(imgs[LIVE])})")
check(pm.read_money(imgs[SAVE]) == 246,
      f"the 1867x1050 frame reads 246 (got {pm.read_money(imgs[SAVE])}) — which is what "
      f"Load Last Save restores, from a different capture size")

print("\n2. AND REFUSES A SCREEN THAT IS NOT THE PAUSE MENU")
check(pm.is_pause_screen(imgs[WALL]) is False,
      "the bright-wall frame is not a pause screen")
check(pm.read_money(imgs[WALL]) is None,
      "so no money is read off it — the only number on a gameplay frame is the HEALTH "
      "coin, and reading that as money once reported $246 collapsing to $100")

print("\n3. THE BOX SPANS BOTH GEOMETRIES, which one frame cannot show")
x0, y0, x1, y1 = pm.MONEY_BOX_FRAC
check(x0 <= 0.9036 and x1 >= 0.9475,
      f"x {x0}-{x1} covers the digits of BOTH frames (0.9036 and 0.9475) — the first "
      f"version ended at 0.947 and clipped the live frame's last digit")
check(y0 <= 0.1929 and y1 >= 0.2381,
      f"y {y0}-{y1} covers both (0.1929 and 0.2381) — the first version started at 0.205 "
      f"and cut the tops off")

print("\n4. TWO SCALES MUST AGREE, because a single read got it WRONG")
seen = []
for up in (4, 6):
    w, h = imgs[LIVE].size
    c = imgs[LIVE].convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * up, c.height * up), Image.LANCZOS)
    import ocr_glyphs
    t = ocr_glyphs.image_to_text(c, psm=6, whitelist="0123456789") or ""
    seen.append("".join(ch for ch in t if ch.isdigit()))
check(seen[0] == seen[1] == "196",
      f"both scales read 196 on the live frame ({seen}) — psm 7 read 106 there, a "
      f"confidently wrong BALANCE, which on the money guard is worse than no answer")

print("\n5. THE PAUSE-MENU GUARD, DRIVEN rather than fixture-tested")
# A mutant survived the fixture version: on the bright-wall frame the money box holds no
# digits, so deleting the guard changed nothing and the check stayed green. The guard's
# real job is a frame that DOES have a number in that box and is NOT the pause menu, and
# the way to test that is to drive it, not to hunt for such a frame.
_real = pm.is_pause_screen
try:
    pm.is_pause_screen = lambda _img: False
    got = pm.read_money(imgs[LIVE])
finally:
    pm.is_pause_screen = _real
check(got is None,
      f"with is_pause_screen saying NO, the live frame's plainly-readable 196 is refused "
      f"(got {got!r}) — a money read is only valid once the menu is confirmed open, "
      f"because toggle_pause does not always land")
check(pm.read_money(imgs[LIVE]) == 196, "...and it still reads once the guard says yes")

print("\n6. TWO SCALES THAT DISAGREE PRODUCE NO ANSWER")
# Also mutant-driven: on these fixtures a single read happens to be right, so "one read is
# enough" survived. Feed it two different answers and it must refuse.
calls = {"n": 0}
def _flaky(im, psm=6):
    calls["n"] += 1
    return "196" if calls["n"] == 1 else "106"
check(pm.read_money(imgs[LIVE], ocr=_flaky) is None,
      "196 then 106 yields None — which is the exact pair the shipped psm-7 reader produced")
calls["n"] = 0
def _steady(im, psm=6):
    return "196"
check(pm.read_money(imgs[LIVE], ocr=_steady) == 196,
      "...while two that agree are believed")

print("\n7. AND IT NEVER RETURNS SOMETHING A WALLET CANNOT HOLD")
check(pm.MONEY_MIN == 0 and pm.MONEY_MAX == 9999,
      f"the range is 0..9999 ({pm.MONEY_MIN}..{pm.MONEY_MAX})")

# --- IT MUST ACTUALLY BE CALLED, and the menu must always close --------------
# This reader was built, measured on both capture geometries, fully tested -- and had
# ZERO production callers. Both sites wanting a balance called
# read_balance_from_pause_menu, which is a PAID call; with the paid model off it raises,
# run_cycles swallows that and returns its hardcoded RELOAD_WALLET of 246 every
# cycle. So the only thing able to reconcile the tracked balance against the game was a
# constant, while "Load Last Save" keeps putting $246 back in the wallet and the tracked
# figure only ever marches down. A measurement built and never wired (10.1).
import orchestrator as _o

_saved = (_o.press, _o.wait_for_screen_to_settle, _o._fast_grab,
          pm.is_pause_screen, pm.read_money, _o.read_ban_counter)
_presses = []
try:
    _o.press = lambda k, *a, **kw: _presses.append(k)
    _o.wait_for_screen_to_settle = lambda *a, **k: True
    _o._fast_grab = lambda: "FRAME"
    pm.is_pause_screen = lambda img: True
    # The money path now refuses a BAN screen, so this block has to say which book
    # it is looking at. None = "not a ban screen", i.e. the pause book.
    _o.read_ban_counter = lambda img: None

    pm.read_money = lambda img, ocr=None: 196
    _presses.clear()
    _got = _o.read_balance_from_pause_menu()
    check(_got == 196,
          f"read_balance_from_pause_menu ignored the LOCAL reader and returned {_got}")
    check(_presses == ["toggle_pause", "toggle_pause"],
          f"the menu must be opened and closed exactly once each, got {_presses}")

    # ...and when the local reader abstains, the paid path raises (the model is off) --
    # the menu must STILL close. It used to close only AFTER the paid call, so any
    # exception from it left the game PAUSED for the rest of the run, and the symptom
    # looks like dead input at a healthy stream.
    pm.read_money = lambda img, ocr=None: None
    _presses.clear()
    try:
        _o.read_balance_from_pause_menu()
        check(False, "with the paid model off the paid path must raise, not answer")
    except Exception as _e:
        check(type(_e).__name__ == "PaidModelDisabled",
              f"expected PaidModelDisabled, got {_e!r}")
    check(_presses.count("toggle_pause") == 2,
          f"the pause menu was left OPEN when the read raised ({_presses}) — every "
          "press after this lands in a menu instead of the world")
finally:
    (_o.press, _o.wait_for_screen_to_settle, _o._fast_grab,
     pm.is_pause_screen, pm.read_money, _o.read_ban_counter) = _saved

# --- THE BAN SCREEN IS A NOTEBOOK PAGE TOO -----------------------------------
# is_pause_screen's negative population was a bright WALL (n=1). The ban book is a
# THIRD CLASS that was never in it -- 10.31's missing-class shape exactly. Censused
# over 10,239 frames: PAUSE 0.9263..0.9446 (n=14), BAN 0.7101..0.8587 (n=1140),
# everything else up to 0.9272. 1,122 of 1,140 ban frames clear PAGE_MIN_FRAC 0.80,
# and MENU_TEXT_MIN_FRAC cannot rescue it (ban 0.1224-0.4148 vs pause 0.0733-0.4309,
# complete overlap -- no threshold on that quantity separates two notebooks).
#
# Over 1,131 ban frames read_money returns a CONFIDENT WRONG balance on 5 ($7 x4,
# $1 x1) with both OCR scales agreeing. That is the "$246 -> $100" failure its own
# docstring exists to prevent, reached THROUGH the guard. Harmless while read_money
# had no callers; wiring it into the money path is what made it live.
_saved2 = (_o.press, _o.wait_for_screen_to_settle, _o._fast_grab,
           pm.is_pause_screen, pm.read_money, _o.read_ban_counter)
_p2 = []
try:
    _o.press = lambda k, *a, **kw: _p2.append(k)
    _o.wait_for_screen_to_settle = lambda *a, **k: True
    _o._fast_grab = lambda: "FRAME"
    pm.is_pause_screen = lambda img: True        # the guard that admits a ban screen
    pm.read_money = lambda img, ocr=None: 7      # the confident wrong value it gives there

    _o.read_ban_counter = lambda img: 2          # ...but the ban counter answers
    _p2.clear()
    try:
        _got2 = _o.read_balance_from_pause_menu()
        check(False, f"read the wallet off a BAN screen and returned ${_got2} — a "
                     "confident wrong balance is worse than none")
    except RuntimeError as _e:
        check("ban screen" in str(_e),
              f"refused for the wrong reason: {_e!r}")
    check(_p2.count("toggle_pause") == 2,
          f"refusing left the pause menu OPEN ({_p2})")

    # CONTROL: a real pause screen has no ban counter, and must still read.
    _o.read_ban_counter = lambda img: None
    pm.read_money = lambda img, ocr=None: 196
    _p2.clear()
    check(_o.read_balance_from_pause_menu() == 196,
          "CONTROL: a genuine pause screen must still be read — otherwise this rule "
          "disables the money path entirely and reads like a working guard (10.1)")
finally:
    (_o.press, _o.wait_for_screen_to_settle, _o._fast_grab,
     pm.is_pause_screen, pm.read_money, _o.read_ban_counter) = _saved2

# ...and the underlying fact, on real frames, so the census above is not just prose.
_ban_fx = sorted(glob.glob(os.path.join(_ROOT, "test_fixtures", "ban_digits", "*.jpg")))
_admitted = [os.path.basename(f) for f in _ban_fx
             if pm.is_pause_screen(Image.open(f))]
check(_admitted,
      f"fixture error: no ban fixture is admitted by is_pause_screen ({len(_ban_fx)} "
      "scanned) — then this whole section is guarding nothing and the census is stale")
print(f"  (is_pause_screen admits {len(_admitted)} of {len(_ban_fx)} ban fixtures: "
      f"{_admitted})")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
