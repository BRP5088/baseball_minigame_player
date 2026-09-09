"""patch62: the discard decision reads the SCOREBOARD's own DISCARDS dots.THE DEFECT, VERIFIED ON FRAMES 2026-09-08. The match loop decides "discard"
from vision's `discards_left` (orchestrator.play_one_turn), and vision's number
is not the game's. In the smoke run (overnight/smoke_cycle_20260908_2016.log)
it read 2 on nearly every turn and 3 or 4 on ten reads, each clamped to 0 by
the "[repair] discards_left N outside 0-2" branch. Match 1 issued FIFTEEN
discard decisions; match 3 issued four.The scoreboard says what the game actually did. Its lower panel carries a
DISCARDS row of two dots: a WHITE dot is an unused discard, a DARK dot a spent
one. Over the 58 scoreboard frames of
overnight/census/reveal_edge_frames_20260908 (native 1920x1080, match 3's
second half) the dots read WHITE-WHITE from t0081 to t0153 and WHITE-DARK from
t0189 to t0245 -- so the game consumed ONE discard in match 3 while the code
believed it had discarded FOUR times. Three of those presses were something
else, and `input_controller.select_and_discard` ends in `confirm_play`, so the
likeliest something else is that the card was PLAYED. That is what the user
watched happen.The code could not tell a discard from a play because it never looked. A
ledger of our own presses would be wrong in the OTHER direction -- it would
stop discarding at two while the game still had two. The dots are the truth.WHAT THIS ADDS  1. discard_dots.py -- read_discard_dots(img) -> (unused, detail). Pure
     PIL/numpy, ~1.2 ms, no OCR and no API call. Fractional geometry, so it
     reads the 1920x1080 census frames and the 2000px-wide frames
     orchestrator._fast_grab() produces alike. It ABSTAINS (None) rather than
     guessing; every threshold in it sits between two measured populations and
     the module docstring carries both (CLAUDE.md 10.4).  2. orchestrator.py, anchored on the discard branch and nothing else:
       (a) before the irreversible press, the dots are read from a FRESH
           capture; `unused == 0` means the card is PLAYED instead of
           discarded, with "[discard] dots say 0 unused ... playing";
       (b) after the press the dots are polled (0.25 s, up to 5 s) until the
           count drops, and the turn logs "[discard] registered: dots N -> M"
           or "[discard] did NOT register (dots N -> N) -- the card was most
           likely PLAYED". Only a REGISTERED discard increments the per-match
           ledger DISCARD_LEDGER["discards_used_this_match"], reset where
           bans_done_this_match is;
       (c) `redraws_left` is min(vision's clamped value, the dots' unused)
           when the dots read and vision's value when they do not, and both
           numbers appear on the "[redraw]" line of every turn.
     REDRAW_POWER_THRESHOLD, the play selection, navigation, the money path,
     the reveal code and every wait outside the discard branch are untouched.  3. tests/minigame/test_discard_dots.py plus five fixture frames copied into
     test_fixtures/discard_dots/. A sixth frame, the dimmest scoreboard on
     disk, is read where it already lives (test_fixtures/give_up/).ORDER AGAINST PATCH60. Both were built against the same orchestrator.py.
patch62's anchors are the import line, the interior of play_one_turn's discard
branch, and the bans reset; patch60's are read_matchup_reveal, the
select_and_play commit, and run()'s try/finally. Verified rather than reasoned
about: applied in BOTH orders on scratch copies, the resulting orchestrator.py
files are byte-identical (diff -q). patch60 landed first in the event, and
patch62 applies cleanly on top of it.WHAT IT DOES NOT DO. It does not make a discard happen. It refuses one the
game cannot grant, and it says out loud when one did not land -- which is the
measurement the next live match needs before anything else is changed.PRE-REGISTERED LIVE ACCEPTANCE, for the next live match:  * EVERY "[discard]" line shows a before count and an after count. A
    "[discard]" line with no numbers is a failed acceptance, not a partial
    one.
  * The number of "did NOT register" lines is REPORTED, whatever it is. This
    run is a measurement of how often the discard press plays the card
    instead; a zero is a result and so is a five.
  * DISCARD_LEDGER["discards_used_this_match"] never exceeds 2 in a match. It
    counts confirmed drops in the scoreboard's own count, so exceeding 2 means
    the reader is wrong and the patch is withdrawn.
  * The "[redraw]" line shows the dots' number beside vision's on EVERY turn,
    including turns that discard. Their disagreement rate over the match is
    the second number this run exists to collect.
  * ANY turn where the dots and vision disagree gets its frame kept and read.
    The dot discs sit outside both "is the scoreboard there" gates (see
    discard_dots' "WHAT IS NOT GUARDED"), and no frame in the 1,396 searched
    has anything covering a dot -- so the first one that does will show up
    here, as a disagreement, and it becomes a fixture in
    test_fixtures/discard_dots/ rather than an argument.Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch62.py [ROOT]
"""
import ast
import os
import shutil
import sysROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
ORCH = os.path.join(ROOT, "orchestrator.py")
MOD = os.path.join(ROOT, "discard_dots.py")
TEST = os.path.join(ROOT, "tests", "minigame", "test_discard_dots.py")
FIXDIR = os.path.join(ROOT, "test_fixtures", "discard_dots")
SRCDIR = os.path.join(ROOT, "overnight", "census", "reveal_edge_frames_20260908")# (source frame, fixture name, what it is). Picked BY LOOKING at the
# scoreboard crop of each, not by filename: t0231 is the DIMMED white-dark
# case (the game spotlights the scoreboard down to a third of its brightness
# on some frames) and carries the tightest dark dot in the whole census at
# -20.1, so it is the fixture a moved threshold breaks first.
FIXTURES = [
    ("t0083.21_e0.0799.jpg", "white_white_t0083.jpg"),
    ("t0130.48_e0.0710.jpg", "white_white_t0130.jpg"),
    ("t0191.52_e0.0873.jpg", "white_dark_t0191.jpg"),
    ("t0231.38_e0.0764.jpg", "white_dark_dimmed_t0231.jpg"),
    ("t0246.68_e0.0597.jpg", "world_no_scoreboard_t0246.jpg"),
]NEW_MODULE = r'''"""Read the DISCARDS row of the in-match scoreboard: how many discards are LEFT.WHY THIS EXISTS
---------------
The match loop decided "discard" from vision's `discards_left`, and vision's
number is not the game's. In the 2026-09-08 smoke run
(`overnight/smoke_cycle_20260908_2016.log`) it read 2 on nearly every turn and
3 or 4 on ten reads, each clamped to 0 by the "[repair] discards_left N outside
0-2" branch. Match 1 issued 15 discard decisions and match 3 issued 4 -- while
the SCOREBOARD says the game consumed exactly ONE discard in match 3. The other
three presses did something else, and `input_controller.select_and_discard`
ends in `confirm_play`, so the likeliest something else is that the card was
PLAYED. That is what the user watched happen.A ledger of our own presses would be wrong in the other direction: it would
stop discarding at two while the game still had two. The DOTS are the truth.WHAT THE DOTS ARE
-----------------
The scoreboard's lower panel carries two rows of dots: ROUND (five) and
DISCARDS (two). On the DISCARDS row a WHITE dot is an UNUSED discard and a DARK
dot a SPENT one, so this returns the number of white dots -- how many discards
remain. (The ROUND row uses the opposite sense, white = played. This module
does not read it.)Pure PIL + numpy: no OCR, no vision API, ~1.2 ms a call. The geometry is
FRACTIONAL, so the same constants read the 1920x1080 frames the census
recorder writes, the 960x540 half-scale ones, and the 2000px-wide frames
`orchestrator._fast_grab()` produces.THE CORPORA
-----------
  A  overnight/census/reveal_edge_frames_20260908   60 frames, 1920x1080,
     match 3's second half. 58 carry the scoreboard (26 WHITE-WHITE t0081.68
     to t0153.79, 32 WHITE-DARK t0189.96 to t0245.15) and 2 are the world
     (t0246.68, t0248.21). Labelled BY LOOKING at the scoreboard crop.
  B  overnight/census/match_timeline_20260908/frames   994 frames, 960x540,
     a whole match plus the next -- the half-scale check.
  C  EVERY 16:9 image under test_fixtures/ -- 342 of the 756 there, the rest
     being crops and contact sheets of other aspect ratios. 27 carry a
     scoreboard (reveal_trigger, reveal_occlusion, reveal_episode,
     prompt_detector, give_up) and 315 do not (world, dealer, localiser,
     pause menu, leg failures, chiaki's own host list). Defined by a GLOB
     rather than by hand, so it is reproducible: `agent_progress/patch62/fix/
     census.py` re-derives every number below and writes the file list beside
     them in census_files.json. Its geometry is duplicated from this module
     DELIBERATELY, so that moving a constant here cannot move the census that
     justifies it.Verified on A: 26 of 26 read 2, 32 of 32 read 1, 2 of 2 abstain -- no
exceptions. On B: 88 abstentions, every one of them a world frame, and the 906
reads run 2 -> 1 -> 0 through the first match, reset to 2 at the match
boundary (t0298.30, where the ROUND row also resets), then 2 -> 1 -> 0 again.
The only non-monotone step in 994 frames is that boundary.WHY EACH THRESHOLD SITS WHERE IT DOES (CLAUDE.md 10.4)
------------------------------------------------------
IS THE SCOREBOARD THERE AT ALL -- two conditions, both required.  BORDER CONTRAST, min(top border, bottom border) / panel mean. This is the
  statistic that SEPARATES:      scoreboard present   2.88 .. 4.58   n = 991  (A 58, B 906, C 27)
      not present          0.21 .. 2.22   n = 405  (A 2, B 88, C 315)  BORDER_MIN_RATIO = 2.55 is the midpoint of that gap: 0.33 clear of both.
  The worst absent frame at 2.22 is
  test_fixtures/table_prompt_cases/prompt_dark_b13_t05_it073.jpg -- a world
  frame with a bright window burning through behind the quest log.  A RATIO, not a difference, because the game DIMS the whole scoreboard on
  some frames (A's t0222..t0245: border 80 against 186, panel 21 against 46).
  An alpha blend towards black is multiplicative, so a ratio survives it while
  the difference falls from ~135 to ~60 and lands on top of the absent
  population.  Only the TOP and BOTTOM borders are read. The dimming is a spotlight, not a
  uniform fade: on those same frames the LEFT border collapses to 33 against a
  panel of 21 while top and bottom hold. Top and bottom span the panel's whole
  width, so they average across the gradient.  PANEL FLATNESS, the standard deviation of a patch of empty panel beside the
  dots. This one does NOT separate on its own and is not asked to:      scoreboard present   0.70 .. 2.45   n = 991
      not present          0.00 .. 83.45  n = 405  The 0.00 is chiaki's own host list (test_fixtures/not_streaming/
  hostlist_standby.png) -- Qt draws flat fills, which is the same fact
  CLAUDE.md section 3 uses to tell the stream from the UI. PANEL_FLAT_MAX =
  6.0 is a one-sided necessary condition: 2.4x above the whole present
  population, so it has never rejected a scoreboard, and it rejects 403 of the
  405 absent frames on its own.  BE CLEAR ABOUT WHAT FLATNESS IS FOR. On the corpus it has never been the
  DECIDING gate: the border ratio alone rejects all 133 absent frames, so no
  real frame on disk needs it. It is defence in depth on the $50 gate, and it
  is kept only because a test demonstrates it can fire -- a panel patch with
  the same MEAN and a standard deviation of 40 sails through the ratio at 4.08
  and is refused here. A guard nothing can trigger is the shape CLAUDE.md
  catalogues over and over; this one has a trigger and a check that exercises
  it. Its measured value is the margin it adds on the closest miss: the b13
  world frame sits 0.33 from the ratio gate and 30 from this one. With both
  conditions, 0 of 133 absent frames are read and 0 of 983 present ones are
  refused.WHITE DOT OR DARK DOT -- the dot's disc mean minus the panel mean, so a global
dim moves both together:      WHITE   +21.38 .. +88.09   n = 1417
      DARK    -41.33 .. -20.10   n =  565The gap (-20.10, +21.38) is empty -- no dot in 1,982 lands in it. The band
[DARK_MAX_CONTRAST, WHITE_MIN_CONTRAST] = [-5.0, +20.0] sits inside that gap
and a dot between the two is NOT classified: the read abstains rather than
guessing. The band exists so that a flat dark frame which somehow passed both
gates above cannot be read as "0 unused", which is the one answer that would
stop the bot discarding for the rest of a match.  THE WHITE MARGIN IS 1.38, NOT 17.3, AND AN EARLIER DRAFT OF THIS DOCSTRING
  SAID +37.28. It was measured on a hand-picked 60-frame slice of C; over
  EVERY 16:9 fixture the floor is +21.38, both dots of
  test_fixtures/give_up/give_up_dialog.jpg -- a real mid-match scoreboard
  dimmed behind the "Give up?" modal to a panel mean of 11.1. Checked BY EYE
  on the brightened crop: its DISCARDS row is two white dots, so the reader's
  2 is right and this is a genuine member of the white population, not a false
  positive. It is now a fixture, so the thinnest case is the one a moved
  constant breaks first.  The asymmetry is deliberate and the thin side is the safe one. "White" is
  the dangerous answer -- it is what grants permission to press discard -- so
  it demands the most evidence, and a white dot dimmed BELOW +20.0 falls into
  the band and ABSTAINS, which returns the caller to vision's number. A dark
  dot cannot mirror that failure: on a panel this dim its contrast is bounded
  by the panel mean itself (-11.1 here), so the dim direction pushes it toward
  the band too. Every crossing of either edge abstains; none misclassifies.WHAT IS NOT GUARDED: THE DOTS THEMSELVES
----------------------------------------
Both presence gates read pixels that are NOT the dots -- the top and bottom
borders, and an empty patch of panel to the right of them. Neither overlaps
either disc. So they answer "is the scoreboard on screen", and nothing here
answers "is anything sitting ON a dot". If a sprite ever covered ONE dot while
leaving the borders and the panel patch intact, that dot's own contrast would
decide the read alone.NO SUCH FRAME EXISTS IN ANYTHING ON DISK, and that was looked for rather than
assumed: all 60 native frames of A, all 994 of B exhaustively, and all 342
16:9 fixtures of C -- including test_fixtures/reveal_occlusion (12 frames) and
reveal_trigger (5, the "PLAY BALL!" banner among them), which are the
project's own corpus of things that cover the screen mid-turn. 1,982 dots, and
the ambiguous band holds ZERO of them. In this game's UI the centred banners
and the card animations do not reach the top-left corner.NO GATE IS INVENTED FOR IT, deliberately. A threshold needs two measured
populations (CLAUDE.md 10.4) and there is no occluded population to measure --
inventing one from the un-occluded side alone is how four thresholds on this
project ended up inside a single distribution. What defends the dot instead is
the ambiguity band above, which is the reason it is wide toward white; a
partial cover drags a dot's contrast toward the panel and into it, and the
read abstains. `tests/minigame/test_discard_dots.py` paints out a real dot
with the panel's own mean and requires exactly that -- until it did, a mutant
that replaced the band with a guess survived the whole suite.AND THE CONSEQUENCE IS BOUNDED IN BOTH DIRECTIONS, which is why this is
documented rather than defended further:  read too DARK (a dot covered by something dim) -- the turn plays its card
  instead of discarding it. One turn's discard, and it is the direction this
  design already prefers everywhere else.  read too WHITE (a dot covered by something bright) -- the pre-press check
  lets a discard proceed that the game cannot grant. The press then plays the
  card, exactly as it does today, AND the after-press check sees no drop and
  logs "did NOT register" without touching the ledger. The over-read cannot
  inflate the count, because a count needs a drop between two reads and a
  systematically fooled reader is fooled the same way twice. Pinned by a flow
  test.The live acceptance therefore watches the dots-vs-vision disagreement rate,
and the first real occluded-dot frame to appear in a log becomes a fixture
here.WHAT IT WILL NOT DO
-------------------
Abstain is the ONLY failure mode. Every caller treats None as "carry on
believing whatever you believed", never as a count.
"""import numpy as np# --- Geometry, as fractions of the frame -----------------------------------
#
# Measured by pixel dump on
# overnight/census/reveal_edge_frames_20260908/t0083.21_e0.0799.jpg (1920x1080):
#
#   dot 1   disc x 236..254, y 338..356   ->  centre (245.0, 347)
#   dot 2   disc x 263..281, y 338..356   ->  centre (272.5, 347)   spacing 27.5
#   panel   top border    y 288..293      left border  x 50..55
#           bottom border y 367..371      right border x 377..382
#   empty panel, no dots and no label:    x 292..355, y 340..362
#
# The sample radius is 6 px at 1920 -- inside the disc's ~9 px radius, so it
# never reaches the dot's dark outline, and still 3 px at 960x540.
DOT_Y_FRAC = 347.0 / 1080          # 0.32130
DOT_X_FRACS = (245.0 / 1920,       # 0.12760
               272.5 / 1920)       # 0.14193
DOT_R_FRAC = 6.0 / 1920            # 0.003125, of the frame WIDTHPANEL_BOX = (292 / 1920, 340 / 1080, 355 / 1920, 362 / 1080)
TOP_BORDER_BOX = (60 / 1920, 288 / 1080, 375 / 1920, 294 / 1080)
BOTTOM_BORDER_BOX = (60 / 1920, 367 / 1080, 375 / 1920, 372 / 1080)# --- Thresholds. The docstring above carries the population either side of
# --- every one of them. Do not move one without re-measuring both.
BORDER_MIN_RATIO = 2.55            # present >= 2.88, absent <= 2.22
PANEL_FLAT_MAX = 6.0               # present <= 2.45 (one-sided; see above)
WHITE_MIN_CONTRAST = 20.0          # white dots >= +37.28
DARK_MAX_CONTRAST = -5.0           # dark dots <= -20.10# Every box above is a fraction of the GAME WINDOW, which is 16:9. The frames
# in the corpora are all within 0.0012 of that. A desktop grab -- which is what
# orchestrator._fast_grab() falls back to, loudly, when the game window cannot
# be found -- is 1.55, and every box would then land on different pixels.
ASPECT = 16.0 / 9.0
ASPECT_TOL = 0.02def _box(a, frac):
    """The pixels of `frac` = (x0, y0, x1, y1), fractions, at least 1x1."""
    h, w = a.shape
    x0, y0, x1, y1 = frac
    px0, py0 = int(x0 * w), int(y0 * h)
    px1, py1 = max(int(x1 * w), px0 + 1), max(int(y1 * h), py0 + 1)
    return a[py0:py1, px0:px1]def _disc_mean(a, cx_frac, cy_frac, r_frac):
    """Mean luminance inside a disc, centre and radius given as fractions."""
    h, w = a.shape
    cx, cy, r = cx_frac * w, cy_frac * h, max(r_frac * w, 1.0)
    x0, x1 = int(np.floor(cx - r)), int(np.ceil(cx + r)) + 1
    y0, y1 = int(np.floor(cy - r)), int(np.ceil(cy + r)) + 1
    ys, xs = np.mgrid[y0:y1, x0:x1]
    inside = ((xs - cx) ** 2 + (ys - cy) ** 2) <= r * r
    return float(a[y0:y1, x0:x1][inside].mean())def read_discard_dots(img):
    """(unused, detail) -- how many discards the SCOREBOARD says are left.    `img` is a PIL image of the game window, any size, 16:9. Returns
    (2 | 1 | 0, detail) when the scoreboard is on screen and both dots are
    unambiguous, and (None, why) otherwise. It never guesses: every rejection
    names the statistic that failed and the threshold it failed against, and
    every accepted read carries the numbers it was made on, so a log line is
    enough to re-derive the verdict.
    """
    if img is None:
        return None, "no frame"
    w, h = img.size
    if h <= 0 or abs(w / float(h) - ASPECT) > ASPECT_TOL:
        return None, (f"aspect {w}x{h} is not the game window's "
                      f"{ASPECT:.3f} +-{ASPECT_TOL}")    a = np.asarray(img.convert("L"), dtype=float)
    panel = _box(a, PANEL_BOX)
    panel_mean, panel_std = float(panel.mean()), float(panel.std())
    border = min(float(_box(a, TOP_BORDER_BOX).mean()),
                 float(_box(a, BOTTOM_BORDER_BOX).mean()))
    ratio = border / max(panel_mean, 1.0)
    base = (f"panel {panel_mean:.1f} flat {panel_std:.2f} "
            f"border {border:.1f} ratio {ratio:.2f}")    if ratio < BORDER_MIN_RATIO:
        return None, (f"no scoreboard: border ratio {ratio:.2f} < "
                      f"{BORDER_MIN_RATIO} -- {base}")
    if panel_std > PANEL_FLAT_MAX:
        return None, (f"no scoreboard: panel not flat ({panel_std:.2f} > "
                      f"{PANEL_FLAT_MAX}) -- {base}")    unused, marks = 0, []
    for x_frac in DOT_X_FRACS:
        contrast = _disc_mean(a, x_frac, DOT_Y_FRAC, DOT_R_FRAC) - panel_mean
        if contrast >= WHITE_MIN_CONTRAST:
            unused += 1
            marks.append(f"{contrast:+.1f} white")
        elif contrast <= DARK_MAX_CONTRAST:
            marks.append(f"{contrast:+.1f} dark")
        else:
            return None, (f"dot {len(marks) + 1} is neither ({contrast:+.1f} "
                          f"is between {DARK_MAX_CONTRAST} and "
                          f"{WHITE_MIN_CONTRAST}) -- {base}")
    return unused, f"unused {unused} [{', '.join(marks)}] -- {base}"
'''# --- the orchestrator edits -------------------------------------------------A_IMPORT = "import input_controller\n"
B_IMPORT = "import discard_dots\nimport input_controller\n"A_HELPERS = "def play_one_turn(state_json: dict, batters_used: int):"
B_HELPERS = '''# --- The DISCARDS dots: what the GAME says a discard cost -------------------
#
# THE DEFECT, verified on frames 2026-09-08. The discard decision was taken on
# vision's `discards_left`, and that number is not the game's: over the smoke
# run (overnight/smoke_cycle_20260908_2016.log) it read 2 on nearly every turn
# and 3 or 4 on ten reads, each clamped to 0 by the "[repair] discards_left N
# outside 0-2" branch. Match 1 issued FIFTEEN discard decisions and match 3
# issued four, while the scoreboard's own DISCARDS row says match 3 spent
# exactly ONE. The other presses did something else, and select_and_discard
# ends in confirm_play, so the likeliest something else is that the card was
# PLAYED -- which is what the user watched happen.
#
# Counting our own presses would be wrong the other way: it would stop
# discarding at two while the game still had two. The dots are the truth, and
# discard_dots.read_discard_dots reads them in ~1.2 ms with no OCR and no API
# call. It ABSTAINS rather than guessing, and every path below treats an
# abstention as "carry on believing vision", never as a count.
DISCARD_LEDGER = {"discards_used_this_match": 0}# The scoreboard does not repaint the instant the button is pressed, and
# SETTLE_REGION_SETS has no set for that region -- so the after-read polls the
# thing it actually cares about, the dot count, rather than waiting on pixels
# somewhere else. A timeout here is not an error: it IS the finding.
DISCARD_SETTLE_POLL_S = 0.25
DISCARD_SETTLE_MAX_S = 5.0def reset_discard_ledger():
    """Zero the per-match count of discards the SCOREBOARD confirmed.    Called exactly where bans_done_this_match resets, which is the one moment
    a new match has been paid for and started.
    """
    DISCARD_LEDGER["discards_used_this_match"] = 0def _capture_for_dots():
    """The frame the dot reader reads. Its own seam, so a test can replace it.    Returns None under BASEBALL_TEST_RUN: _fast_grab() falls back to a
    FULL-SCREEN grab when the game window cannot be located, and an offline
    test must never photograph the user's desktop (CLAUDE.md section 1, where
    that mistake logged the user's own work for 247 frames). The environment
    is read at CALL time, never captured in a default or at import time
    (sections 5 and 10.18).
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        return None
    return _fast_grab()def read_discard_dots_now():
    """(unused, detail) for the CURRENT screen, or (None, why)."""
    img = _capture_for_dots()
    if img is None:
        return None, "no frame"
    try:
        return discard_dots.read_discard_dots(img)
    except Exception as exc:                            # pragma: no cover
        return None, f"dot read raised {exc!r}"def _wait_for_discard_to_register(before):
    """Poll the dots until the count drops below `before`, or time out.    Returns (after, detail); `after` is None if the dots never read.    THE BOUND IS DISCARD_SETTLE_MAX_S PLUS ONE ITERATION, not exactly
    DISCARD_SETTLE_MAX_S: the deadline is checked BEFORE the sleep and the
    re-read, so the last iteration can start just inside it and finish just
    outside. The overrun is one poll plus one capture -- `_fast_grab()` is a
    local window grab, not an API call, so it is tens of milliseconds, and a
    turn running fractionally over five seconds is harmless. It is stated
    rather than tightened because the alternative is a second clock read whose
    only effect is to make a comment true.
    """
    deadline = time.time() + DISCARD_SETTLE_MAX_S
    after, detail = read_discard_dots_now()
    while (after is None or after >= before) and time.time() < deadline:
        time.sleep(DISCARD_SETTLE_POLL_S)
        after, detail = read_discard_dots_now()
    return after, detaildef play_one_turn(state_json: dict, batters_used: int):'''A_STATE = "        discards_left = 0\n\n    state = GameState("
