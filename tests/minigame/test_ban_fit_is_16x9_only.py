"""THE FITTED BAN GEOMETRY IS 16:9 ONLY, AND THAT IS ENFORCED RATHER THAN ASSUMED.

ban_grid derives a card's height as CARD_ASPECT * column_width * (w / h), so the frame's
ASPECT is an input to the row fit -- and every constant in it was measured at 16:9. On an
archived 2000x1292 frame (aspect 1.548) it fits rows at 0.382 / 0.710 where the true ones
are 0.195 / 0.478. Different cards, not a small error.

This was not caught by four phases of live comparison, because the live rig captures only
16:9. It was caught the moment USE_FITTED_BAN_GRID was flipped, by an archived fixture:
test_ocr_ban_card went from 2 abstentions to 18. CLAUDE.md section 3 says a reader is
checked at BOTH geometries; "it does not happen today" is how a rig change becomes a silent
wrong answer later.
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
import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def F(*p):
    return _os.path.join(_ROOT, *p)


# NAMED, never globbed: these two exist to be the two geometries, and a glob over a
# directory a live run writes to is how a fixture population changes under a test
# (CLAUDE.md section 2).
WIDE = F("test_fixtures", "ban_grid", "scroll_p00.png")          # 2000x1125, 16:9
TALL = F("test_fixtures", "20260824_200601_124.jpg")             # 2000x1292, 1.548
missing = [p for p in (WIDE, TALL) if not _os.path.exists(p)]
print("0. fixtures")
check(not missing, f"both geometries are present (missing: {missing})")
if missing:
    raise SystemExit(1)

print("\n1. THE TWO FIXTURES REALLY ARE DIFFERENT SHAPES")
w = Image.open(WIDE).convert("RGB")
t = Image.open(TALL).convert("RGB")
aw, at_ = w.size[0] / w.size[1], t.size[0] / t.size[1]
check(abs(aw - 16 / 9) < 0.01, f"{_os.path.basename(WIDE)} is 16:9 ({aw:.3f})")
check(abs(at_ - 16 / 9) > 0.15,
      f"{_os.path.basename(TALL)} is NOT ({at_:.3f}) — without this the test proves nothing")

print("\n2. THE GUARD ROUTES BY SHAPE")
check(o._ban_frame_is_16x9(w) is True, "a 16:9 frame is admitted to the fitted path")
check(o._ban_frame_is_16x9(t) is False, "a 1.548 frame is not")
o._FIT_MEMO.update({"key": None, "rows": None})
check(o._fitted_ban_rows(t) is None,
      "_fitted_ban_rows REFUSES the wrong shape rather than returning a fit for it")
o._FIT_MEMO.update({"key": None, "rows": None})
check(o._fitted_ban_rows(w) is not None, "...and still fits the right one")

print("\n3. THE CROP FOLLOWS, which is what actually reads a card")
was = o.USE_FITTED_BAN_GRID
try:
    o.USE_FITTED_BAN_GRID = True
    o._FIT_MEMO.update({"key": None, "rows": None})
    tall_crop = o.get_ban_grid_card_crop(t, 0, 0)
    o._FIT_MEMO.update({"key": None, "rows": None})
    wide_crop = o.get_ban_grid_card_crop(w, 0, 0)
    o.USE_FITTED_BAN_GRID = False
    o._FIT_MEMO.update({"key": None, "rows": None})
    tall_shipped = o.get_ban_grid_card_crop(t, 0, 0)
    wide_shipped = o.get_ban_grid_card_crop(w, 0, 0)
finally:
    o.USE_FITTED_BAN_GRID = was
    o._FIT_MEMO.update({"key": None, "rows": None})
check(tall_crop.size == tall_shipped.size,
      f"with the flag ON, the 1.548 frame still gets the SHIPPED crop "
      f"({tall_crop.size} == {tall_shipped.size})")
check(wide_crop.size != wide_shipped.size,
      f"while the 16:9 frame gets the fitted one ({wide_crop.size} != {wide_shipped.size}) "
      f"— otherwise the flag would be doing nothing and this test would pass anyway")

print("\n4. AND THE NAME STILL READS ON THE SHAPE THE FIT CANNOT HANDLE")
# The regression in one line: 18 abstentions became 2 again once the guard landed.
was = o.USE_FITTED_BAN_GRID
try:
    o.USE_FITTED_BAN_GRID = True
    o._FIT_MEMO.update({"key": None, "rows": None})
    card = o.ocr_ban_card_name(o.get_ban_grid_card_crop(t, 0, 0))
finally:
    o.USE_FITTED_BAN_GRID = was
    o._FIT_MEMO.update({"key": None, "rows": None})
check(getattr(card, "name", None) == "Rube Sharp",
      f"the 1.548 frame's r0c0 still resolves to Rube Sharp with the flag ON "
      f"(got {getattr(card, 'name', None)!r}) — it read None before the guard")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
