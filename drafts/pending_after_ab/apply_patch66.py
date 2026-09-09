"""patch66: the deal gate asks HOW FAR THE HAND HAS MOVED FROM WHERE IT STARTED, not
how much it moved since the last sample. Measured from 30 real gate windows.

WHY THE RISING EDGE CANNOT WORK, non-circularly (2026-09-08, two matches recorded at
60 fps: overnight/recordings/cycle_20260908_2239 + overnight/events/cycle_20260908_2239.jsonl;
scripts in agent_progress/hand-timing/). The 30 deal-gate windows were located in the
event log (a run of _fast_grab captures 0.15 s apart IS the gate polling), and each was
scored two ways against the recording:

  * comparing a window's FIRST and LAST frame -- a question the threshold cannot beg --
    splits the ELEVEN timeouts in two: SEVEN where the hand barely moved (2.4-8.4, so
    there was no deal to see) and FOUR where the hand plainly changed (19.3-33.4) while
    no single 0.15 s step ever reached 25 (their biggest steps: 8.9, 9.2, 12.9, 16.1).
    A card that slides in over two seconds spreads its motion across thirteen polls and
    a rising edge sees a fraction of it. That is not a threshold that needs tuning; it
    is the wrong question.
  * the right question separates cleanly. `mean|frame - baseline|`, baseline being the
    hand at the moment the gate started:

        NO DEAL (n=7)    4.1  5.5  6.8  9.3  9.3 10.1 11.5
        DEAL   (n=23)   20.0 21.6 29.1 29.4 29.8 31.9 31.9 32.0 34.3 34.6 34.9 35.9
                        36.2 37.2 37.5 39.9 40.1 40.6 41.2 46.8 48.8 49.1 50.1

    A gap of 11.5 to 20.0 with no overlap (10.4). HAND_DEAL_THRESHOLD = 15.0 is
    1.30x the highest no-deal and 0.75x the lowest deal.

WHAT IT BUYS, measured over the same 30 windows:

                              shipped (rising edge, 25)   baseline, 15
      deals detected                    19 / 30              23 / 30
      median wait                         8.5 s               5.5 s
      p90 / slowest real deal            n/a                 10.6 s / 15.0 s
      windows burning the full cap        11                   0

  Every real deal crossed by 15.0 s, so DEAL_BASELINE_MAX_WAIT = 20.0 carries a third
  of margin and the seven no-deal turns cost 20 s instead of 35. Together that is about
  three minutes of a twenty-two minute match.

HONEST LIMITS. n=7 on the no-deal side, from one cycle of two matches, one session. The
gap is wide (1.74x) and the mechanism is understood, but the rate is not established.
The threshold stays a call-time knob (BASEBALL_DEAL_THRESHOLD, patch65) so the next
cycle can move it without a code edit, and the heartbeat already prints the statistic in
force, so every future turn reports where it sat.

Applies to: orchestrator.py. Extends tests/minigame/test_reveal_peak.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch66.py [ROOT]
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
OP = os.path.join(ROOT, "orchestrator.py")
TP = os.path.join(ROOT, "tests", "minigame", "test_reveal_peak.py")
O = open(OP).read(); T = open(TP).read()

A1 = "POST_PLAY_DEAL_MAX_WAIT = 35.0\n"
A6 = "HAND_DEAL_THRESHOLD = 25.0\n"
A2 = '''    start = time.time()
    prev = _grab_settle_regions(("hand",))["hand"]
    seen = False
    th = hand_deal_threshold()
    biggest = 0.0
    last_beat = start
'''
A3 = '''        d = _mean_abs_delta(prev, cur)
        biggest = max(biggest, d)
'''
A4 = "        prev = cur\n"
A5 = "def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,\n"
for a in (A1, A2, A3, A4, A5, A6):
    assert O.count(a) == 1, (O.count(a), a[:50])
assert O.count("HAND_DEAL_THRESHOLD = 25.0") == 1 and O.count("baseline") == 0
assert O.count("hand_deal_threshold") == 3      # the def and its two call sites

R1 = """# 20.0, was 35.0: over 30 real gate windows recorded at 60 fps on 2026-09-08 EVERY
# deal crossed the threshold below by 15.0 s (p50 5.5, p90 10.6), so 20 s carries a third
# of margin. The old 35 was sized for the rising-edge gate, which missed 11 of 30 windows
# and paid the whole cap for each. A cap costs time only on a turn with no deal.
POST_PLAY_DEAL_MAX_WAIT = 20.0
"""
R6 = """# 15.0, WAS 25.0 AND A DIFFERENT QUANTITY. The gate now measures how far the hand has
# moved from where it was when the gate STARTED, not how much it moved since the previous
# sample. Measured non-circularly over 30 real gate windows (agent_progress/hand-timing/):
#     no deal (n=7)    4.1  5.5  6.8  9.3  9.3 10.1 11.5
#     deal   (n=23)   20.0 21.6 29.1 ... 49.1 50.1
# 15.0 sits in that gap, 1.30x above the highest no-deal and 0.75x the lowest deal. The
# rising-edge statistic it replaces cannot see a card that slides in over two seconds,
# because that motion is divided among the thirteen polls that carry it -- four of the
# eleven live timeouts were exactly that, with total movement 19.3-33.4 and no step over
# 16.1. Read through hand_deal_threshold(), so a sweep moves it without a code edit.
HAND_DEAL_THRESHOLD = 15.0
"""
R2 = '''    start = time.time()
    # THE BASELINE: the hand as it was when this gate started. Every later frame is
    # compared against THIS, not against its predecessor, so a gradual deal accumulates
    # instead of being divided among the polls that carried it.
    baseline = _grab_settle_regions(("hand",))["hand"]
    seen = False
    th = hand_deal_threshold()
    biggest = 0.0
    last_beat = start
'''
R3 = '''        d = _mean_abs_delta(baseline, cur)
        biggest = max(biggest, d)
'''
R4 = "\n"        # the baseline is fixed: nothing to carry forward
R5 = '''def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,
'''
O2 = O.replace(A1, R1, 1).replace(A6, R6, 1).replace(A2, R2, 1).replace(A3, R3, 1).replace(A4, R4, 1)
# the knob's default becomes the baseline threshold: one number, one meaning.
B1 = "    if raw is None:\n        return HAND_DEAL_THRESHOLD\n"
assert O2.count(B1) == 1
O2 = O2.replace(B1, "    if raw is None:\n        return HAND_DEAL_THRESHOLD\n", 1)

ast.parse(O2)
assert O2.count("_mean_abs_delta(baseline, cur)") == 1
assert O2.count("_mean_abs_delta(prev, cur)") == 0
# NOT the bare substring: `prev = cur` also matches `prev = current`, which two other
# settle functions use and must keep (10.10 -- count the occurrences first).
assert O2.count("        prev = cur\n") == 0
# wait_for_screen_to_settle and its sibling keep their own `prev = _grab_settle_regions(names)`;
# only the deal gate's `(("hand",))["hand"]` form is replaced.
assert O2.count("prev = _grab_settle_regions") == 2
assert O2.count('prev = _grab_settle_regions(("hand",))["hand"]') == 0
assert O2.count("HAND_DEAL_THRESHOLD = 15.0") == 1 and O2.count("HAND_DEAL_THRESHOLD = 25.0") == 0
# One constant, one meaning: no dead 25.0 left beside the live 15.0.
assert O2.count("HAND_DEAL_THRESHOLD") == 3   # the definition, the knob default, one comment
assert O2.count("POST_PLAY_DEAL_MAX_WAIT = 20.0") == 1

EXTRA = '''
# --- patch66: the gate measures distance from the BASELINE ------------------------
NO_DEAL = [4.1, 5.5, 6.8, 9.3, 9.3, 10.1, 11.5]        # measured, n=7
DEAL = [20.0, 21.6, 29.1, 29.4, 29.8, 31.9, 31.9, 32.0, 34.3, 34.6, 34.9, 35.9,
        36.2, 37.2, 37.5, 39.9, 40.1, 40.6, 41.2, 46.8, 48.8, 49.1, 50.1]   # n=23
check(o.HAND_DEAL_THRESHOLD == 15.0, "HAND_DEAL_THRESHOLD is the measured 15.0, now a distance from the baseline")
check(max(NO_DEAL) < o.HAND_DEAL_THRESHOLD < min(DEAL),
      f"it sits BETWEEN the two measured populations ({max(NO_DEAL)} .. {min(DEAL)})")
check(o.POST_PLAY_DEAL_MAX_WAIT == 20.0, "the cap is 20.0")
check(o.POST_PLAY_DEAL_MAX_WAIT > 15.0,
      "...which clears the slowest real deal measured (15.0s)")
check(o.hand_deal_threshold({}) == 15.0, "the knob now defaults to the baseline threshold")
check(o.HAND_DEAL_THRESHOLD == 15.0, "there is ONE deal constant and it is 15.0")
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("_mean_abs_delta(baseline, cur)" in _src, "the poll compares against the BASELINE")
check("_mean_abs_delta(prev, cur)" not in _src, "...and no longer against the previous sample")
check(not any(l.strip() == "prev = cur" for l in _src.splitlines()),
      "the previous-sample carry is gone (matched as a whole line, not the substring that also hits `prev = current`)")

# It must SEE a gradual deal the rising edge misses: 40 steps of 0.8 each.
_rt = o.time
class _C:
    def __init__(s): s.t = 0.0
    def time(s): return s.t
    def sleep(s, d): s.t += d
try:
    _c = _C(); o.time = _c
    calls = {"n": 0}
    o._grab_settle_regions = lambda names: (calls.__setitem__("n", calls["n"] + 1), {n: None for n in names})[1]
    # distance from the baseline grows 0.8 per poll; no single STEP is ever above 0.8
    o._mean_abs_delta = lambda a, b: 0.8 * calls["n"]
    got = o.wait_for_hand_deal(max_wait=20.0, poll_interval=0.15)
    check(got is True, "a GRADUAL deal (0.8 per poll, never a big step) is now detected")
    check(_c.t < 20.0, f"...and detected before the cap ({_c.t:.1f}s)")
    _c2 = _C(); o.time = _c2; calls["n"] = 0
    o._mean_abs_delta = lambda a, b: 9.0        # a no-deal window: sits in the 4.1-11.5 band
    check(o.wait_for_hand_deal(max_wait=20.0, poll_interval=0.15) is False,
          "a no-deal window (statistic 9.0, inside the measured no-deal band) still times out")
finally:
    o.time = _rt
'''
assert T.count("if fails:") == 1
T2 = T.replace("\nif fails:", EXTRA + "\nif fails:", 1)
ast.parse(T2)

# The two checks that pinned the OLD rising-edge value move with the constant.
T65 = 'check(o.hand_deal_threshold({}) == 25.0, "the deal threshold defaults to 25.0 with the env unset")'
assert T.count(T65) == 1
T2 = T2.replace(T65, 'check(o.hand_deal_threshold({}) == 15.0, "the deal threshold defaults to the measured 15.0 with the env unset")', 1)
P63 = os.path.join(ROOT, "tests", "minigame", "test_post_play_timing.py")
t63 = open(P63).read()
O63 = 'check(_o.HAND_DEAL_THRESHOLD == 25.0, "HAND_DEAL_THRESHOLD is the measured 25.0")'
assert t63.count(O63) == 1, t63.count(O63)
N63 = ('check(_o.HAND_DEAL_THRESHOLD == 15.0,\n'
       '      "HAND_DEAL_THRESHOLD is 15.0 -- patch66 remeasured it live as a distance from the "\n'
       '      "baseline, where no-deal windows reach 11.5 and real deals start at 20.0")')
t63b = t63.replace(O63, N63, 1)
# patch63's own two-population check was about the RISING-EDGE populations, which no
# longer describe the gate. Retire it explicitly rather than let it pin a dead claim.
OLD_POPS = 'check(DEAD_WINDOW_MAX < _o.HAND_DEAL_THRESHOLD < DEAL_BURST_MIN,\n      "the deal threshold sits BETWEEN the dead window (max 15.44) and the deal burst (min 31.83)")'
assert t63b.count(OLD_POPS) == 1
NEW_POPS = ('# RETIRED by patch66. Those two populations were of the RISING-EDGE statistic\n'
            '# (sample vs previous sample), which the gate no longer uses; live it missed 11 of\n'
            '# 30 windows. The populations that pin the shipped gate are in test_reveal_peak.py.\n'
            'check(_o.SETTLE_THRESHOLDS["hand"] == 8.0,\n'
            '      "the SETTLE gate keeps its own 8.0 -- correct once the deal has landed")')
t63b = t63b.replace(OLD_POPS, NEW_POPS, 1)

# THREE MORE PINS THAT PATCH63 DERIVED OFFLINE AND PATCH66 SUPERSEDES WITH LIVE DATA.
# Each is updated with its reason, not deleted: the offline numbers were real, they were
# just of a different statistic (rising edge) and a smaller sample (n=9 replayed turns
# against n=30 live gate windows).
X1 = 'check(not _o.hand_deal_seen([20.0]), "a delta inside the gap but under 25 (20.0) is NOT a deal")'
assert t63b.count(X1) == 1
Y1 = ('# 20.0 IS a deal now: patch66 remeasured the gate as a distance from the baseline,\n'
      '# where the no-deal band tops out at 11.5 and real deals start at 20.0.\n'
      'check(_o.hand_deal_seen([20.0]), "20.0 clears the live threshold of 15.0")\n'
      'check(not _o.hand_deal_seen([11.5]), "11.5, the highest no-deal window measured, does not")')
t63b = t63b.replace(X1, Y1, 1)
X2 = 'check(_o.POST_PLAY_DEAL_MAX_WAIT >= 22.0, "the cap clears the worst measured deal (21.95 s)")'
assert t63b.count(X2) == 1
Y2 = ('# The 21.95 s worst case came from replaying 9 turns offline against the rising-edge\n'
      '# statistic. Live, over 30 gate windows, every real deal crossed the shipped\n'
      '# threshold by 15.0 s, so a 20 s cap carries a third of margin and saves 15 s on\n'
      '# each of the 7 turns in 30 that have no deal coming at all.\n'
      'check(_o.POST_PLAY_DEAL_MAX_WAIT >= 15.0 * 1.25,\n'
      '      "the cap clears the slowest deal measured LIVE (15.0 s) with 25% margin")')
t63b = t63b.replace(X2, Y2, 1)

ast.parse(t63b)
open(P63, "w").write(t63b)


# test_settle_regions.py pinned the cap against the same offline figure.
PSR = os.path.join(ROOT, "tests", "minigame", "test_settle_regions.py")
tsr = open(PSR).read()
XS = "if POST_PLAY_DEAL_MAX_WAIT < 22:"
assert tsr.count(XS) == 1, tsr.count(XS)
YS = ("# 20 s, live-measured: every deal in 30 gate windows crossed by 15.0 s (patch66).\n"
      "if POST_PLAY_DEAL_MAX_WAIT < 18:")
tsr2 = tsr.replace(XS, YS, 1)
XS2 = 'f"POST_PLAY_DEAL_MAX_WAIT={POST_PLAY_DEAL_MAX_WAIT} is below "'
assert tsr2.count(XS2) == 1
tsr2 = tsr2.replace('"the p50 deal time of ~16.9s plus margin — it would time out "',
                    '"the 15.0s slowest deal measured live plus margin — it would time out "', 1)
# The summary line still said "rising-edge", which the gate no longer is.
XS3 = 'print(f"OK: post-play deal gate — rising-edge on the hand at threshold {_th}, "'
assert tsr2.count(XS3) == 1
tsr2 = tsr2.replace(XS3, 'print(f"OK: post-play deal gate — distance from the baseline at threshold {_th}, "', 1)
ast.parse(tsr2)
open(PSR, "w").write(tsr2)

open(OP, "w").write(O2); open(TP, "w").write(T2)
print("patch66 applied to", ROOT)