B_STATE = '''        discards_left = 0    # THE SCOREBOARD'S OWN DISCARDS ROW, beside what vision said. Vision's
    # number is unreliable in both directions (see the block above
    # read_discard_dots_now); the dots are what the game did. Take the LOWER
    # of the two, because the damage is one-directional -- believing a discard
    # we do not have spends the turn PLAYING the card we meant to throw away.
    # An abstention leaves vision's number alone.
    dots_unused, dots_detail = read_discard_dots_now()
    redraws_left = (discards_left if dots_unused is None
                    else min(discards_left, dots_unused))    state = GameState('''A_REDRAWS = "        redraws_left=discards_left,\n    )"
B_REDRAWS = "        redraws_left=redraws_left,\n    )"A_BRANCH = "    if should_redraw(player_only, state):\n"
B_BRANCH = '''    dots_before, dots_before_detail = None, "not read"
    _redraw_wanted = should_redraw(player_only, state)
    if _redraw_wanted:
        # READ THE DOTS AGAIN, FROM A FRESH FRAME, immediately before the
        # irreversible press. The read above is a whole vision round-trip old,
        # and the PREVIOUS turn's discard may only have registered since.
        dots_before, dots_before_detail = read_discard_dots_now()
        if dots_before == 0:
            print(f"  [discard] dots say 0 unused -- vision said "
                  f"{discards_left}; playing ({dots_before_detail})")
            _redraw_wanted = False    if _redraw_wanted:
'''A_PRESS = "        select_and_discard(player_idx)\n        return False, None\n"
B_PRESS = '''        print(f"  [redraw] discarding: {state.redraws_left} discard(s) left "
              f"(vision {discards_left}, dots {dots_unused}) vs threshold "
              f"{REDRAW_POWER_THRESHOLD}")
        select_and_discard(player_idx)
        # DID IT REGISTER? A discard that did not is a card PLAYED, and until
        # this line nothing in the log told the two apart -- which is how
        # match 1 recorded fifteen discards of an allowance of two.
        if dots_before is None:
            print(f"  [discard] dots did not read before the press "
                  f"({dots_before_detail}) -- cannot say whether it "
                  f"registered")
        else:
            dots_after, dots_after_detail = _wait_for_discard_to_register(
                dots_before)
            if dots_after is None:
                print(f"  [discard] dots {dots_before} -> unreadable "
                      f"({dots_after_detail}) -- cannot say whether it "
                      f"registered")
            elif dots_after < dots_before:
                DISCARD_LEDGER["discards_used_this_match"] += 1
                print(f"  [discard] registered: dots {dots_before} -> "
                      f"{dots_after} "
                      f"({DISCARD_LEDGER['discards_used_this_match']} "
                      f"confirmed this match)")
            else:
                print(f"  [discard] did NOT register (dots {dots_before} -> "
                      f"{dots_after}) -- the card was most likely PLAYED")
        return False, None
'''A_WHY = ('        _why = ("NO DISCARDS LEFT — this hand was not kept on merit"\n'
         '                if state.redraws_left <= 0 else "hand is strong enough")\n')
