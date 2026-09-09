"""patch63: the post-play read waits for the DEAL, at a threshold that sits between two
measured populations, with a hard floor -- the OCR timing the user said was off.

MEASURED 2026-09-08 (match 4 of the smoke test, chiaki's frame dump at 20 Hz, native
1920x1080; agent_progress/ocr-timing/TIMING_REPORT.md, data in
overnight/census/match_timeline_20260908/):
  * the replacement card lands 11.48 / 19.01 / 23.01 s (p50/p90/max, n=9) after the play;
    the shipped gate released at 0.38 / 0.90 / 2.16 s (n=85) -- a median 10.4 s EARLY on
    9 of 9 turns. That early read cost 27 retry calls of 175 (15.4% of the API budget) and
    is the frame the local hand reader also read (8 of its 9 misses).
  * hand_deal_seen's threshold was SETTLE_THRESHOLDS["hand"] = 8.0, which sits BELOW the
    dead-window population it must ignore (max d_hand between the play burst and the deal
    burst: 7.25..15.44 per turn, n=9); the deal burst peaks at 31.83..41.15 (n=9). 8.0 is
    inside the noise (CLAUDE.md 10.4); 25.0 sits in the gap 15.44..31.83 and fires 9/9 at
    p50 9.95 s, max 21.95 s. Values 16..30 behave the same.
  * a floor of 6.0 s sits between the fastest release the old gate produced (2.16 s) and the
    earliest the hand was ever readable (8.43 s, by eye on frames).
  * CAVEAT the report carries: the deltas were measured at a 0.060 s sample gap; the live poll
    is 0.15 s, so both populations rise in production. Re-check 25.0 against the first live
    session's [deal] lines. It is not final.

WHAT CHANGES: HAND_DEAL_THRESHOLD = 25.0 (its own constant; SETTLE_THRESHOLDS["hand"] stays
8.0 for the settle gate, which is right ONCE the deal has landed); POST_PLAY_MIN_WAIT = 6.0
(wait_for_hand_deal returns no earlier than that, even on an edge); POST_PLAY_DEAL_MAX_WAIT
25 -> 35 (the worst deal was 21.95 s at n=9; 25 left 3 s of margin); the deal wait is ON by
default and read at CALL time (10.18) through post_play_wait_for_deal(), BASEBALL_DEAL_WAIT=0
turns it off. Nothing else in the loop changes: the reveal wait, the settle gate, the 0.4 s
buffer, the retry ladder, navigation and the money path are untouched.

PRE-REGISTERED LIVE ACCEPTANCE (the next cycle): "mid-deal or partial read" retries per match
fall from ~7 to <= 1; "[local-check] hand: local found 0" lines fall to 0 on full hands;
"[deal]" lines show the deal seen on >= 8 of 10 plays with the release time printed; no play
exceeds POST_PLAY_DEAL_MAX_WAIT without a "[deal] no replacement card" line.

Applies to: orchestrator.py, tests/minigame/test_settle_regions.py; creates
tests/minigame/test_post_play_timing.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch63.py [ROOT]
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
O = os.path.join(ROOT, "orchestrator.py")
T = os.path.join(ROOT, "tests", "minigame", "test_settle_regions.py")
N = os.path.join(ROOT, "tests", "minigame", "test_post_play_timing.py")
o = open(O).read(); t = open(T).read()
assert not os.path.exists(N), N

A1 = "POST_PLAY_DEAL_MAX_WAIT = 25.0\n"
A2 = '''# DEFAULT OFF. The DIAGNOSIS behind this is solid (88/88 plays read ~15 s
# early, 46.8% false-still during the animation), but replaying this particular
# gate over the logged frames only closes about half the gap — median earliness
# 11.3 s -> 5.5 s, plays released >1 s early 79/87 -> 66/87 — and 2 of 87 plays
# hit the timeout. That is not enough to change the shipped default on. Turn it
# on for one live session with BASEBALL_DEAL_WAIT=1 and read the failed-read
# count and settle_stats_summary() afterwards; tune from those, not from the
# 0.57 s frame log, which cannot resolve the 0.15 s poll rate.
POST_PLAY_WAIT_FOR_DEAL = bool(os.environ.get("BASEBALL_DEAL_WAIT"))
'''
A3 = '    th = SETTLE_THRESHOLDS["hand"] if threshold is None else threshold\n'
A4 = '''    start = time.time()
    prev = _grab_settle_regions(("hand",))["hand"]
    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        cur = _grab_settle_regions(("hand",))["hand"]
        if _mean_abs_delta(prev, cur) >= SETTLE_THRESHOLDS["hand"]:
            return True
        prev = cur
'''
A5 = "                if POST_PLAY_WAIT_FOR_DEAL:\n                    wait_for_hand_deal()\n"
for a in (A1, A2, A3, A4, A5):
    assert o.count(a) == 1, (o.count(a), a[:60])
assert o.count("HAND_DEAL_THRESHOLD") == 0 and o.count("POST_PLAY_MIN_WAIT") == 0
assert o.count("def post_play_wait_for_deal") == 0
assert o.count("def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,") == 1

B1 = '_th = _o.SETTLE_THRESHOLDS["hand"]\n'
B2 = '''# Default OFF: the replay closes only about half the gap (11.3s -> 5.5s early)
# and 2 of 87 plays hit the timeout, so this stays opt-in until one live
# session validates it. BASEBALL_DEAL_WAIT=1 turns it on.
if POST_PLAY_WAIT_FOR_DEAL and not os.environ.get("BASEBALL_DEAL_WAIT"):
    failures.append("the deal gate is on without BASEBALL_DEAL_WAIT being set")
if POST_PLAY_DEAL_MAX_WAIT < 20:
'''
B3 = "# It must be a threshold, not a constant: mutating SETTLE_THRESHOLDS[\"hand\"]\n# must move the boundary.\n"
for b in (B1, B2, B3):
    assert t.count(b) == 1, (t.count(b), b[:60])

R1 = '''# 35, was 25: the worst deal measured 2026-09-08 landed 21.95 s after the play (n=9);
# 25 left 3 s of margin. The cap costs time only on a turn that already failed.
POST_PLAY_DEAL_MAX_WAIT = 35.0
# THE DEAL EDGE, between two measured populations (2026-09-08, 20 Hz on the frame
# dump, n=9 turns; agent_progress/ocr-timing/TIMING_REPORT.md):
#   dead window (max d_hand between the play burst and the deal burst)  7.25 .. 15.44
#   the deal burst (its peak d_hand)                                    31.83 .. 41.15
# SETTLE_THRESHOLDS["hand"] = 8.0 sits BELOW the dead window -- inside the noise this
# gate must ignore (10.4) -- which is why the deal wait alone closed only half the
# gap. 25.0 sits in the gap; 16..30 all release at p50 ~10 s. CAVEAT: measured at a
# 0.060 s sample gap; the live poll is 0.15 s, so both populations rise in
# production. Re-check against the first live session's [deal] lines.
HAND_DEAL_THRESHOLD = 25.0
# No post-play read before this, edge or no edge: between the fastest release the
# old gate produced (2.16 s, n=85 live) and the earliest a hand was readable by eye
# (8.43 s, n=9).
POST_PLAY_MIN_WAIT = 6.0
'''
R2 = '''# ON BY DEFAULT since 2026-09-08. The diagnosis (88/88 plays read ~15 s early) was
# never in doubt; the replay that closed only half the gap did so because the
# threshold sat inside the noise -- see HAND_DEAL_THRESHOLD. Measured directly on
# the frame dump the deal lands 11.5 / 19.0 / 23.0 s (p50/p90/max, n=9) after the
# play and the old gate released at 0.38 s. Read at CALL time (10.18);
# BASEBALL_DEAL_WAIT=0 turns it off for one session.
def post_play_wait_for_deal(env=None):
    raw = (os.environ if env is None else env).get("BASEBALL_DEAL_WAIT")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "off", "no", "")


POST_PLAY_WAIT_FOR_DEAL = post_play_wait_for_deal()
'''
R3 = '    th = HAND_DEAL_THRESHOLD if threshold is None else threshold\n'
R4 = '''    start = time.time()
    prev = _grab_settle_regions(("hand",))["hand"]
    seen = False
    while time.time() - start < max_wait:
        time.sleep(poll_interval)
        cur = _grab_settle_regions(("hand",))["hand"]
        if _mean_abs_delta(prev, cur) >= HAND_DEAL_THRESHOLD:
            seen = True
        prev = cur
        # The floor: an edge before POST_PLAY_MIN_WAIT is dead-window noise by the
        # measurement above, so keep polling; return on the first poll at or past
        # the floor once an edge has been seen.
        if seen and time.time() - start >= POST_PLAY_MIN_WAIT:
            print(f"  [deal] replacement card seen; released {time.time() - start:.1f}s after the play")
            return True
'''
R5 = "                if post_play_wait_for_deal():\n                    wait_for_hand_deal()\n"
o2 = o.replace(A1, R1, 1).replace(A2, R2, 1).replace(A3, R3, 1).replace(A4, R4, 1).replace(A5, R5, 1)

S1 = "_th = _o.HAND_DEAL_THRESHOLD\n"
S2 = '''# ON by default since 2026-09-08 (patch63); BASEBALL_DEAL_WAIT=0 is the only off switch.
if not POST_PLAY_WAIT_FOR_DEAL and (os.environ.get("BASEBALL_DEAL_WAIT") or "1").strip().lower() not in ("0", "false", "off", "no"):
    failures.append("the deal gate is OFF by default -- patch63 turned it on")
if POST_PLAY_DEAL_MAX_WAIT < 22:
'''
S3 = "# It must be a threshold, not a constant: mutating HAND_DEAL_THRESHOLD\n# must move the boundary.\n"
t2 = t.replace(B1, S1, 1).replace(B2, S2, 1).replace(B3, S3, 1)

NEW_TEST = r'''"""patch63: the post-play deal wait -- threshold between two measured populations,
a hard floor, ON by default and read at call time. Pins LITERALS (10.11).
"""
import os, sys, time as _t
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
import orchestrator as _o

fails = []
def check(cond, msg):
    (print("PASS", msg) if cond else (fails.append(msg), print("FAIL", msg)))

# The two populations, measured 2026-09-08 (n=9 each). Literals, not the constant.
DEAD_WINDOW_MAX = 15.44
DEAL_BURST_MIN = 31.83
check(_o.HAND_DEAL_THRESHOLD == 25.0, "HAND_DEAL_THRESHOLD is the measured 25.0")
check(DEAD_WINDOW_MAX < _o.HAND_DEAL_THRESHOLD < DEAL_BURST_MIN,
      "the deal threshold sits BETWEEN the dead window (max 15.44) and the deal burst (min 31.83)")
check(_o.SETTLE_THRESHOLDS["hand"] == 8.0, "SETTLE_THRESHOLDS['hand'] stays 8.0 for the settle gate")
check(not _o.hand_deal_seen([10.0]), "a dead-window delta (10.0) is NOT a deal by default")
check(not _o.hand_deal_seen([20.0]), "a delta inside the gap but under 25 (20.0) is NOT a deal")
check(_o.hand_deal_seen([32.0]), "a deal-burst delta (32.0) IS a deal")
check(_o.POST_PLAY_MIN_WAIT == 6.0, "POST_PLAY_MIN_WAIT is 6.0")
check(2.16 < _o.POST_PLAY_MIN_WAIT < 8.43, "the floor sits between the fastest old release (2.16) and the earliest readable hand (8.43)")
check(_o.POST_PLAY_DEAL_MAX_WAIT >= 22.0, "the cap clears the worst measured deal (21.95 s)")

# ON by default, off only by the env, read at call time.
check(_o.post_play_wait_for_deal({}) is True, "deal wait is ON with the env unset")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "0"}) is False, "BASEBALL_DEAL_WAIT=0 turns it off")
check(_o.post_play_wait_for_deal({"BASEBALL_DEAL_WAIT": "1"}) is True, "BASEBALL_DEAL_WAIT=1 keeps it on")
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("if post_play_wait_for_deal():\n                    wait_for_hand_deal()" in src,
      "the turn loop asks post_play_wait_for_deal() at CALL time")
check("if POST_PLAY_WAIT_FOR_DEAL:\n" not in src, "the loop no longer reads the import-time constant")

# wait_for_hand_deal: the floor holds even when the edge comes early; the edge is
# still required; the stubs are really reached.
def run(deltas, max_wait=35.0):
    calls = {"grab": 0, "delta": 0}
    it = iter(deltas)
    real = (_o._grab_settle_regions, _o._mean_abs_delta, _o.time)
    clock = [1000.0]
    _o._grab_settle_regions = lambda names: (calls.__setitem__("grab", calls["grab"] + 1), {n: None for n in names})[1]
    def delta(a, b):
        calls["delta"] += 1
        return next(it, 0.0)
    _o._mean_abs_delta = delta
    _o.time = type("C", (), {"sleep": staticmethod(lambda s: clock.__setitem__(0, clock[0] + s)),
                             "time": staticmethod(lambda: clock[0]),
                             "strftime": staticmethod(_t.strftime)})()
    try:
        res = _o.wait_for_hand_deal(max_wait=max_wait, poll_interval=0.15)
        return res, clock[0] - 1000.0, calls
    finally:
        _o._grab_settle_regions, _o._mean_abs_delta, _o.time = real

res, elapsed, calls = run([0.0, 32.0] + [0.0] * 400)   # the edge at 0.30 s
check(res is True, "an early deal edge is still recognised")
check(elapsed >= 6.0, f"...but not released before the 6.0 s floor (released at {elapsed:.2f}s)")
check(elapsed < 7.0, f"...and released promptly once past the floor ({elapsed:.2f}s)")
check(calls["delta"] >= 2 and calls["grab"] >= 3, "the stubs were really polled")

res, elapsed, calls = run([0.0, 32.0] + [0.0] * 400)
res2, elapsed2, _ = run([14.0] * 400)                  # dead-window level only, never a deal
check(res2 is False, "dead-window deltas (14.0) never release the gate")
check(elapsed2 >= 35.0 - 0.2, f"...it falls through at the cap ({elapsed2:.1f}s)")

res3, elapsed3, _ = run([0.0] * 60 + [40.0] + [0.0] * 400)   # the edge at ~9.2 s
check(res3 is True and 9.0 <= elapsed3 <= 9.6, f"an edge past the floor releases at the edge ({elapsed3:.2f}s)")

if fails:
    print(f"\n{len(fails)} FAILED"); sys.exit(1)
print("\nall green")
'''
for chunk in (R1, R2, R3, R4, R5):
    assert o2.count(chunk) == 1
ast.parse(o2); ast.parse(t2); ast.parse(NEW_TEST)
assert o2.count("SETTLE_THRESHOLDS[\"hand\"] if threshold") == 0
assert o2.count("if POST_PLAY_WAIT_FOR_DEAL:") == 0
open(O, "w").write(o2); open(T, "w").write(t2); open(N, "w").write(NEW_TEST)
print("patch63 applied to", ROOT)
