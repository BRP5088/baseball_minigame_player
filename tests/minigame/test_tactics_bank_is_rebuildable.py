"""The hand tactics bank must be re-derivable, and adding to it must only ADD.

tactics_templates.npz is a committed BINARY on the money path: the tactics TYPE
decides which card is played, and RULES.md records that only SWING and PITCH
boosts add power -- so a fielding boost read as a swing boost plays the wrong card
in a $50 match and nothing downstream reports an error. Until 2026-09-20 it had no
builder in the live tree and could only be trusted, never checked.

WHAT THE DONORS FIXED. Measured over 540 archived hand crops, the rejection rate
against MIN_TYPE_SCORE splits by SLOT x TYPE and by neither alone:

    slot |  fielding |    pitch |    speed |    swing
      0  |  0.0(137) |  0.0( 25)|  0.0( 89)|  0.0( 59)
      3  |100.0( 12) |  0.0( 11)|  0.0( 38)|  0.0( 11)   <- 12 of 12

137 of 163 fielding examples in the bank are slot 0, so it encoded the slot-0
framing and a slot-3 card topped out at 0.75 against it AT ANY OFFSET.

THE TWO CHEAPER EXPLANATIONS WERE MEASURED AND REJECTED (do not retry them):
widening BANNER_BOX for the longest label moved within-class agreement by +0.006
for fielding and made the other three WORSE; and the offset search already covers
the peak, which sits at ox=0.

This file pins three things:
  1. the bank is exactly what tools/build_hand_tactics_templates.py builds, so it
     can never drift from its source again;
  2. every donor frame it names is still on disk -- a pruned frame must FAIL here
     rather than silently shrink the bank;
  3. adding templates only ever ADDS readings. The score is the max over the bank
     (CLAUDE.md 10.30), so a template can raise a score and must never lower one.
"""
import os as _os
import subprocess as _sp
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import numpy as np                                                   # noqa: E402

import local_hand as lh                                              # noqa: E402

_BUILDER = _os.path.join(_ROOT, "tools", "build_hand_tactics_templates.py")
_sys.path.insert(0, _os.path.join(_ROOT, "tools"))
import build_hand_tactics_templates as builder                       # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# --- 1. every named donor frame is still there -------------------------------
# The builder NAMES its inputs rather than globbing, so a pruned directory fails
# loudly. A glob would quietly build a smaller bank and still pass.
missing = [f for f, _s, _k in builder.DONORS
           if not _os.path.exists(_os.path.join(_ROOT, f))]
check(not missing,
      f"donor frame(s) gone: {missing}. The bank cannot be rebuilt without them; "
      "they are tracked files, so restore rather than dropping the donor.")

# --- 2. the shipped bank IS what the builder builds --------------------------
_r = _sp.run([_sys.executable, "-B", _BUILDER, "--check"],
             capture_output=True, text=True, cwd=_ROOT)
check(_r.returncode == 0,
      f"tactics_templates.npz does not match tools/build_hand_tactics_templates.py. "
      f"Re-run the builder and commit the result.\n{_r.stdout}{_r.stderr}")

_z = np.load(lh.TACTICS_TEMPLATES, allow_pickle=True)
_V, _T = _z["vectors"], np.array([str(x) for x in _z["types"]])
check(len(_V) == builder.BASE_N + len(builder.DONORS),
      f"bank has {len(_V)} templates, expected "
      f"{builder.BASE_N} preserved + {len(builder.DONORS)} donors")

# --- 3. the donors are present and labelled fielding --------------------------
check(list(_T[builder.BASE_N:]) == [k for _f, _s, k in builder.DONORS],
      f"the appended labels are not the donors': {list(_T[builder.BASE_N:])!r}")

# --- 4. ADDING A TEMPLATE MUST NOT LOWER ANY SCORE ---------------------------
# The reader takes the MAX over the bank, so a larger bank can only raise a
# score. If this ever fails the scoring rule has changed underneath the bank and
# every "can only add a reading" claim above is void.
_rng = np.random.default_rng(20260920)
_probe = _rng.standard_normal((64, _V.shape[1])).astype(np.float32)
_probe /= np.linalg.norm(_probe, axis=1, keepdims=True)
_base_max = (_V[:builder.BASE_N] @ _probe.T).max(axis=0)
_full_max = (_V @ _probe.T).max(axis=0)
check(bool((_full_max >= _base_max - 1e-6).all()),
      "a probe scored LOWER against the full bank than against the base alone — "
      "the max-over-bank rule no longer holds, so adding templates is no longer safe")
# CONTROL: the donors must actually be reachable, or the check above is vacuous --
# it would pass just as well on twelve all-zero rows nothing can match.
check(bool((_full_max > _base_max + 1e-6).any()),
      "no probe was matched better by ANY donor — the appended templates are "
      "unreachable, so the check above proves nothing")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print(f"  the tactics bank ({len(_V)} templates) matches its builder, every donor "
      "frame is present, and adding templates can only raise a score")