B_WHY = '''        if dots_before == 0:
            _why = ("the DOTS say NO DISCARDS LEFT — this hand was not kept "
                    "on merit, and vision disagreed")
        elif state.redraws_left <= 0:
            _why = "NO DISCARDS LEFT — this hand was not kept on merit"
        else:
            _why = "hand is strong enough"
'''A_KEEP = ('        print(f"  [redraw] keeping the hand: best power {_best} vs threshold "\n'
          '              f"{REDRAW_POWER_THRESHOLD}, {state.redraws_left} discard(s) "\n'
          '              f"left — {_why}")\n')
B_KEEP = ('        print(f"  [redraw] keeping the hand: best power {_best} vs threshold "\n'
          '              f"{REDRAW_POWER_THRESHOLD}, {state.redraws_left} discard(s) "\n'
          '              f"left (vision {discards_left}, dots {dots_unused}) "\n'
          '              f"— {_why}")\n')A_BANS = "                bans_done_this_match = False   # new match, bans are due again\n"
B_BANS = ('                bans_done_this_match = False   # new match, bans are due again\n'
          '                # ... and so is the per-match discard ledger, which counts\n'
          '                # only the discards the SCOREBOARD confirmed.\n'
          '                reset_discard_ledger()\n')NEW_TEST = r'''"""The DISCARDS dots, and the discard branch that now reads them.WHY THIS EXISTS
---------------
The match loop decided "discard" from vision's `discards_left`. In the
2026-09-08 smoke run vision read 2 on nearly every turn; match 1 issued FIFTEEN
discard decisions and match 3 issued four, while the scoreboard's DISCARDS row
says match 3 spent exactly ONE. Three of those four presses did something else,
and select_and_discard ends in confirm_play, so the card was most likely
PLAYED. Nothing in the code or the log could tell the two apart.These checks are about the READER and about the BRANCH:  1. Six real frames, picked by looking at the scoreboard crop of each, must
     read 2, 2, 1, 1, None and 2. The dimmed white-dark frame carries the
     tightest dark dot in the whole census (-20.1); the "Give up?" modal frame
     carries the dimmest white pair (+21.4 / +23.0, the white population's
     floor), so between them they are what a moved threshold breaks first.
  2. Every threshold is required to sit BETWEEN two populations that are
     written down HERE as literals. CLAUDE.md 10.11: a test that asserts
     against the constant it guards rises with the constant and passes
     forever.
  3. Each gate with a frame only IT rejects, including the ambiguity band --
     the ONLY thing guarding the dots themselves, and unreachable by any real
     frame, so it gets a synthetic dot painted out at the panel's brightness.
  4. The branch, driven through the REAL play_one_turn with the dot reader and
     the input calls stubbed, asserting on the CALLS: dots of 0 must PLAY, not
     discard; an after-read that did not drop must log "did NOT register" and
     must not increment the ledger; one that dropped, on the first poll or a
     later one, must increment it; an ABSTENTION must leave vision's number
     alone rather than folding in as zero; and an over-reading dot must not be
     able to inflate the ledger.Offline: no game, no API, no input, no capture.
"""import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)import contextlib
import io
import os# Set BEFORE orchestrator (and through it input_controller) is imported: it is
# what holds every input path off, and it is also what makes _capture_for_dots
# refuse to photograph the desktop.
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")import numpy as np
from PIL import Imageimport discard_dots as ddfailures = []def check(cond, msg):
    if not cond:
        failures.append(msg)FIXROOT = os.path.join(_ROOT, "test_fixtures")
FIX = os.path.join(FIXROOT, "discard_dots")# ===========================================================================
# 1. The six frames
#
# Five are copied into test_fixtures/discard_dots/ by the patch. The sixth is
# referenced where it already lives: give_up/give_up_dialog.jpg is the DIMMEST
# scoreboard on disk (panel mean 11.1, behind the "Give up?" modal) and it
# carries the whole white population's floor at +21.4 / +23.0, 1.4 above
# WHITE_MIN_CONTRAST. Without it the tightest white here is +41.5 and the
# constant could be raised to 41 with nothing failing.
# ===========================================================================
CASES = [
    ("discard_dots/white_white_t0083.jpg", 2, "both discards unused"),
    ("discard_dots/white_white_t0130.jpg", 2, "both discards unused"),
    ("discard_dots/white_dark_t0191.jpg", 1, "one spent"),
    ("discard_dots/white_dark_dimmed_t0231.jpg", 1, "one spent, dimmed"),
    ("discard_dots/world_no_scoreboard_t0246.jpg", None, "the world"),
    ("give_up/give_up_dialog.jpg", 2, "the dimmest scoreboard on disk"),
]
_read = {}
for _name, _want, _what in CASES:
    _path = os.path.join(FIXROOT, _name)
    check(os.path.exists(_path), f"missing fixture {_name}")
    if not os.path.exists(_path):
        continue
    _got, _detail = dd.read_discard_dots(Image.open(_path))
    _read[_name] = (_got, _detail)
    check(_got == _want,
          f"{_name} ({_what}) read {_got!r}, expected {_want!r} - {_detail}")# ANTI-VACUITY: the five fixtures must not all give the same answer, or a
# reader that returns a constant passes every line above.
check(len({v[0] for v in _read.values()}) == 3,
      f"the fixtures cover only {sorted({str(v[0]) for v in _read.values()})} "
      "- a reader returning a constant would pass")# ===========================================================================
# 2. Per-fixture statistics, pinned as literals
#
# Recomputed here rather than trusted, so that moving a dot centre or a box by
# a few pixels fails EVEN IF the verdict happens to survive. Measured
# 2026-09-08 on these exact files.
# ===========================================================================
MEASURED = {
    # name: (panel flatness, border ratio, (dot1 contrast, dot2 contrast))
    "discard_dots/white_white_t0083.jpg": (1.78, 3.96, (80.3, 84.1)),
    "discard_dots/white_white_t0130.jpg": (1.72, 3.88, (81.0, 82.9)),
    "discard_dots/white_dark_t0191.jpg": (1.77, 4.12, (82.3, -38.5)),
    "discard_dots/white_dark_dimmed_t0231.jpg": (1.04, 3.83, (41.5, -20.1)),
    "discard_dots/world_no_scoreboard_t0246.jpg": (20.02, 0.68, (-7.4, -34.0)),
    "give_up/give_up_dialog.jpg": (0.70, 3.81, (21.4, 23.0)),
}def _stats(path):
    a = np.asarray(Image.open(path).convert("L"), dtype=float)
    panel = dd._box(a, dd.PANEL_BOX)
    pm, ps = float(panel.mean()), float(panel.std())
    border = min(float(dd._box(a, dd.TOP_BORDER_BOX).mean()),
                 float(dd._box(a, dd.BOTTOM_BORDER_BOX).mean()))
    dots = tuple(dd._disc_mean(a, x, dd.DOT_Y_FRAC, dd.DOT_R_FRAC) - pm
                 for x in dd.DOT_X_FRACS)
    return ps, border / max(pm, 1.0), dotsfor _name, (_flat, _ratio, _dots) in MEASURED.items():
    _p = os.path.join(FIXROOT, _name)
    if not os.path.exists(_p):
        continue
    _f, _r, _d = _stats(_p)
    check(abs(_f - _flat) < 0.05,
          f"{_name} panel flatness is {_f:.2f}, recorded {_flat}")
    check(abs(_r - _ratio) < 0.05,
          f"{_name} border ratio is {_r:.2f}, recorded {_ratio}")
    for _i, (_a, _b) in enumerate(zip(_d, _dots)):
        check(abs(_a - _b) < 0.5,
              f"{_name} dot {_i + 1} contrast is {_a:+.1f}, recorded {_b:+.1f}"
              " - the sample geometry moved")# ===========================================================================
# 3. Every threshold between two MEASURED populations (CLAUDE.md 10.4, 10.11)
#
# The census is written down here as LITERALS. The constants are required to
# lie between them, so raising a constant cannot make its own check pass.
#
# Populations, 2026-09-08, re-derived from scratch by
# agent_progress/patch62/fix/census.py (which duplicates the geometry rather
# than importing it, and saves the file list to census_files.json): 991 frames
# with the scoreboard (58 native 1920x1080 + 906 half-scale 960x540 + 27 of
# the 342 16:9 test_fixtures images) and 405 without (2 + 88 + 315); 1417
# white dots and 565 dark ones, and ZERO in the band between them.
#
# WHITE_CONTRAST_MIN WAS 37.28 IN THE FIRST DRAFT AND THAT WAS WRONG - it came
# from a hand-picked 60-fixture slice. The true floor is +21.38, both dots of
# give_up/give_up_dialog.jpg, which leaves WHITE_MIN_CONTRAST a margin of 1.38
# rather than 17.3. Nothing moves as a result: the constant still sits between
# the populations, and the failure direction when a dot crosses it is
# ABSTENTION, not a wrong count. But a test that overstates its own margin by
# 12x is not a guard, so the literal is the measured one.
# ===========================================================================
PRESENT_RATIO_MIN = 2.88
ABSENT_RATIO_MAX = 2.22
PRESENT_FLAT_MAX = 2.45
WHITE_CONTRAST_MIN = 21.38
DARK_CONTRAST_MAX = -20.10check(ABSENT_RATIO_MAX < dd.BORDER_MIN_RATIO < PRESENT_RATIO_MIN,
      f"BORDER_MIN_RATIO {dd.BORDER_MIN_RATIO} is not between the measured "
      f"populations: absent tops out at {ABSENT_RATIO_MAX}, present bottoms "
      f"out at {PRESENT_RATIO_MIN}")
check(dd.PANEL_FLAT_MAX > PRESENT_FLAT_MAX,
      f"PANEL_FLAT_MAX {dd.PANEL_FLAT_MAX} cuts into the present population, "
      f"whose flattest-but-one reaches {PRESENT_FLAT_MAX} - it would refuse "
      "real scoreboards")
check(DARK_CONTRAST_MAX < dd.DARK_MAX_CONTRAST
      < dd.WHITE_MIN_CONTRAST < WHITE_CONTRAST_MIN,
      f"the dot band [{dd.DARK_MAX_CONTRAST}, {dd.WHITE_MIN_CONTRAST}] is not "
      f"inside the empty gap ({DARK_CONTRAST_MAX}, {WHITE_CONTRAST_MIN}) "
      "between the measured dark and white populations")# --- Each gate on its own, with a frame only IT rejects ---------------------
#
# Both gates are redundant on the five fixtures above, so a mutant that
# deletes either one survives them. These two checks are what make each gate
# provable: a guard whose trigger nothing can reach is the shape CLAUDE.md
# catalogues (section 10.1), and a test that cannot tell it is gone is how one
# gets deleted by accident.# THE BORDER RATIO, alone. chiaki's own host list is a REAL frame with a
# perfectly flat patch where the panel would be (Qt draws flat fills -
# CLAUDE.md section 3), so the flatness gate passes it at 0.00 and only the
# ratio refuses it.
_host = os.path.join(_ROOT, "test_fixtures", "not_streaming",
                     "hostlist_standby.png")
if os.path.exists(_host):
    _hv, _hd = dd.read_discard_dots(Image.open(_host))
    check(_hv is None,
          f"chiaki's own host list was read as {_hv!r} discards - its panel "
          f"patch is FLAT (0.00), so only the border ratio can refuse it: "
          f"{_hd}")
    check("border ratio" in _hd,
          f"the host list was refused for the wrong reason: {_hd}")# THE FLATNESS GATE, alone. A panel patch with the SAME MEAN and a standard
# deviation of 40 leaves the border ratio untouched (4.08, well over the gate)
# and only flatness refuses it. Synthetic on purpose: it is a control for the
# gate, not evidence about the game.
_ctl_path = os.path.join(FIX, "white_white_t0083.jpg")
if os.path.exists(_ctl_path):
    _src = Image.open(_ctl_path).convert("RGB")
    _a = np.asarray(_src).copy()
    _h, _w, _ = _a.shape
    _x0, _y0 = int(dd.PANEL_BOX[0] * _w), int(dd.PANEL_BOX[1] * _h)
    _x1, _y1 = int(dd.PANEL_BOX[2] * _w), int(dd.PANEL_BOX[3] * _h)
    _mean = _a[_y0:_y1, _x0:_x1].astype(float).mean()
    _ys, _xs = np.mgrid[0:_y1 - _y0, 0:_x1 - _x0]
    _board = np.where(((_xs + _ys) % 2) == 0, _mean - 40, _mean + 40)
    _a[_y0:_y1, _x0:_x1] = np.clip(_board, 0, 255).astype(np.uint8)[:, :, None]
    _rough, _rd = dd.read_discard_dots(Image.fromarray(_a))
    check(_rough is None,
          f"a panel patch with the same mean and a spread of 40 was read as "
          f"{_rough!r} - the flatness gate is not doing anything: {_rd}")
    check("not flat" in _rd,
          f"the rough panel was refused for the wrong reason: {_rd}")
    # THE CONTROL for the control: the same frame, unmodified, still reads 2.
    check(dd.read_discard_dots(_src)[0] == 2,
          "the unmodified frame stopped reading 2 - the check above proves "
          "nothing if the reader refuses everything")# THE AMBIGUITY BAND, alone -- and it is the ONLY thing guarding the dots.
#
# Both presence gates read the borders and an empty patch of panel. Neither
# overlaps either disc, so nothing above answers "is something sitting ON a
# dot". No frame on disk has one: 1,982 dots across all three corpora and the
# band holds zero of them, reveal_occlusion and reveal_trigger included. So
# the band is unreachable by any real frame, and until this check existed a
# mutant that replaced it with a guess ("treat an ambiguous dot as dark")
# survived the entire suite. That is CLAUDE.md 10.1's shape exactly: a guard
# nothing can trigger.
#
# The control paints dot 2 out with the panel's OWN mean, which is what a
# partial cover does to a dot's contrast - drags it toward zero. Synthetic on
# purpose: it is a control for the band, not evidence about the game.
_amb_src = os.path.join(FIX, "white_dark_t0191.jpg")
if os.path.exists(_amb_src):
    _im = Image.open(_amb_src).convert("RGB")
    _a2 = np.asarray(_im).copy()
    _h2, _w2, _ = _a2.shape
    _pm = _a2[int(dd.PANEL_BOX[1] * _h2):int(dd.PANEL_BOX[3] * _h2),
              int(dd.PANEL_BOX[0] * _w2):int(dd.PANEL_BOX[2] * _w2)
              ].astype(float).mean()
    _cx = dd.DOT_X_FRACS[1] * _w2
    _cy, _r2 = dd.DOT_Y_FRAC * _h2, dd.DOT_R_FRAC * _w2 * 2.0
    _yy, _xx = np.mgrid[0:_h2, 0:_w2]
    _a2[((_xx - _cx) ** 2 + (_yy - _cy) ** 2) <= _r2 * _r2] = int(round(_pm))
    _amb, _amb_detail = dd.read_discard_dots(Image.fromarray(_a2))
    check(_amb is None,
          f"a dot painted out at the panel's own brightness was read as "
          f"{_amb!r} discards - an ambiguous dot must ABSTAIN, never be "
          f"guessed: {_amb_detail}")
    check("is neither" in _amb_detail,
          f"the covered dot was refused for the wrong reason: {_amb_detail}")
    # THE CONTROL for the control: untouched, the same frame still reads 1.
    check(dd.read_discard_dots(_im)[0] == 1,
          "the unmodified frame stopped reading 1 - the check above proves "
          "nothing if the reader refuses everything")# A frame that is not the game window's 16:9 must abstain, whatever is on it:
# _fast_grab falls back to a desktop grab (aspect ~1.55) and every box here
# would then land on different pixels.
_sq = Image.open(os.path.join(FIX, "white_white_t0083.jpg")).resize((900, 900))
check(dd.read_discard_dots(_sq)[0] is None,
      "a non-16:9 frame was read - the fractional geometry does not apply to "
      "a desktop grab")
check(dd.read_discard_dots(None)[0] is None, "None was read as a count")# ===========================================================================
# 4. The discard branch, through the REAL play_one_turn
# ===========================================================================
import orchestrator as orch# The shipped poll literals, pinned before they are shrunk for speed.
check(orch.DISCARD_SETTLE_POLL_S == 0.25,
      f"DISCARD_SETTLE_POLL_S is {orch.DISCARD_SETTLE_POLL_S}, not 0.25")
check(orch.DISCARD_SETTLE_MAX_S == 5.0,
      f"DISCARD_SETTLE_MAX_S is {orch.DISCARD_SETTLE_MAX_S}, not 5.0")# The seam that keeps an offline run off the user's screen.
check(orch._capture_for_dots() is None,
      "_capture_for_dots grabbed a frame under BASEBALL_TEST_RUN - an offline "
      "test must never photograph the desktop")
check(orch.read_discard_dots_now()[0] is None,
      "read_discard_dots_now returned a count with no frame")def _turn_state(powers, discards_left):
    return {
        "phase": "batting", "your_score": 0, "opp_score": 0, "runners": [],
        "discards_left": discards_left,
        "hand": [{"kind": "player", "name": f"P{i}", "power": p,
                  "secondary": 0, "hand_index": i}
                 for i, p in enumerate(powers)],
    }class Flow:
    """A scripted dot reader plus a recorder for the two irreversible calls."""    def __init__(self, reads):
        self.reads = list(reads)
        self.calls = 0
        self.discarded = []
        self.played = []    def read(self):
        self.calls += 1
        v = self.reads[min(self.calls - 1, len(self.reads) - 1)]
        return v, f"stub {v}"@contextlib.contextmanager
def driven(flow):
    saved = (orch.read_discard_dots_now, orch.select_and_discard,
             orch.select_and_play, orch.press,
             orch.DISCARD_SETTLE_POLL_S, orch.DISCARD_SETTLE_MAX_S)
    orch.read_discard_dots_now = flow.read
    orch.select_and_discard = lambda idx, *a, **k: flow.discarded.append(idx)
    orch.select_and_play = lambda idx, *a, **k: flow.played.append(idx)
    orch.press = lambda *a, **k: None
    # Real seconds, shrunk: the "did NOT register" flow polls until the cap.
    orch.DISCARD_SETTLE_POLL_S = 0.01
    orch.DISCARD_SETTLE_MAX_S = 0.05
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            yield buf
    finally:
        (orch.read_discard_dots_now, orch.select_and_discard,
         orch.select_and_play, orch.press,
         orch.DISCARD_SETTLE_POLL_S, orch.DISCARD_SETTLE_MAX_S) = saved# --- (a) the dots say 0 right before the press: PLAY, do not discard --------
# The early read says 2, so should_redraw fires exactly as it does today; the
# fresh read taken immediately before the irreversible press says 0.
orch.reset_discard_ledger()
f_a = Flow([2, 0])
with driven(f_a) as out_a:
    played_a, _ = orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_a = out_a.getvalue()
check(f_a.calls >= 2,
      f"the stubbed reader was called {f_a.calls} times - the branch never "
      "consulted the dots, so nothing below is testing anything")
check(f_a.discarded == [],
      f"discarded {f_a.discarded} with the dots reading 0 unused - the game "
      "has no discard to give and the press plays the card instead")
check(f_a.played != [],
      "the turn neither discarded nor played - a turn must do one of them")
check(played_a is True,
      "play_one_turn reported a discard turn when it played the card")
check("dots say 0 unused" in text_a,
      f"the refusal was silent. Output was: {text_a!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 0,
      "a refused discard was counted in the ledger")# --- (b) min(vision, dots): vision says 2, the dots say 0 -------------------
#
# The second scripted read is None ON PURPOSE. It is what isolates min() from
# the pre-press veto in (a): with the min applied, redraws_left is 0 and
# should_redraw never fires, so the second read is never taken. With the min
# dropped, redraws_left is vision's 2, should_redraw fires, and the pre-press
# read ABSTAINS - so `dots_before == 0` is False and the discard goes ahead.
# Scripted as [0] alone, both arms refuse and the mutant survives; measured.
orch.reset_discard_ledger()
f_b = Flow([0, None])
with driven(f_b) as out_b:
    played_b, _ = orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_b = out_b.getvalue()
line_b = next((ln for ln in text_b.splitlines() if "[redraw]" in ln), "")
check(f_b.calls >= 1, "the reader was never called on the min() path")
check(f_b.discarded == [],
      f"discarded {f_b.discarded} on an all-weak hand while the DOTS said 0 "
      "unused - vision's 2 was used as-is")
check(played_b is True, "the hand was not played")
check(line_b != "", f"no [redraw] line at all. Output was: {text_b!r}")
check("vision 2" in line_b and "dots 0" in line_b,
      f"the [redraw] line does not carry BOTH numbers: {line_b!r}")# --- (c) the press did not register: say so, and do not count it ------------
orch.reset_discard_ledger()
f_c = Flow([2, 2, 2])
with driven(f_c) as out_c:
    played_c, _ = orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_c = out_c.getvalue()
check(f_c.discarded == [0] or f_c.discarded == [2],
      f"the discard did not happen ({f_c.discarded}) - with both numbers at 2 "
      "and an all-weak hand it must")
check(played_c is False, "a discard turn reported itself as a play")
check("did NOT register" in text_c,
      f"a discard whose dot count never dropped was not reported. Output was: "
      f"{text_c!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 0,
      f"the ledger counted an unregistered discard "
      f"({orch.DISCARD_LEDGER['discards_used_this_match']}) - it counts "
      "presses, not what the game granted")
check(f_c.calls >= 3,
      f"the reader was called {f_c.calls} times - there is no after-read")# --- (d) the press registered: count it -------------------------------------
orch.reset_discard_ledger()
f_d = Flow([2, 2, 1])
with driven(f_d) as out_d:
    orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_d = out_d.getvalue()
check("registered: dots 2 -> 1" in text_d,
      f"a registered discard was not reported with its numbers. Output was: "
      f"{text_d!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 1,
      f"the ledger says {orch.DISCARD_LEDGER['discards_used_this_match']} "
      "after one confirmed discard")
check("did NOT register" not in text_d,
      "a discard the scoreboard confirmed was reported as not registering")# --- (e) the drop appears on a LATER poll, not the first --------------------
#
# The settle poll exists because the scoreboard does not repaint the instant
# the button is pressed. Every flow above either drops on the very first
# after-read or never drops at all, so the loop BODY never executes in any of
# them - and a mutant weakening its condition from `after >= before` to
# `after > before` (an ordinary off-by-one) survived all of them. With that
# mutant a discard that needs one more poll is reported as "did NOT register",
# which is the exact race DISCARD_SETTLE_MAX_S exists to give time for.
orch.reset_discard_ledger()
f_e = Flow([2, 2, 2, 1])
with driven(f_e) as out_e:
    orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_e = out_e.getvalue()
check(f_e.discarded != [], "the late-drop flow never discarded")
check("registered: dots 2 -> 1" in text_e,
      f"a discard that registered on the SECOND poll was not seen - the "
      f"settle loop gave up after one read. Output was: {text_e!r}")
check("did NOT register" not in text_e,
      f"a discard the scoreboard confirmed one poll late was reported as not "
      f"registering. Output was: {text_e!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 1,
      f"the ledger says {orch.DISCARD_LEDGER['discards_used_this_match']} "
      "after a discard that registered on the second poll")
check(f_e.calls >= 4,
      f"the reader was called {f_e.calls} times - the poll never took a "
      "second after-read, so nothing above tests the loop body")# --- (f) an ABSTENTION must bypass min(), not fold in as zero ---------------
#
# `redraws_left = discards_left if dots_unused is None else min(...)`. Writing
# it as `min(discards_left, dots_unused or 0)` looks like the same thing and
# is not: it turns "the dots could not read" into "the dots say zero", which
# disables the discard branch for the turn with NO log line, because
# should_redraw short-circuits on redraws_left <= 0 long before any of the
# "[discard]" logging is reached. That mutant survived every other check here.
# The dots abstain on any capture failure, not only on the documented aspect
# fallback, so this is the ordinary case and not an exotic one.
orch.reset_discard_ledger()
f_f = Flow([None, 2, 2, 1])
with driven(f_f) as out_f:
    orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_f = out_f.getvalue()
line_f = next((ln for ln in text_f.splitlines() if "[redraw]" in ln), "")
check(f_f.discarded != [],
      f"the turn did not discard ({f_f.discarded}) although vision said 2 and "
      "the dots merely ABSTAINED - an abstention was folded in as zero")
check("vision 2" in line_f and "dots None" in line_f,
      f"the [redraw] line does not show the abstention beside vision's "
      f"number: {line_f!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 1,
      "the discard that followed an abstained first read was not counted")# --- (g) an OVER-READ cannot inflate the ledger -----------------------------
#
# The bound on the one thing the presence gates do not cover (see
# discard_dots' "WHAT IS NOT GUARDED"): if something bright ever covered a
# spent dot, the reader would say 1 where the truth is 0, and the pre-press
# check would let the discard through. It still cannot corrupt the count. A
# count needs a DROP between two reads, and a reader fooled by a sprite is
# fooled the same way twice - so the after-read matches the before-read, the
# turn logs "did NOT register", and the ledger stays where it was. That is the
# self-correction this patch exists to provide, and it is asserted, not
# assumed.
orch.reset_discard_ledger()
f_g = Flow([1, 1, 1])
with driven(f_g) as out_g:
    orch.play_one_turn(_turn_state([4, 5, 4], 2), 0)
text_g = out_g.getvalue()
check(f_g.discarded != [],
      "the over-read flow never pressed discard, so it does not test the "
      "over-read at all")
check("did NOT register" in text_g,
      f"an over-read discard that the game never granted was not reported. "
      f"Output was: {text_g!r}")
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 0,
      f"a discard the game never granted was counted "
      f"({orch.DISCARD_LEDGER['discards_used_this_match']}) - an over-reading "
      "dot would then inflate the per-match ledger")# --- (h) the ledger resets ---------------------------------------------------
orch.reset_discard_ledger()
check(orch.DISCARD_LEDGER["discards_used_this_match"] == 0,
      "reset_discard_ledger did not zero the ledger")if failures:
    for f in failures:
        print("FAIL:", f)
    raise SystemExit(1)
print(f"OK: discard dots read {len(CASES)} real frames correctly, every "
      f"threshold sits between two measured populations and every gate has a "
      f"frame only it rejects, and the discard branch refuses a discard the "
      f"dots say does not exist, keeps vision's number when they abstain, "
      f"reports one that did not register, and counts only the ones the "
      f"scoreboard granted - on the first poll or a later one")
'''# --- ASSERT EVERYTHING FIRST, THEN WRITE (CLAUDE.md 10.19) -----------------assert os.path.isdir(ROOT), ROOT
assert os.path.exists(ORCH), ORCH
assert os.path.isdir(os.path.dirname(TEST)), os.path.dirname(TEST)
assert not os.path.exists(MOD), f"{MOD} already exists - patch62 already applied?"
assert not os.path.exists(TEST), f"{TEST} already exists"
assert os.path.isdir(SRCDIR), f"missing the census frames: {SRCDIR}"
for _src, _dst in FIXTURES:
    assert os.path.exists(os.path.join(SRCDIR, _src)), _srco = open(ORCH).read()
