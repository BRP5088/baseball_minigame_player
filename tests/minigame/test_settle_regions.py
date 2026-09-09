"""Tests for region-aware settle detection.

WHY THIS EXISTS
---------------
The original detector watched ONE region, `ANIMATION_ROI_FRACTION`
(y 0.15-0.65). The hand — which every turn decision is read from — is at
y 0.716-1.0. They do not overlap at all, so the detector could report
"settled" while cards were still animating into the hand. Reading then
produced empty hands and power-0 cards, which pushed `should_redraw()` into
defensive discards. That degraded actual play, not just logging.

Nothing caught it because there was no test asserting the detector watches
what the readers read. That invariant is asserted here.

Offline: pure geometry, no screenshots, no API, no PS5 input.
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


import os

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
from orchestrator import (ANIMATION_ROI_FRACTION, GAMEPLAY_REGIONS_FRAC,
                          SETTLE_REGION_SETS, _settle_region_box)

failures = []


def overlaps(a, b):
    """Do two (x0, y0, x1, y1) fractional boxes intersect at all?"""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return (min(ax1, bx1) > max(ax0, bx0)) and (min(ay1, by1) > max(ay0, by0))


# --- 0. Thresholds must be per-region, not one shared constant ------------
# At a shared 6.0, 17.4% of genuinely idle hand pairs read as "moving".
from orchestrator import SETTLE_THRESHOLDS
for name in set(sum((list(v) for v in SETTLE_REGION_SETS.values()), [])):
    if name not in SETTLE_THRESHOLDS:
        failures.append(f"region {name!r} is gated on but has no threshold")
# TWO-SIDED. The floor stops idle noise reading as motion; the ceiling stops
# the opposite and worse failure — a threshold of 1000 means every frame reads
# as settled, which is the original bug this whole file exists for. Real
# animation on the hand measures well above 20, so 40 is a generous ceiling.
_hand_th = SETTLE_THRESHOLDS.get("hand", 0)
if _hand_th < 7.0:
    failures.append(
        f"hand threshold {_hand_th} is below its measured idle p95 of 7.63 — "
        "idle noise would read as motion")
if _hand_th > 40.0:
    failures.append(
        f"hand threshold {_hand_th} is so high that genuine card animation "
        "reads as settled — that is the original defect: the gate reports "
        "'settled' while cards are still moving into the hand")

# --- 1. Every named region must resolve to a real box ---------------------
for set_name, names in SETTLE_REGION_SETS.items():
    if not names:
        failures.append(f"region set {set_name!r} is empty")
    for n in names:
        try:
            box = _settle_region_box(n)
        except KeyError:
            failures.append(f"region {n!r} in set {set_name!r} does not resolve")
            continue
        x0, y0, x1, y1 = box
        if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
            failures.append(f"region {n!r} has an invalid box {box}")

# --- 2. THE INVARIANT: a turn read must be gated on the HAND --------------
# The original bug was that the detector never watched the hand at all.
# Note the gate is hand-ALONE by measurement, not hand-plus-everything: adding
# regions raised bad reads from 1.6% to 3.3% and p90 latency to 17.97s,
# because waiting longer runs into the next animation
# (SETTLE_TIMING_ANALYSIS.md §4).
turn_set = SETTLE_REGION_SETS["turn"]
if "hand" not in turn_set:
    failures.append(
        f"the 'turn' settle set {turn_set} omits the hand — that is the "
        "original bug, the loop would read cards mid-deal")
if "scoreboard" in turn_set:
    failures.append(
        "'scoreboard' is in the turn gate: its motion during real animation "
        "(p50 6.59) barely exceeds its own idle noise (p90 6.81), so it cannot "
        "discriminate and only adds latency")

# --- 3. Regression guard: the old ROI genuinely did not cover the hand ----
# Documents the original defect so the geometry can't silently drift back.
if overlaps(ANIMATION_ROI_FRACTION, GAMEPLAY_REGIONS_FRAC["hand"]):
    failures.append(
        "ANIMATION_ROI_FRACTION now overlaps the hand — this test's premise "
        "changed; re-check whether the 'turn' set is still needed")

# --- 4. The default set must include the hand ----------------------------
# Callers that don't opt into a set still must not read a mid-deal hand.
if "hand" not in SETTLE_REGION_SETS["default"]:
    failures.append(
        "the 'default' settle set omits the hand — un-migrated callers would "
        "reproduce the original bug")

# --- 5. Reveal must NOT be handled by settling ---------------------------
# The centre keeps animating for ~9s after the reveal and only goes quiet once
# the cards have already cleared, so a settle-based reveal reads an empty
# diamond. It uses a presence trigger instead (wait_for_reveal_cards).
if "reveal" in SETTLE_REGION_SETS:
    failures.append(
        "a 'reveal' settle set exists again — settling is the WRONG trigger "
        "for the matchup reveal; use wait_for_reveal_cards() (presence), see "
        "REVEAL_CENTER_REGION for the measured timeline")

from orchestrator import REVEAL_CENTER_REGION, REVEAL_EDGE_THRESHOLD
cx0, cy0, cx1, cy1 = REVEAL_CENTER_REGION
if not (cx0 <= 0.5 <= cx1 and cy0 <= 0.42 <= cy1):
    failures.append(f"REVEAL_CENTER_REGION {REVEAL_CENTER_REGION} does not "
                    "cover where the cards meet (~0.5, 0.42)")
# The threshold must hold on BOTH capture paths, because _fast_grab() falls
# back to pyautogui when mss is unavailable. A gradient count is scale-
# sensitive, and the two paths reach 2000px from opposite directions:
#   native (pyautogui 3456 -> downscale): absent max 0.0615 | present min 0.0779
#   mss    (1728 -> UPSCALE, interpolated): absent max 0.0591 | present min 0.0692
# Upscaling invents no high-frequency detail, so every count lands lower. The
# safe band is the INTERSECTION, [0.0615, 0.0692]. The original 0.070 was fit
# to the native path only and sat ABOVE the mss present-min, so on that path
# the weakest genuine reveal never fired — silently, since a False return is
# swallowed by the caller's bare except.
#
# !! THE "absent max" ABOVE IS WRONG, AND SO IS THE GAP IT IMPLIES. !!
# A full census of the 3700 logged frames of the 2026-08-26 run (native path)
# puts 447 NON-reveal frames above 0.065, and hand-verified frame
# 20260826_105511_814.jpg — an ordinary turn screen, hand fanned, nothing
# revealed — measures 0.0844. That is above both the claimed absent max
# (0.0615) and the claimed present min (0.0779), so the two classes OVERLAP
# and no threshold separates them (AUC 0.735, best balanced accuracy 0.724).
#
# The cause is not the face-down pitcher card (it reads 0.021-0.035, so the
# old V7 diagnosis was wrong): this game draws BASE RUNNERS as face-up cards
# on the diamond, and they clip the region. A reveal with runners on base and
# an idle turn with runners on base look nearly the same to an edge count.
#
# The band is kept ONLY as a change-detector pinning the threshold to the
# value that ran live, NOT as evidence of a safe margin — there is no margin.
# Do not cite it as one. Replacing the feature (the hand fan is nearly binary:
# present on every turn screen, hidden for the whole reveal) needs a live
# re-measure on the mss path, which cannot be done from logged frames.
if not (0.0615 < REVEAL_EDGE_THRESHOLD < 0.0692):
    failures.append(
        f"REVEAL_EDGE_THRESHOLD={REVEAL_EDGE_THRESHOLD} is outside the band "
        "that ran live. NOTE: this band is a change-detector, not a proven "
        "separation — the classes overlap (see the comment above).")


print(f"OK: {len(SETTLE_REGION_SETS)} region sets resolve; 'turn' gates on all "
      f"the hand (measured hand-alone gate); 'default' includes the "
      f"hand; reveal threshold {REVEAL_EDGE_THRESHOLD} pinned to the value "
      f"that ran live (NOT a separating threshold — classes overlap)")


# --- The gate must actually GATE ------------------------------------------
# QA_VACUOUS: `settled = True` could be hard-wired into wait_for_screen_to_settle
# and nothing in the suite noticed — this file inspects CONSTANTS only and never
# calls the function. A gate that always reports "settled" returns instantly on
# a mid-deal frame, which is the exact failure the whole region-set design
# exists to prevent (reading cards while they are still animating in).
#
# Driven with fabricated crops so it is pure logic: no capture, no screen.
import time as _t

from PIL import Image

import orchestrator as _o

_STILL = Image.new("L", (40, 40), 128)
_MOVED = Image.new("L", (40, 40), 20)


def _drive(frames, **kw):
    """Run the real gate against a scripted sequence of crops."""
    seq = list(frames)
    calls = {"n": 0}

    def fake_grab(names):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return {n: seq[i] for n in names}

    _real_grab, _real_time = _o._grab_settle_regions, _o.time
    clock = [1000.0]
    _o._grab_settle_regions = fake_grab
    _o.time = type("C", (), {"sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
                             "time": staticmethod(lambda: clock[0]),
                             "strftime": staticmethod(_t.strftime)})()
    try:
        return _o.wait_for_screen_to_settle(**kw), calls["n"]
    finally:
        _o._grab_settle_regions = _real_grab
        _o.time = _real_time


# A screen that never stops moving must consume its whole max_wait...
_elapsed, _polls = _drive([_STILL, _MOVED] * 200, max_wait=4.0, regions="turn")
if _elapsed < 3.0:
    failures.append(
        f"a perpetually MOVING screen settled after {_elapsed:.2f}s of a 4.0s "
        "budget — the gate is not gating, so callers read mid-animation frames")

# A screen that goes quiet for exactly ONE poll mid-animation must NOT be
# declared settled. This is the single pattern `stable_polls_required` exists
# for, and nothing covered it: lowering it 2 -> 1 survived the entire suite.
# The existing cases cannot separate the two — an alternating [STILL, MOVED]
# sequence never goes quiet for one poll and then moves again, and an
# all-STILL sequence settles under either value. The docstring's own
# measurement was run in the RAISING direction only, and so was the coverage.
# Measured on this exact sequence: required=1 settles at 5 polls, required=2
# at 6, required=3 at 7. The first quiet COMPARISON lands at poll 5, so
# "must not settle at the first quiet poll" is `polls > 5`. An earlier version
# asserted `polls <= 3`, which both settings clear — it distinguished nothing.
_one_quiet = [_MOVED, _STILL, _MOVED, _STILL, _STILL, _STILL, _STILL, _STILL]
_elapsed3, _polls3 = _drive(_one_quiet, max_wait=8.0, regions="turn")
if _polls3 <= 5:
    failures.append(
        f"the gate settled after {_polls3} polls on a screen that went quiet "
        "for ONE poll and then moved again — a single quiet frame is being "
        "treated as settled, which is exactly the mid-animation read that "
        "stable_polls_required was measured to prevent")

# ...and a still screen must return quickly, or every turn pays the full cap.
_elapsed2, _ = _drive([_STILL] * 50, max_wait=8.0, regions="turn")
if _elapsed2 > 2.0:
    failures.append(
        f"a STILL screen took {_elapsed2:.2f}s to settle — the gate is waiting "
        "when it has nothing to wait for, which is pure per-turn latency")

# And the two must be distinguishable: if they are not, the gate is a no-op.
if _elapsed2 >= _elapsed:
    failures.append(
        f"still screen ({_elapsed2:.2f}s) settled no faster than a moving one "
        f"({_elapsed:.2f}s) — the gate cannot tell motion from stillness")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} settle-region failures")


# --- the post-play deal gate (wait_for_hand_deal) ------------------------
# The loop reads a median of 14.7s too early after every play — 88 of 88 real
# plays. "Settled" and "ready" are different questions: right after a play the
# hand is quiet because NOTHING HAS HAPPENED YET, so a settle gate on the hand
# returns almost immediately and the loop reads before the replacement card
# lands. That is where the empty-hand / power-0 misreads come from.
from orchestrator import (POST_PLAY_DEAL_MAX_WAIT, POST_PLAY_WAIT_FOR_DEAL,
                          hand_deal_seen, wait_for_hand_deal)

_th = _o.HAND_DEAL_THRESHOLD

# The pure decision function: a deal is a RISING EDGE above the hand threshold.
if not hand_deal_seen([0.0, 1.0, _th + 5]):
    failures.append("a clear deal-sized delta was not recognised as a deal")
if hand_deal_seen([0.0, 1.0, _th - 0.1]):
    failures.append("sub-threshold jitter is being read as a deal — the gate "
                    "would release on noise and the read stays early")
if hand_deal_seen([]):
    failures.append("an empty delta stream reports a deal")

# It must be a threshold, not a constant: mutating HAND_DEAL_THRESHOLD
# must move the boundary.
if not hand_deal_seen([_th], threshold=_th):
    failures.append("a delta exactly AT the threshold is not counted")
if hand_deal_seen([_th], threshold=_th + 1):
    failures.append("threshold argument is ignored")

# ON by default since 2026-09-08 (patch63); BASEBALL_DEAL_WAIT=0 is the only off switch.
if not POST_PLAY_WAIT_FOR_DEAL and (os.environ.get("BASEBALL_DEAL_WAIT") or "1").strip().lower() not in ("0", "false", "off", "no"):
    failures.append("the deal gate is OFF by default -- patch63 turned it on")
# 20 s, live-measured: every deal in 30 gate windows crossed by 15.0 s (patch66).
if POST_PLAY_DEAL_MAX_WAIT < 18:
    failures.append(f"POST_PLAY_DEAL_MAX_WAIT={POST_PLAY_DEAL_MAX_WAIT} is below "
                    "the 15.0s slowest deal measured live plus margin — it would time out "
                    "on ordinary plays and silently revert to reading early")

# Timeout must FALL THROUGH, never raise: the caller still needs a frame, and
# the existing retry path handles a bad one.
_grabs = {"n": 0}
_real_grab = _o._grab_settle_regions
_o._grab_settle_regions = lambda names: (_grabs.__setitem__("n", _grabs["n"] + 1),
                                         {n: _STILL for n in names})[1]
_real_time = _o.time
_clock = [1000.0]
_o.time = type("C", (), {"sleep": staticmethod(lambda s: _clock.__setitem__(0, _clock[0] + s)),
                         "time": staticmethod(lambda: _clock[0]),
                         "strftime": staticmethod(_t.strftime)})()
try:
    _res = wait_for_hand_deal(max_wait=2.0, poll_interval=0.15)
    if _res is not False:
        failures.append(f"a hand that never changes returned {_res!r}, expected False")
finally:
    _o._grab_settle_regions = _real_grab
    _o.time = _real_time

print(f"OK: post-play deal gate — distance from the baseline at threshold {_th}, "
      f"falls through after {POST_PLAY_DEAL_MAX_WAIT:.0f}s, "
      f"{'ENABLED' if POST_PLAY_WAIT_FOR_DEAL else 'default off'}")


# FINAL failure summary — keep this LAST in the file. The summary at line ~228
# raises, so any check appended after it runs but can never report: its
# failures land in `failures` after the block that would have printed them.
# Two mutations (any->all in hand_deal_seen, and halving
# POST_PLAY_DEAL_MAX_WAIT) both "survived" for exactly this reason, not
# because the assertions were wrong. Fourth instance of this trap today.
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} settle-region failure(s)")
