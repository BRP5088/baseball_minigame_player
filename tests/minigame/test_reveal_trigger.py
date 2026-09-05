"""wait_for_reveal_cards() must not fire before the cards flip face-up.

WHY THIS EXISTS
---------------
`REVEAL_CENTER_REGION`'s right edge used to be 0.62, and
`GAMEPLAY_REGIONS_FRAC["first_base"]` starts at 0.550 — so the region meant to
watch the centre of the diamond reached 0.07 of screen width into a BASE. This
game draws base runners as face-up cards on the bases, and a runner sits there
for the whole turn, so with a runner on first the "are the cards at centre yet"
statistic cleared its threshold during the card-SELECTION phase, before
anything had been revealed. `wait_for_reveal_cards()` returned True on its
first poll and `read_matchup_reveal()` spent its vision call on the pre-flip
screen, where our own card is still face down. The reader then reported the
face-up cards it COULD see — the runners — and the auditor correctly concluded
our card was absent and blamed a dropped keystroke that never happened. Seven
turns and a run-wide 2.6x input slowdown on 2026-09-01 came from this.

The threshold was never wrong; the region was. That is the invariant here.

Offline: reads saved frames, no capture, no vision, no API key, no PS5 input.
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

from PIL import Image

from orchestrator import (GAMEPLAY_REGIONS_FRAC, READ_MATCHUP_PROMPT,
                          REVEAL_CENTER_REGION,
                          REVEAL_EDGE_THRESHOLD, center_card_edge_fraction)

FIXTURES = os.path.join(_ROOT, "test_fixtures", "reveal_trigger")

# Every fixture is a real 1920x1080 frame from the 2026-09-01 live run, labelled
# by opening it. The first two and the third are the SAME TURN either side of
# the flip, which is the whole point: nothing about the runner on first changes
# between them, only whether the faceoff is face-up.
FACE_DOWN = {
    # The selection frame for the turn that logged
    #   [MISFIRE?] ... our played power 8 ... revealed [('Johnny Drawers', 7, [7]), ...]
    # Two face-down card backs at centre, our hand still fanned along the
    # bottom, and Johnny Drawers — power 7, secondary 1 — face-up on first
    # base. He is the card that reveal read came back with.
    "facedown_runner_on_first.jpg": "selection phase, runner on first",
    # Worst case in the run: the face-down frame that scored highest under the
    # old region (0.0842, versus a 0.065 threshold).
    "facedown_runner_on_first_worst.jpg": "selection phase, highest-scoring false trigger",
}
FACE_UP = {
    # The flip of that same turn: PLAY BALL!, both cards face-up. The runner is
    # still on first, abutting the opponent's tactics card.
    "reveal_playball_same_turn.jpg": "genuine reveal, same turn as the two above",
    # The two weakest genuine reveals in the run — both scored 0.0654 under the
    # old region, i.e. they were within 0.0004 of never being detected at all.
    "reveal_weak.jpg": "genuine reveal, weakest in the run",
    "reveal_weak_2.jpg": "genuine reveal, weakest in the run",
}

# The statistic is a gradient-pixel COUNT normalised by area, so it rises as the
# capture shrinks — the module comment measures the classes separating at 2000px
# and NOT separating at 1400px. Both live capture paths deliver 2000px wide, so
# that is the width that has to hold; 1920 is the width the fixtures were saved
# at. Checking both means a regression cannot hide behind a resample.
WIDTHS = (1920, 2000)

failures = []


def _score(path, width):
    img = Image.open(path)
    if img.size[0] != width:
        img = img.resize((width, round(img.size[1] * width / img.size[0])),
                         Image.LANCZOS)
    return center_card_edge_fraction(img)


# --- 1. The geometry invariant, stated directly ---------------------------
# This is the root cause in one line: a region watching the CENTRE must not
# reach the card a base runner stands on, because that card is face-up for the
# whole turn and its edges read exactly like a revealed card's.
#
# 0.58 is measured, not inherited from GAMEPLAY_REGIONS_FRAC["first_base"]
# (0.550), which is a crop BOX with margin around the base rather than the card
# itself. Column-wise edge energy across y 0.28-0.58 of the two face-down
# fixtures puts the runner's card body at x 0.58-0.655, with a dead gutter of
# bare wood between it and the centre cards:
#
#   x     0.55   0.56   0.57   0.58   0.59  ...  0.65   0.66
#   edge  0.096  0.004  0.008  0.147  0.109      0.099  0.000
#
# So the right edge belongs in that gutter. It must not be pulled in FURTHER
# than the gutter either: at 0.56 and 0.55 the empty wood stops diluting the
# statistic, the face-down pair fills more of the region, and false triggers
# come back (31/227 and 14/227 respectively, versus 0/227 at 0.58).
_RUNNER_CARD_LEFT = 0.58
_first_base_left = GAMEPLAY_REGIONS_FRAC["first_base"][0]
if REVEAL_CENTER_REGION[2] > _RUNNER_CARD_LEFT:
    failures.append(
        f"REVEAL_CENTER_REGION right edge {REVEAL_CENTER_REGION[2]} reaches "
        f"the card a runner on first stands on (x >= {_RUNNER_CARD_LEFT}). "
        "That card is face-up for the whole turn, so the reveal trigger will "
        "fire during card selection and the reveal will be read before the "
        "cards flip.")

# It still has to cover where the two cards actually meet — the same assertion
# test_settle_regions.py makes, repeated because narrowing the region to dodge
# first base must not be allowed to narrow it off the faceoff entirely.
_cx0, _cy0, _cx1, _cy1 = REVEAL_CENTER_REGION
if not (_cx0 <= 0.5 <= _cx1 and _cy0 <= 0.42 <= _cy1):
    failures.append(f"REVEAL_CENTER_REGION {REVEAL_CENTER_REGION} no longer "
                    "covers where the cards meet (~0.5, 0.42)")

# --- 2. Real frames: pre-flip must NOT trigger ----------------------------
for name, what in FACE_DOWN.items():
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        failures.append(f"missing fixture {name} — this test must not silently "
                        "skip; a detector test that runs on zero frames "
                        "reports success on nothing")
        continue
    for w in WIDTHS:
        got = _score(path, w)
        if got >= REVEAL_EDGE_THRESHOLD:
            failures.append(
                f"{name} ({what}) at {w}px scores {got:.4f} >= threshold "
                f"{REVEAL_EDGE_THRESHOLD}: wait_for_reveal_cards() would "
                "return True with the faceoff still face down, and the reveal "
                "read would report the base runners instead of our card")

# --- 3. Real frames: the genuine reveal must STILL trigger ----------------
for name, what in FACE_UP.items():
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        failures.append(f"missing fixture {name} — this test must not silently skip")
        continue
    for w in WIDTHS:
        got = _score(path, w)
        if got < REVEAL_EDGE_THRESHOLD:
            failures.append(
                f"{name} ({what}) at {w}px scores {got:.4f} < threshold "
                f"{REVEAL_EDGE_THRESHOLD}: a real reveal would time out and "
                "the turn would never be logged")

# --- 4. The two classes must actually be SEPARATED, not merely ordered ----
# Prior work concluded no threshold separates reveal from non-reveal and pinned
# the constant as a change-detector only (see test_settle_regions.py). That was
# measured with the old region; with first base excluded there is a real gap,
# and this asserts it stays real rather than drifting back to a coin flip.
_down = [_score(os.path.join(FIXTURES, n), w)
         for n in FACE_DOWN if os.path.exists(os.path.join(FIXTURES, n))
         for w in WIDTHS]
_up = [_score(os.path.join(FIXTURES, n), w)
       for n in FACE_UP if os.path.exists(os.path.join(FIXTURES, n))
       for w in WIDTHS]
if _down and _up:
    _gap = min(_up) - max(_down)
    if _gap < 0.005:
        failures.append(
            f"face-down max {max(_down):.4f} and reveal min {min(_up):.4f} "
            f"leave a gap of {_gap:.4f}; the classes have collapsed back into "
            "each other and no threshold can separate them")

# --- 5. The prompt must not re-assert its own premise ---------------------
# A change-detector, and labelled as one: it cannot prove the model behaves,
# only that the two sentences the live failure was traced to have not come
# back. Worth having because the trigger fix above narrows the window but does
# not close it — a read can still land pre-flip — and the prompt is the only
# thing that decides whether that returns [] or a confident wrong answer.
#
# The old opening asserted the reveal was on screen ("You are looking at a
# screenshot showing the face-up cards revealed"), which left the model no way
# to say "not yet" and got the base runners reported instead.
_p = READ_MATCHUP_PROMPT.lower()
if "you are looking at a screenshot showing the face-up cards revealed" in _p:
    failures.append(
        "READ_MATCHUP_PROMPT asserts that the reveal is on screen again. On a "
        "pre-flip frame that premise is false and the model answers it anyway, "
        "with whatever else is face-up — the base runners.")
for _needle, _why in (
        ("base runner", "the runners are the cards actually returned by the "
                        "failing reads; the prompt has to name them"),
        ("face-down", "the prompt has to say the faceoff may not have flipped "
                      "yet, or there is no reason for the model to say so"),
        ('{"cards": []}', "the model needs an explicit way to answer "
                          "'nothing is revealed yet'")):
    if _needle not in _p:
        failures.append(f"READ_MATCHUP_PROMPT no longer mentions {_needle!r}: {_why}")

if failures:
    for f in failures:
        print("FAIL:", f)
    raise SystemExit(1)

print(f"OK: reveal trigger separates {len(FACE_DOWN)} pre-flip frames "
      f"(max {max(_down):.4f}) from {len(FACE_UP)} genuine reveals "
      f"(min {min(_up):.4f}) at {'/'.join(str(w) for w in WIDTHS)}px, "
      f"threshold {REVEAL_EDGE_THRESHOLD}; region stops at "
      f"{REVEAL_CENTER_REGION[2]}, clear of first base at {_first_base_left}")