for name, anchor, count in [
        ("import", A_IMPORT, 1),
        ("helpers", A_HELPERS, 1),
        ("state", A_STATE, 1),
        ("redraws_left", A_REDRAWS, 1),
        ("branch", A_BRANCH, 1),
        ("press", A_PRESS, 1),
        ("why", A_WHY, 1),
        ("keep", A_KEEP, 1),
        ("bans", A_BANS, 1)]:
    got = o.count(anchor)
    assert got == count, f"anchor {name}: found {got}, expected {count}"# nothing that is NOT the discard branch may be touched, so these must not
# already exist
for absent in ("discard_dots", "DISCARD_LEDGER", "read_discard_dots_now",
               "reset_discard_ledger", "[discard]"):
    assert absent not in o, f"orchestrator.py already mentions {absent!r}"new = o
new = new.replace(A_IMPORT, B_IMPORT, 1)
new = new.replace(A_HELPERS, B_HELPERS, 1)
new = new.replace(A_STATE, B_STATE, 1)
new = new.replace(A_REDRAWS, B_REDRAWS, 1)
new = new.replace(A_BRANCH, B_BRANCH, 1)
new = new.replace(A_PRESS, B_PRESS, 1)
new = new.replace(A_WHY, B_WHY, 1)
new = new.replace(A_KEEP, B_KEEP, 1)
new = new.replace(A_BANS, B_BANS, 1)assert new != o
# every replacement landed
assert new.count("import discard_dots\n") == 1
assert new.count("def reset_discard_ledger():") == 1
assert new.count("def _capture_for_dots():") == 1
assert new.count("def read_discard_dots_now():") == 1
assert new.count("def _wait_for_discard_to_register(before):") == 1
assert new.count("dots_unused, dots_detail = read_discard_dots_now()") == 1
assert new.count("redraws_left=redraws_left,") == 1
assert new.count("redraws_left=discards_left,") == 0
assert new.count("_redraw_wanted = should_redraw(player_only, state)") == 1
assert new.count("    if _redraw_wanted:\n") == 2
assert new.count("should_redraw(player_only, state)") == 1
assert new.count("dots say 0 unused") == 1
assert new.count("did NOT register") == 1
assert new.count("registered: dots ") == 1
assert new.count('DISCARD_LEDGER["discards_used_this_match"] += 1') == 1
# the def and exactly one call, at the indentation of the bans reset
assert new.count("def reset_discard_ledger():") == 1
assert new.count("                reset_discard_ledger()\n") == 1
assert new.count("reset_discard_ledger()") == 2
assert new.count("(vision {discards_left}, dots {dots_unused})") == 2
# the branch's shape: the veto read comes BEFORE the press, the register check
# after it, and the ledger is only touched inside that check
assert (new.index("dots_before, dots_before_detail = read_discard_dots_now()")
        < new.index("select_and_discard(player_idx)")
        < new.index("dots_after, dots_after_detail = _wait_for_discard_to_register(")
        < new.index('DISCARD_LEDGER["discards_used_this_match"] += 1'))
