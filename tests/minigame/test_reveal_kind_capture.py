"""The reveal frame for a tactics play is kept, and it can never break the turn.

WHY THIS EXISTS (OPEN-24). `reveal_cards.TACTICS_KIND_MIN` (0.75) gates the
tactics-KIND reader and stands on 48 frames from TWO matches. Meanwhile
`match_log.jsonl` holds 148 rows of GENUINE ground truth -- `our_tactics_kind` is
`decision.tactics_card.kind`, the card this code chose and played -- and not one of
them has a surviving frame, because `SCREENSHOT_KEEP_RUNS` is 3 and the append-only
row outlives the picture. The log remembers what we played; the disk forgot what it
looked like.

`record_reveal_kind` closes that going forward. It writes the frame the reader was
handed, labelled by the engine's own choice, so the corpus widens by ~4 frames a
match with no new capture.

TWO PROPERTIES MATTER AND THEY PULL APART, which is why both are pinned here:

  it must WRITE          or the corpus never grows and OPEN-24 stays open with a
                         function that looks like it closed it -- 10.1's family
  it must NEVER RAISE    it is called from the turn loop, between the play and the
                         reveal read, on a match that has been debited $50. A
                         corpus frame is worth a slower census later; it is not
                         worth an exception there

The label is not circular (10.22): the OPPONENT's kind is READ by the same reader
this corpus scores, and carries the bonus-of-3 values RULES.md says cannot exist.
Ours is chosen. Only ours is written.
"""
import os
import re
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

from PIL import Image

import orchestrator

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def _img(w=640, h=360):
    return Image.new("RGB", (w, h), (30, 40, 50))


INFO = {"our_tactics_kind": "swing_boost", "our_power": 7}

# --- it writes, and the filename carries the label -------------------------
with tempfile.TemporaryDirectory() as d:
    name = orchestrator.record_reveal_kind(_img(), INFO, out_dir=d)
    on_disk = sorted(os.listdir(d))
    check(name is not None and len(on_disk) == 1,
          f"a tactics play writes exactly one frame (wrote {on_disk})")
    check(bool(name) and name.startswith("swing_boost_"),
          f"the filename carries the KIND, so the corpus is self-labelling ({name})")
    check(bool(name) and name.endswith(".jpg"),
          "written as .jpg, matching the 48 frames already in that corpus")
    if on_disk:
        got = Image.open(os.path.join(d, on_disk[0]))
        check(got.size == (640, 360), f"the frame itself is stored, not a crop ({got.size})")

# --- it does NOT write when there was no tactics card ----------------------
for label, info in (("no tactics card played", {"our_tactics_kind": None}),
                    ("no matchup info at all", None),
                    ("empty matchup info", {})):
    with tempfile.TemporaryDirectory() as d:
        r = orchestrator.record_reveal_kind(_img(), info, out_dir=d)
        check(r is None and not os.listdir(d), f"writes nothing when {label}")

with tempfile.TemporaryDirectory() as d:
    r = orchestrator.record_reveal_kind(None, INFO, out_dir=d)
    check(r is None and not os.listdir(d), "writes nothing when there is no frame")

# --- it can NEVER raise into the turn loop ---------------------------------
class _Explodes:
    """Every attribute access raises, like a frame object that has gone bad."""
    def __getattr__(self, k):
        raise RuntimeError("boom")


try:
    r = orchestrator.record_reveal_kind(_Explodes(), INFO, out_dir=tempfile.mkdtemp())
    check(r is None, "a frame that raises on use returns None instead of propagating")
except Exception as e:
    check(False, f"it RAISED into the caller: {type(e).__name__}: {e}")

try:
    r = orchestrator.record_reveal_kind(_img(), INFO, out_dir="/nonexistent/\0bad")
    check(r is None, "an unwritable directory returns None instead of propagating")
except Exception as e:
    check(False, f"it RAISED on a bad path: {type(e).__name__}: {e}")

# --- under BASEBALL_TEST_RUN the REAL corpus is never touched --------------
# Same shape as test_caches_not_written_in_tests: the suite must not be able to
# append to a tracked corpus. out_dir is the explicit opt-in the checks above use.
check(os.environ.get("BASEBALL_TEST_RUN") == "1", "CONTROL: the test flag is set")
_before = (sorted(os.listdir(orchestrator.REVEAL_KIND_DIR))
           if os.path.isdir(orchestrator.REVEAL_KIND_DIR) else None)
r = orchestrator.record_reveal_kind(_img(), INFO)          # no out_dir
_after = (sorted(os.listdir(orchestrator.REVEAL_KIND_DIR))
          if os.path.isdir(orchestrator.REVEAL_KIND_DIR) else None)
check(r is None and _before == _after,
      "with no out_dir under BASEBALL_TEST_RUN it writes NOTHING to the real corpus")

# --- it is actually WIRED into the turn loop ------------------------------
# A recorder nothing calls is OPEN-24 still open behind a function that looks
# like it closed it. Assert on the call site, next to the frame it needs.
_src = open(os.path.join(_ROOT, "orchestrator.py"), encoding="utf-8").read()
_code = "\n".join(l.split("#", 1)[0] for l in _src.splitlines())
check(_code.count("record_reveal_kind(reveal_img, matchup_info)") == 1,
      "it is CALLED from the turn loop, exactly once")
# MATCH THE CALL, NOT THE `def`. The first version searched for
# "record_reveal_kind(reveal_img" and found the function's own signature 6,400
# lines earlier, so the ordering read backwards and this check failed on correct
# code. CLAUDE.md 10.9 records the same collision passing a wiring assertion that
# should have failed -- same root cause, opposite sign. The full call, with the
# closing paren after matchup_info, cannot match the def (which has out_dir next).
_CALL = "record_reveal_kind(reveal_img, matchup_info)"
# MATCHED BY SHAPE, NOT BY THE CALLEE'S NAME. This read
# `_code.find("reveal_img = reveal_frame_for")` and went to -1 the moment that call
# site was renamed to settled_reveal_frame() -- a real fix (the reveal was being read
# while the cards were still flying in), reported here as a failure of the ordering
# property, which had not changed at all. The property is WHERE the frame is bound
# relative to the two uses below it; which function produces it is not this test's
# business. A dead anchor is -1, and -1 < _j is TRUE, so the `-1 < _i` term below is
# what keeps this from passing vacuously once the name stops matching.
_m = re.search(r"^\s*reveal_img\s*=\s*\w+\(", _code, re.M)
_i = _m.start() if _m else -1
_j = _code.find(_CALL)
_k = _code.find("read_matchup_reveal(img=reveal_img)")
check(-1 < _i < _j < _k,
      f"called AFTER the frame exists and BEFORE the reveal is read, so it uses the "
      f"frame the reader is handed and adds no capture (offsets {_i} < {_j} < {_k})")
check(_code.count("def record_reveal_kind(") == 1 and _CALL not in
      _code[_code.find("def record_reveal_kind("):_code.find("def record_local_hand(")],
      "CONTROL: the anchor above matches the CALL, never the def line")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
