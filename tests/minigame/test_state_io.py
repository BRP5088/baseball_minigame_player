"""Tests for state persistence and parsing helpers.

These had no coverage despite guarding the two things that survive a crash:
the win/loss/balance record, and the learned roster. Several QA findings landed
here (atomic writes, corrupt-file tolerance, shape validation), so they get
regression tests rather than trusting the fix stayed fixed.

Offline: no API calls, no PS5 input, all file work in a temp dir.
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


import json
import os
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")   # the suite exports it; this file
# manipulates the flag itself below, so it must start from the same state standalone.
import orchestrator
from decision_engine import TacticsType
from orchestrator import (_atomic_write_json, extract_json, hand_to_cards,
                          load_progress, save_progress)

failures = []
tmp = tempfile.mkdtemp(prefix="autobaseball_test_")

# ------------------------------------------------------- progress round-trip
pf = os.path.join(tmp, "progress.json")
save_progress(7, 3, 2, 250, pf)
if load_progress(pf) != (7, 3, 2, 250, False, False):
    failures.append(f"progress round-trip failed: {load_progress(pf)}")

# QA2-1: match_in_progress is PERSISTED. A result is only scored for a match
# this process paid for; keeping that flag in memory meant a restart lost it,
# and the result overlay of an already-paid match was refused, dismissed, and
# gone. Every stall message in orchestrator.py ends with "just rerun the
# script", so restart is the DESIGNED recovery path — the flag has to survive it.
save_progress(1, 2, 3, 400, pf, match_in_progress=True, bans_done_this_match=True)
if load_progress(pf) != (1, 2, 3, 400, True, True):
    failures.append(
        f"match_in_progress did not survive a save/load round-trip: "
        f"{load_progress(pf)} — a restart mid-match silently discards a real win")
save_progress(1, 2, 3, 400, pf)          # default must be False, not sticky
if load_progress(pf)[4] is not False or load_progress(pf)[5] is not False:
    failures.append("match_in_progress defaulted to True on a plain save — "
                    "a finished match would look unpaid-for forever")
# A pre-existing progress file written before this field existed must still load.
import json as _json
with open(pf, "w") as _f:
    _json.dump({"wins": 5, "losses": 1, "draws": 0, "balance": 100}, _f)
if load_progress(pf) != (5, 1, 0, 100, False, False):
    failures.append(f"a legacy progress file without match_in_progress broke: "
                    f"{load_progress(pf)}")
save_progress(7, 3, 2, 250, pf)

# A missing file must yield defaults, not raise — this is the first-run path.
if load_progress(os.path.join(tmp, "nope.json")) != (0, 0, 0, None, False, False):
    failures.append("missing progress file should return (0, 0, 0, None, False, False)")

# QA N13: writes must be atomic, so an interrupted run can't truncate the record.
#
# The old assertion here was "no stray .tmp is left behind" — which a NON-atomic
# write satisfies MORE easily, because it never creates a temp file at all. It
# was structurally incapable of failing in the direction it cared about
# (LESSONS.md §1, "assertion satisfied by the mechanism's absence").
#
# What atomicity actually promises: a reader never observes a partial file. So
# interrupt the write MID-STREAM and assert the old contents are still intact.
save_progress(1, 1, 1, 100, pf)
if os.path.exists(pf + ".tmp"):
    failures.append("atomic write left a .tmp file behind")

_before_interrupt = load_progress(pf)


class _Boom(Exception):
    pass


_real_dump = json.dump


def _dump_then_die(obj, fp, *a, **k):
    # Write a truncated prefix, then fail — exactly what a crash mid-write does.
    fp.write('{"wins": 1, "loss')
    raise _Boom("interrupted mid-write")


json.dump = _dump_then_die
try:
    save_progress(9, 9, 9, 999, pf)
except _Boom:
    pass
except Exception as _e:
    failures.append(f"interrupted write raised {type(_e).__name__}, expected _Boom")
finally:
    json.dump = _real_dump

_after_interrupt = load_progress(pf)
if _after_interrupt != _before_interrupt:
    failures.append(
        f"a write interrupted mid-stream changed the file: {_before_interrupt} "
        f"-> {_after_interrupt}. Atomicity means a reader never sees a partial "
        "write — the previous record must survive intact until the rename.")
for _stray in os.listdir(tmp):
    if _stray.endswith(".tmp"):
        failures.append(f"interrupted write left {_stray} behind")

# QA R4: a CORRUPT progress file must refuse loudly rather than silently
# resetting the record to zero — that would discard the trophy progress and
# re-read the balance from the pause menu as if it were a fresh save.
bad = os.path.join(tmp, "corrupt.json")
with open(bad, "w") as f:
    f.write("{not json")
try:
    load_progress(bad)
    failures.append("corrupt progress file loaded silently instead of raising")
except RuntimeError:
    pass  # expected
except Exception as e:
    failures.append(f"corrupt progress raised {type(e).__name__}, expected RuntimeError")

# --------------------------------------------------- learned-roster hardening
# QA R2 N8 / R4 / R5 N26: a malformed cache must never break `import
# orchestrator` — it is loaded at module scope, so a raise there takes down
# every script including this test suite.
MALFORMED = [
    ("[1, 2, 3]", "top-level list"),
    ('{"6,3": "notadict"}', "entry is a string"),
    ('{"badkey": {"name": "X", "power": 5, "secondary": 1}}', "unparseable key"),
    ('{"6,3": {"name": "X"}}', "missing power/secondary"),
    ('{"6,3": {"name": null, "power": 5, "secondary": 1}}', "null name"),
    ('{"6,3": {"name": 123, "power": 5, "secondary": 1}}', "numeric name"),
    ('{"6,3": {"name": "   ", "power": 5, "secondary": 1}}', "blank name"),
]
lr = os.path.join(tmp, "learned.json")
orig_file = orchestrator.LEARNED_BAN_ROSTER_FILE
orchestrator.LEARNED_BAN_ROSTER_FILE = lr
try:
    for payload, desc in MALFORMED:
        with open(lr, "w") as f:
            f.write(payload)
        try:
            orchestrator._load_learned_roster()
            # The real breakage surfaced downstream at ROSTER_BY_NAME's
            # .lower(), so exercise that too rather than only the loader.
            {c.name.lower(): c for c in orchestrator.KNOWN_BAN_ROSTER.values()}
        except Exception as e:
            failures.append(f"malformed roster ({desc}) raised "
                            f"{type(e).__name__}: {e}")

    # A VALID entry must still load — the guards must not reject everything.
    _atomic_write_json(lr, {"6,4": {"name": "Test Card", "power": 7,
                                    "secondary": 2, "source": "test"}})
    orchestrator._load_learned_roster()
    if orchestrator.KNOWN_BAN_ROSTER.get((6, 4)) is None:
        failures.append("a valid learned entry failed to load")
    else:
        orchestrator.KNOWN_BAN_ROSTER.pop((6, 4), None)
finally:
    orchestrator.LEARNED_BAN_ROSTER_FILE = orig_file

# ------------------------------------------------------------- extract_json
# The model wraps JSON in prose and code fences unpredictably; this is why a
# regex replaced the old prefix-stripping approach.
for raw, expect in [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here is the state:\n```json\n{"a": 1}\n```\nHope that helps.', {"a": 1}),
    ('{"nested": {"b": 2}}', {"nested": {"b": 2}}),
]:
    try:
        if extract_json(raw) != expect:
            failures.append(f"extract_json({raw!r}) -> {extract_json(raw)}")
    except Exception as e:
        failures.append(f"extract_json({raw!r}) raised {type(e).__name__}")

try:
    extract_json("no json here at all")
    failures.append("extract_json accepted a response with no JSON")
except json.JSONDecodeError:
    pass

# ------------------------------------------------------------ hand_to_cards
players, tactics = hand_to_cards([
    {"kind": "player", "name": "A", "power": 8, "secondary": 1, "hand_index": 0},
    {"kind": "tactics", "name": "Power Swing", "type": "swing_boost",
     "bonus": 2, "hand_index": 1},
    {"kind": "player", "name": "B", "power": 4, "secondary": 0, "hand_index": 2},
])
if [i for i, _ in players] != [0, 2]:
    failures.append(f"hand_to_cards lost player hand_index mapping: {players}")
if [i for i, _ in tactics] != [1]:
    failures.append(f"hand_to_cards lost tactics hand_index mapping: {tactics}")
if tactics and tactics[0][1].kind is not TacticsType.SWING_BOOST:
    failures.append(f"hand_to_cards mis-typed tactics: {tactics[0][1].kind}")
# Index mapping is what select_and_play() presses against, so a shifted index
# plays the wrong card — assert it survives a gap in hand_index ordering.

for f_ in os.listdir(tmp):
    os.remove(os.path.join(tmp, f_))
os.rmdir(tmp)

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} state-io failures")

print(f"OK: progress round-trip + atomic write + corrupt-refusal, "
      f"{len(MALFORMED)} malformed roster shapes survived import, "
      f"extract_json and hand_to_cards mappings correct")


# --- Synthetic-row stamping and per-run screenshot folders ----------------
# Defence in depth for the contamination that put 30 synthetic rows into
# match_log.jsonl. The redirect (BASEBALL_MATCH_LOG) PREVENTS it; the stamp
# makes it RECOVERABLE when prevention is forgotten. The two fail
# independently, which is the whole point — a test that forgets the redirect
# still produces removable rows instead of invisible ones.
import atexit
import shutil as _shutil
import subprocess
import sys as _sys
import tempfile as _tf

_synth_dir = _tf.mkdtemp()
atexit.register(_shutil.rmtree, _synth_dir, ignore_errors=True)
_synth = os.path.join(_synth_dir, "m.jsonl")
_r = subprocess.run(
    [_sys.executable, "-c",
     "import orchestrator as o; o.log_matchup({'our_card_name': 'X', 'our_power': 5})"],
    env=dict(os.environ, BASEBALL_MATCH_LOG=_synth, BASEBALL_TEST_RUN="1",
             PERSONAL_ANTHROPIC_API_KEY="dummy-offline-test"),
    capture_output=True, text=True, cwd=_ROOT)
with open(_synth) as _f:
    _row = json.loads(_f.read())
assert _row.get("_synthetic") is True, (
    f"a row written under BASEBALL_MATCH_LOG is not stamped _synthetic: {_row} "
    "— contamination would again be indistinguishable from real data")
assert _row.get("_source") == "test-suite", f"missing _source marker: {_row}"
# The stamp must survive the documented removal one-liner.
assert '"_synthetic": true' in json.dumps(_row), (
    "the stamp does not serialise as `\"_synthetic\": true`, so the documented "
    "`grep -v` removal would silently miss these rows")

# A real run must NOT be stamped, or the marker would strip genuine data.
# A genuine run has NEITHER marker. Both must be stripped to simulate it —
# BASEBALL_TEST_RUN is exported by run_tests.sh, and stripping only the log
# override would leave this asserting nothing once the stamp started keying on
# test context rather than on the redirect.
_r2 = subprocess.run(
    [_sys.executable, "-c", "import orchestrator as o; print(o._synthetic_log())"],
    env={k: v for k, v in os.environ.items()
         if k not in ("BASEBALL_MATCH_LOG", "BASEBALL_TEST_RUN")}
        | {"PERSONAL_ANTHROPIC_API_KEY": "dummy-offline-test"},
    capture_output=True, text=True, cwd=_ROOT)
assert "False" in _r2.stdout, (
    f"_synthetic_log() is true without an override ({_r2.stdout!r}) — genuine "
    "rows would be stamped and then stripped by the cleanup one-liner")

# Screenshot folders: new runs are foldered, the calibration corpus is not
# moved. test_ocr_ban_card.py and test_gameplay_regions.py reference specific
# top-level frames by path, and the settle/reveal thresholds were measured
# against them.
import orchestrator as _o
assert _o.SCREENSHOT_LOG_DIR == "screenshot_log", (
    "the corpus root moved — every frame path in the other tests and every "
    "threshold measured against them assumes screenshot_log/")

# The stamp must fire on TEST CONTEXT, not merely on the redirect — that was
# the flaw in the first version: it only marked rows that were already going
# somewhere harmless, and left rows unstamped in the one case that matters.
_r3 = subprocess.run(
    [_sys.executable, "-c", "import orchestrator as o; print(o._synthetic_log())"],
    env={k: v for k, v in os.environ.items() if k != "BASEBALL_MATCH_LOG"}
        | {"PERSONAL_ANTHROPIC_API_KEY": "dummy-offline-test",
           "BASEBALL_TEST_RUN": "1"},
    capture_output=True, text=True, cwd=_ROOT)
assert "True" in _r3.stdout, (
    f"BASEBALL_TEST_RUN alone does not trigger the stamp ({_r3.stdout!r}) — a "
    "test that forgets BASEBALL_MATCH_LOG would write unstamped rows into the "
    "real dataset, which is exactly the case the stamp exists for")

# THE INVERSE, and it is the one that loses data. A REAL run has every reason
# to redirect its log (a per-save log, say). If a bare redirect counted as test
# context, genuine rows would be stamped `_synthetic` and the documented
# `grep -v` cleanup would DELETE them — the loss the stamp exists to prevent,
# inverted. Verified 2026-08-25 as a live defect.
_r4 = subprocess.run(
    [_sys.executable, "-c", "import orchestrator as o; print(o._synthetic_log())"],
    env={k: v for k, v in os.environ.items() if k != "BASEBALL_TEST_RUN"}
        | {"PERSONAL_ANTHROPIC_API_KEY": "dummy-offline-test",
           "BASEBALL_MATCH_LOG": _synth},
    capture_output=True, text=True, cwd=_ROOT)
assert "False" in _r4.stdout, (
    f"a redirected log alone marked the run synthetic ({_r4.stdout!r}) — a real "
    "run that redirects its log would have its genuine rows stamped and then "
    "stripped by the documented cleanup")

print("OK: synthetic rows stamped + removable, stamp fires on test context "
      "only (a bare log redirect does NOT mark a real run), corpus root "
      "unchanged")


# --- Opponent tactics kind must be DERIVABLE, not read from a phantom field
# DOC_AUDIT #9: the code read `opp_tactics.get("type")`, but READ_MATCHUP_PROMPT's
# tactics schema is {kind, name, bonus, paired_with} — there is no `type`. So it
# returned None unconditionally: measured None on 39/39 logged rows, including
# the 8 with a non-zero bonus. analyze_match_log.py then dropped those rows as
# "kind missing", which is precisely the data the field was added to capture.
#
# Only SWING_BOOST/PITCH_BOOST add power (power_bonus, simulate.py), so a bonus
# without a kind cannot be converted to effective power at all.
from orchestrator import (KNOWN_TACTICS_NAMES, TACTICS_NAME_TO_KIND,
                          _tactics_kind_from_name)
from decision_engine import TacticsType

# Every name the prompt can return must map to a real TacticsType.
_valid = {t.value for t in TacticsType}
for _name in KNOWN_TACTICS_NAMES:
    _kind = _tactics_kind_from_name(_name)
    assert _kind in _valid, (
        f"tactics card {_name!r} maps to {_kind!r}, which is not a TacticsType — "
        "its rows will be dropped from the effective-power analysis")

assert len(TACTICS_NAME_TO_KIND) == len(KNOWN_TACTICS_NAMES), (
    f"{len(TACTICS_NAME_TO_KIND)} name->kind mappings for "
    f"{len(KNOWN_TACTICS_NAMES)} known tactics cards — one of them will always "
    "return None and silently lose its rows")

# Case- and spacing-insensitive: the model's capitalisation is not stable.
assert _tactics_kind_from_name("POWER SWING") == TacticsType.SWING_BOOST.value
assert _tactics_kind_from_name("  power swing ") == TacticsType.SWING_BOOST.value

# ABSTAIN on anything unrecognised. Guessing would fabricate the power figure
# the whole match log exists to measure.
assert _tactics_kind_from_name("Not A Real Card") is None
assert _tactics_kind_from_name(None) is None
assert _tactics_kind_from_name("") is None

# And the field must not be read from a key the prompt never sends.
import inspect

import orchestrator as _o
_src = inspect.getsource(_o.run)
assert 'opp_tactics.get("type")' not in _src, (
    "opp_tactics_kind is being read from a `type` field again — the prompt does "
    "not return one, so it will be None on every row")

print(f"OK: all {len(KNOWN_TACTICS_NAMES)} tactics names map to a TacticsType, "
      "unknown names abstain, and the phantom `type` field is not read")
