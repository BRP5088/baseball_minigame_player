"""I-18(b): the reveal frame is kept BESIDE the row it produced, and capped.

WHAT WAS MISSING (OPEN-24). `record_reveal_kind` already wrote the frame and
`tests/minigame/test_reveal_kind_capture.py` already pinned that it writes and that it
never raises. Neither closed the gap the ticket is actually about: `match_log.jsonl`
holds 148 rows of ground truth (`our_tactics_kind` is the card the ENGINE chose) and
NOT ONE has a surviving frame, because `SCREENSHOT_KEEP_RUNS` is 3 and the append-only
row outlives the picture. A frame with no row, or a row with no frame, is half the
evidence either way: the kind reader is scored by comparing a READING of the frame
against the row's label, so the two have to be joined.

So this file drives run() END TO END -- the same harness the debit and motion tests
use -- and asserts on what reaches `log_matchup`, not on the recorder in isolation. A
recorder that writes perfectly while the row it belongs to carries no pointer is
10.1's family: the corpus grows, the census still cannot use it, and nothing fails.

FOUR PROPERTIES, and they pull in different directions:

  the frame is KEPT and the ROW POINTS AT IT   or OPEN-24 stays open
  a turn with NO tactics card writes NOTHING   the label is what makes the frame
                                               worth keeping; an unlabelled frame is
                                               just disk
  the offline suite writes NOTHING             test_fixtures/ is TRACKED and
                                               test_no_side_effects.py watches it
  the directory is CAPPED, by REFUSING         it is on the $50 turn loop and it
                                               writes into the repo

THE CAP REFUSES RATHER THAN PRUNES on purpose, and the test pins that direction:
pruning oldest-first is precisely how the 148 rows lost their frames, and on this
corpus the oldest frames are the RARE kinds (the log's rarest are fielding 8 and
speed 6) -- so a pruning cap would eat the only examples the census needs.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)
# ...and this file's OWN directory, so `_run_harness` imports whether the file
# is run directly, from the project root, or re-executed in a subprocess by
# tests/harness/test_no_side_effects.py.
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import contextlib
import io
import os
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# Set before ANY project import: it is what holds every input path off.
os.environ["BASEBALL_TEST_RUN"] = "1"

# _run_harness FIRST among the project imports: it redirects the diagnostics dir,
# the match log and the deal log at a temp dir and only THEN imports orchestrator.
# Its check() is COND-FIRST -- `def check(cond, msg)` -- which is the half of the
# suite's nine signatures that reads naturally; calling it name-first would put a
# truthy string in the `cond` slot and the check could never fail (CLAUDE.md 5).
from _run_harness import Harness, check, failures
import orchestrator as o
from PIL import Image

# The deal gate spends REAL wall clock against a harness that never produces a
# readable hand, which would push this file at the suite's 300 s ceiling.
o.wait_for_hand_deal = lambda *a, **k: True

# OUR side is the engine's own choice and is never read from the screen, which is
# what makes the filename ground truth rather than the reader marking its own
# homework (10.22).
_INFO_BOOST = {"phase": "batting", "our_card_name": "Johnny Drawers", "our_power": 7,
               "our_secondary": 1, "our_tactics_bonus": 0,
               "our_tactics_kind": "swing_boost",
               "runners_before": 0, "score_before": 0}
_INFO_PLAIN = dict(_INFO_BOOST, our_tactics_kind=None)

_OURS = {"kind": "player", "name": "Johnny Drawers", "power": 7, "secondary": 1}
_THEIRS = {"kind": "player", "name": "Rube Sharp", "power": 4, "secondary": 2}
# What opponent_from_reveal() returns for that faceoff. `_ours_power_seen` must
# match the power we played or run() treats the turn as a misfire and logs nothing.
_OPP_LOCAL = {"opp_power": 4, "opp_tactics_bonus": 0, "opp_tactics_kind": None,
              "_ours_power_seen": 7}


class _Explodes:
    """A frame object that has gone bad: every attribute access raises."""
    def __getattr__(self, k):
        raise RuntimeError("boom")


def _play_one_turn(info, frame_dir, img=None):
    """Drive run() through ONE logged at-bat. Returns the rows log_matchup got.

    `frame_dir` is None to leave the seam ABSENT, which is the state a real offline
    test run is in and the state the suite must be safe in.
    """
    rows = []
    _real_log, _real_settled = o.log_matchup, o.settled_reveal_frame
    _had = os.environ.get(o.REVEAL_KIND_DIR_ENV)
    o.log_matchup = rows.append
    # settled_reveal_frame is the one thing the harness cannot supply: offline it
    # falls through to the re-grab loop and answers None, so the recorder's
    # `reveal_img is None` branch would make every check below pass vacuously.
    o.settled_reveal_frame = lambda *a, **k: (
        img if img is not None else Image.new("RGB", (1920, 1080), (20, 30, 40)))
    if frame_dir is None:
        os.environ.pop(o.REVEAL_KIND_DIR_ENV, None)
    else:
        os.environ[o.REVEAL_KIND_DIR_ENV] = frame_dir
    try:
        Harness(["turn"] + ["other"] * 8, revealed=[_OURS, _THEIRS],
                opp_local=dict(_OPP_LOCAL),
                play_results=[(True, dict(info))]).run(target_wins=99)
    finally:
        o.log_matchup, o.settled_reveal_frame = _real_log, _real_settled
        os.environ.pop(o.REVEAL_KIND_DIR_ENV, None)
        if _had is not None:
            os.environ[o.REVEAL_KIND_DIR_ENV] = _had
    return rows


# --- 1. a tactics play: one frame, and the ROW points at it -----------------
with tempfile.TemporaryDirectory() as d:
    rows = _play_one_turn(_INFO_BOOST, d)
    kept = sorted(os.listdir(d))
    check(len(rows) == 1,
          f"a boosted at-bat logged {len(rows)} rows, expected 1 — the frame cannot "
          f"be joined to a row that was never written")
    check(len(kept) == 1 and kept[0].startswith("swing_boost_")
          and kept[0].endswith(".jpg"),
          f"one frame named by the KIND the engine chose, got {kept}")
    _ref = rows[0].get("reveal_frame") if rows else None
    check(_ref is not None,
          "the logged row carries NO reveal_frame — OPEN-24 is exactly this: the row "
          "survives and nothing says which picture it came from")
    if _ref and kept:
        check(os.path.basename(_ref) == kept[0],
              f"the row points at {_ref!r}, which is not the frame that was written "
              f"({kept[0]})")
        check(not os.path.isabs(_ref),
              f"reveal_frame is an ABSOLUTE path ({_ref!r}) — the corpus moves with "
              f"the checkout, so the row must not name this machine")
        check(os.path.exists(os.path.join(_ROOT, _ref)),
              f"reveal_frame {_ref!r} does not resolve against the project root")
    if kept:
        _im = Image.open(os.path.join(d, kept[0]))
        check(_im.size == (1920, 1080),
              f"the WHOLE frame is stored, not a crop ({_im.size}) — the kind reader "
              f"searches its own zones and needs the full picture")

# The shipped directory, pinned without writing into it: `auto/`, not `live/`.
# live/ is hand-adjudicated (five named fixtures, two of which supplied templates,
# scored with an exclusion list), so an unattended run appending there buries a
# curated set in frames nobody has looked at.
check(os.path.relpath(os.path.join(o.REVEAL_KIND_DIR, "x.jpg"), _ROOT)
      == os.path.join("test_fixtures", "reveal_kind_truth", "auto", "x.jpg"),
      f"frames land in {o.REVEAL_KIND_DIR!r}, not test_fixtures/reveal_kind_truth/auto")

# --- 2. no tactics card: no frame, no pointer -------------------------------
with tempfile.TemporaryDirectory() as d:
    rows = _play_one_turn(_INFO_PLAIN, d)
    check(len(rows) == 1,
          f"an unboosted at-bat logged {len(rows)} rows, expected 1 — CONTROL: the "
          f"turn must still be logged, only the frame is skipped")
    check(not os.listdir(d),
          f"a turn with NO tactics card still wrote {os.listdir(d)} — the label is "
          f"the whole value of the frame, and there is no label here")
    check(rows and "reveal_frame" not in rows[0],
          f"an unboosted row carries a reveal_frame: {rows[0] if rows else None}")

# --- 3. the seam absent under BASEBALL_TEST_RUN: the real corpus is untouched -
check(os.environ.get("BASEBALL_TEST_RUN") == "1", "CONTROL: the test flag is set")
_before = (sorted(os.listdir(o.REVEAL_KIND_DIR))
           if os.path.isdir(o.REVEAL_KIND_DIR) else None)
rows = _play_one_turn(_INFO_BOOST, None)
_after = (sorted(os.listdir(o.REVEAL_KIND_DIR))
          if os.path.isdir(o.REVEAL_KIND_DIR) else None)
check(_before == _after,
      f"the suite wrote into the REAL corpus with no seam set ({_before} -> {_after}) "
      f"— test_fixtures/ is tracked and test_no_side_effects.py watches it")
check(rows and "reveal_frame" not in rows[0],
      f"no frame was written, yet the row claims one: {rows[0] if rows else None}")

# --- 4. the cap REFUSES, and says so ----------------------------------------
with tempfile.TemporaryDirectory() as d:
    for i in range(o.REVEAL_KIND_MAX_FILES):
        open(os.path.join(d, f"swing_boost_{i}.jpg"), "w").close()
    info = dict(_INFO_BOOST)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = o.record_reveal_kind(Image.new("RGB", (640, 360)), info, out_dir=d)
    _n = len(os.listdir(d))
    check(r is None and _n == o.REVEAL_KIND_MAX_FILES,
          f"a full corpus was written to anyway: returned {r!r}, {_n} files against "
          f"a cap of {o.REVEAL_KIND_MAX_FILES}")
    check("reveal_frame" not in info,
          f"the row was stamped with a frame that was never written: {info}")
    check("[reveal]" in buf.getvalue() and str(o.REVEAL_KIND_MAX_FILES) in buf.getvalue(),
          f"the refusal was SILENT — a corpus that has quietly stopped growing reads "
          f"exactly like one nobody is playing matches for. Printed: {buf.getvalue()!r}")
    # And the refusal must not be a prune: 10.1 aside, the oldest frames here are
    # the RARE kinds, which are the only ones the census is short of.
    check(os.path.exists(os.path.join(d, "swing_boost_0.jpg")),
          "the cap PRUNED the oldest frame — that is how the 148 rows lost their "
          "pictures in the first place")

# --- 5. a frame that raises must not cost the TURN --------------------------
# The caller's own except swallows anything this raises and the turn is then simply
# not logged, so "never raises" is not a property of the recorder alone: it is
# measurable at the row.
with tempfile.TemporaryDirectory() as d:
    rows = _play_one_turn(_INFO_BOOST, d, img=_Explodes())
    check(len(rows) == 1,
          f"a frame that raises on use cost the ROW ({len(rows)} logged, expected 1) "
          f"— a corpus frame is worth a slower census later; it is not worth the "
          f"at-bat of a $50 match")
    check(rows and "reveal_frame" not in rows[0],
          f"the row points at a frame the save never wrote: "
          f"{rows[0].get('reveal_frame') if rows else None}")
    check(not os.listdir(d), f"a failed save left something behind: {os.listdir(d)}")

print("OK: I-18(b) — the reveal frame is kept for every tactics play, the row points "
      "at it, an unboosted turn keeps nothing, the offline suite writes nothing "
      "without its seam, the 200-file cap refuses out loud instead of pruning, and a "
      "frame that raises costs the frame but never the at-bat")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} reveal-frame failure(s)")
