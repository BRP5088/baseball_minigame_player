"""tools/crawl_sheet.py must not touch BASEBALL_TEST_RUN, at import or ever.

WHAT THIS GUARDS. crawl_sheet used to `os.environ.pop("BASEBALL_TEST_RUN", None)`
unconditionally at import time -- CLAUDE.md 10.1's guard-that-disables-itself.
tools/match_crawl.py imports it (crawl_sheet.panel at ~line 753, crawl_sheet
itself at ~804) while a live crawl session may be running under
BASEBALL_TEST_RUN=1 in the SAME process as other tests, and that import silently
switched off the offline input lockout for the rest of the process -- every
other safety check in this project (the emission census, the three/four-path
lockout in input_controller/ensure_stream/inject_reset) trusts that flag to stay
set once a test process has set it.

WHAT THE FIX LOOKS LIKE. crawl_sheet.build() now refuses under BASEBALL_TEST_RUN
only at the point it would actually grab a fresh frame (img is None), mirroring
match_crawl.py's own CRAWL_DRIVE_IN_TESTS / _refuse_if_test_run() shape. Handed
an existing frame (the normal call shape from match_crawl.py), it never touches
the environment or the console at all.

MUTATION TEST: restoring the import-time pop makes case (a) fail; deleting the
refusal from build() makes case (b) fail.
"""
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        ok = False


os.environ["BASEBALL_TEST_RUN"] = "1"

# ---- (a) importing crawl_sheet must leave the flag exactly as it found it ----
if "crawl_sheet" in sys.modules:
    del sys.modules["crawl_sheet"]
import crawl_sheet  # noqa: E402

check("importing crawl_sheet under BASEBALL_TEST_RUN=1 leaves it set",
      os.environ.get("BASEBALL_TEST_RUN") == "1")

# ---- (b) build() with no frame supplied refuses under the flag ----
refused = False
try:
    crawl_sheet.build()
except RuntimeError as e:
    refused = "BASEBALL_TEST_RUN" in str(e)
except Exception as e:
    # some other failure (e.g. no display/capture backend) does NOT prove the
    # guard fired -- only a RuntimeError naming the flag counts
    check(f"build() with no frame raised the flag-refusal, not "
          f"{type(e).__name__}: {e}", False)
    refused = None

if refused is not None:
    check("build() with no frame refuses under BASEBALL_TEST_RUN "
          "(CRAWL_SHEET_DRIVE_IN_TESTS unset)", refused)

check("BASEBALL_TEST_RUN is still set after the refused call "
      "(build() must not pop it on the way out either)",
      os.environ.get("BASEBALL_TEST_RUN") == "1")

# ---- (c) CRAWL_SHEET_DRIVE_IN_TESTS=True + a stubbed capture runs build()'s own logic ----
from PIL import Image
import orchestrator as o

stub_img = Image.new("RGB", (1920, 1080), (40, 40, 40))
_orig_grab = o._fast_grab
_orig_crop = o.crop_gameplay_regions
_orig_flag = crawl_sheet.CRAWL_SHEET_DRIVE_IN_TESTS
grabbed = []


def _stub_grab():
    grabbed.append(True)
    return stub_img


def _stub_crop(img):
    return []  # no hand/scoreboard/base crops -- exercises the "nothing readable" path


o._fast_grab = _stub_grab
o.crop_gameplay_regions = _stub_crop
crawl_sheet.CRAWL_SHEET_DRIVE_IN_TESTS = True
try:
    tmp_out = os.path.join(_ROOT, "overnight", "_test_crawl_sheet_tmp.png")
    dest = crawl_sheet.build(out=tmp_out)
    check("build() under CRAWL_SHEET_DRIVE_IN_TESTS=True with a stubbed capture "
          "produces a sheet instead of refusing", os.path.exists(dest))
    check("the stubbed capture was actually reached "
          "(build() didn't silently skip the capture path)", len(grabbed) >= 1)
    if os.path.exists(dest):
        os.remove(dest)
finally:
    o._fast_grab = _orig_grab
    o.crop_gameplay_regions = _orig_crop
    crawl_sheet.CRAWL_SHEET_DRIVE_IN_TESTS = _orig_flag

check("BASEBALL_TEST_RUN is STILL set after the opt-in drive path "
      "(CRAWL_SHEET_DRIVE_IN_TESTS never unsets it)",
      os.environ.get("BASEBALL_TEST_RUN") == "1")

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