# the helpers are defined before play_one_turn uses them
assert (new.index("def read_discard_dots_now():")
        < new.index("def play_one_turn(state_json: dict, batters_used: int):"))
# untouched: the threshold, the play path, the money path
assert new.count("REDRAW_POWER_THRESHOLD") == o.count("REDRAW_POWER_THRESHOLD") + 1
assert new.count("select_and_play(player_idx, tactics_idx)") == 1
assert new.count("balance -= 50") == o.count("balance -= 50") == 1ast.parse(new, filename="orchestrator.py")
ast.parse(NEW_MODULE, filename="discard_dots.py")
ast.parse(NEW_TEST, filename="test_discard_dots.py")# --- writes ----------------------------------------------------------------open(MOD, "w").write(NEW_MODULE)
open(ORCH, "w").write(new)
open(TEST, "w").write(NEW_TEST)
os.makedirs(FIXDIR, exist_ok=True)
for _src, _dst in FIXTURES:
    shutil.copyfile(os.path.join(SRCDIR, _src), os.path.join(FIXDIR, _dst))print("patch62 applied to", ROOT)
print("  new module:", MOD)
print("  new test:  ", TEST)
print("  fixtures:  ", FIXDIR, f"({len(FIXTURES)} frames)")
print("  orchestrator.py: the discard branch reads the scoreboard's DISCARDS")
print("  dots before and after the press; only a confirmed drop is counted")
