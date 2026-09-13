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

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
