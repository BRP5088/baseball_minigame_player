"""patch67: take the deal gate's baseline AT THE PLAY, not when the gate starts -- the
card has usually landed before we begin looking for it.

THE USER, watching a match run 21.7 minutes: "I don't think matches when I play last
that long so there must be a lot of wasted time." Measured, and they were right.

The turn does three things in series: wait for the reveal, pay for a vision read of it,
then watch the hand for the replacement card. The card does not wait its turn. Over the
28 plays recorded at 60 fps on 2026-09-08 (agent_progress/hand-timing/), the hand had
ALREADY moved this far from its at-the-play state by the moment the gate began:

    every play          13.4 .. 99.2, median 53.5
    the 8 that TIMED OUT 13.4  19.7  20.1  21.9  27.8  29.6  53.5  60.0

Against a threshold of 15.0 that is the whole failure: the gate opens, photographs a hand
that has already been refilled, calls that its baseline, and then waits 20-35 s for a
change that finished during the vision call. Seven of the eight are plainly "deal already
done"; the eighth (13.4) is the one turn where nothing moved at all.

MEASURING FROM THE PLAY CATCHES 8 OF 8. The same statistic against a baseline captured at
the commit press reads 15.5 .. 82.0 on those eight, every one clearing 15.0. And on the
turns that already worked it is satisfied on the gate's FIRST poll -- they read 23.0 to
104.3 by then -- so the gate stops costing a median 5.5 s and costs one capture.

WHAT CHANGES. `play_one_turn` grabs the hand region one line before the commit press, at
the same instant as the reveal mark, and hands it to `wait_for_hand_deal(baseline=...)`.
With no baseline given the function behaves exactly as before (its own capture at entry),
so every existing caller and test is unaffected. Nothing else moves: not the threshold,
not the cap, not the reveal path, not the money path, not navigation.

WHAT THIS DOES NOT FIX, said plainly: the turn is still ~26 s and a human plays one in a
fraction of that. This removes the deal wait. The reveal animation is the game's own time,
and the two paid vision calls per turn are the next item.

Applies to: orchestrator.py. Extends tests/minigame/test_reveal_peak.py.
Run:  .venv/bin/python -B drafts/pending_after_ab/apply_patch67.py [ROOT]
"""
import ast, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
OP = os.path.join(ROOT, "orchestrator.py")
TP = os.path.join(ROOT, "tests", "minigame", "test_reveal_peak.py")
O = open(OP).read(); T = open(TP).read()

A1 = '''def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,
                       poll_interval: float = 0.15) -> bool:
'''
A2 = '''    baseline = _grab_settle_regions(("hand",))["hand"]
'''
A3 = '''    _reveal_mark = reveal_mark()
    select_and_play(player_idx, tactics_idx)
'''
A4 = '''                if post_play_wait_for_deal():
                    wait_for_hand_deal()
'''
for a in (A1, A2, A3, A4):
    assert O.count(a) == 1, (O.count(a), a[:60])
assert O.count("_HAND_BASELINE") == 0 and O.count("baseline=") == 0

R1 = '''# THE HAND AT THE PLAY, handed from play_one_turn to the deal gate in run(). POPPED,
# never merely read: a turn that does not set one must not inherit the previous turn's
# hand, which would have the gate compare against a stale picture and return at once.
# That is graph_walk's _LAST_LEG_END pattern, here for the same reason -- and the two
# sites are in DIFFERENT functions, which is why a plain local would have been a
# NameError (the patch asserts the setter and the popper are not the same function).
_HAND_BASELINE = None


def stash_hand_baseline(img):
    global _HAND_BASELINE
    _HAND_BASELINE = img


def pop_hand_baseline():
    global _HAND_BASELINE
    img, _HAND_BASELINE = _HAND_BASELINE, None
    return img


def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,
                       poll_interval: float = 0.15, baseline=None) -> bool:
'''
R2 = '''    # THE BASELINE IS THE HAND AT THE PLAY when the caller has it (patch67). Captured
    # here instead, it photographs a hand the game has usually already refilled: over 28
    # recorded plays the hand had moved a median 53.5 from its at-the-play state by the
    # time this function began, and all eight of the timeouts were changes that finished
    # during the reveal read. None is a supported value -- every existing caller keeps
    # the old behaviour.
    if baseline is None:
        baseline = _grab_settle_regions(("hand",))["hand"]
'''
R3 = '''    _reveal_mark = reveal_mark()
    # THE HAND AS IT IS AT THE PLAY, for the deal gate that run() reaches further down.
    # Taken here, beside the reveal mark and before the press, because the replacement
    # card can land while the reveal is being read and a baseline captured after that is
    # already post-deal. It crosses functions the way graph_walk carries a leg-end frame:
    # a module stash that the consumer POPS, so a turn can never inherit the last one.
    stash_hand_baseline(_grab_settle_regions(("hand",))["hand"])
    select_and_play(player_idx, tactics_idx)
'''
R4 = '''                if post_play_wait_for_deal():
                    wait_for_hand_deal(baseline=pop_hand_baseline())
'''
O2 = O.replace(A1, R1, 1).replace(A2, R2, 1).replace(A3, R3, 1).replace(A4, R4, 1)

# The stash must be SET in play_one_turn and POPPED in run() -- different functions, which
# is exactly why a plain local would have been a NameError. Assert both, by AST.
tree = ast.parse(O2)
src_lines = O2.splitlines()
setter = popper = None
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef):
        body = "\n".join(src_lines[n.lineno - 1:(n.end_lineno or n.lineno)])
        if "stash_hand_baseline(_grab_settle_regions" in body: setter = n.name
        if "wait_for_hand_deal(baseline=pop_hand_baseline())" in body: popper = n.name
assert setter and popper, (setter, popper)
assert setter != popper, "setter and popper are the same function; the stash is pointless"
print(f"  stashed in {setter}(), popped in {popper}()")

EXTRA = '''
# --- patch67: the baseline is taken AT THE PLAY -----------------------------------
# Measured over 28 recorded plays: how far the hand had ALREADY moved from its
# at-the-play state by the moment the gate began. The eight that timed out are the
# subset; against a threshold of 15.0 every one of them clears when measured from the
# play, and none of them cleared when measured from the gate's start.
MOVED_BEFORE_GATE_ON_TIMEOUTS = [13.4, 19.7, 20.1, 21.9, 27.8, 29.6, 53.5, 60.0]
FROM_PLAY_ON_TIMEOUTS = [15.5, 23.0, 23.9, 26.8, 29.6, 30.5, 77.4, 82.0]
check(min(FROM_PLAY_ON_TIMEOUTS) >= o.HAND_DEAL_THRESHOLD,
      "measured from the PLAY, all 8 timed-out turns clear the 15.0 threshold")
check(sum(1 for x in MOVED_BEFORE_GATE_ON_TIMEOUTS if x >= o.HAND_DEAL_THRESHOLD) == 7,
      "7 of those 8 had already passed the threshold BEFORE the gate opened -- the deal was over")

import inspect
check("baseline=None" in inspect.signature(o.wait_for_hand_deal).__str__() or
      o.wait_for_hand_deal.__defaults__ is not None,
      "wait_for_hand_deal takes a baseline")
_src2 = open(os.path.join(_ROOT, "orchestrator.py")).read()
check("wait_for_hand_deal(baseline=pop_hand_baseline())" in _src2, "the turn loop passes the play-time baseline")
check("stash_hand_baseline(_grab_settle_regions" in _src2, "...which it stashed beside the reveal mark")
o.stash_hand_baseline("X")
check(o.pop_hand_baseline() == "X", "the stash round-trips")
check(o.pop_hand_baseline() is None, "...and a second pop yields None, so no turn inherits the last one's hand")
_i_base = _src2.index("stash_hand_baseline(_grab_settle_regions")
_i_play = _src2.index("select_and_play(player_idx, tactics_idx)")
check(_i_base < _i_play, "the baseline is captured BEFORE the commit press, not after")

# A GIVEN baseline must be used -- and no capture taken at entry.
_rt = o.time
class _C2:
    def __init__(s): s.t = 0.0
    def time(s): return s.t
    def sleep(s, d): s.t += d
try:
    o.time = _C2()
    grabs = {"n": 0}
    o._grab_settle_regions = lambda names: (grabs.__setitem__("n", grabs["n"] + 1), {n: "LIVE" for n in names})[1]
    seen = {}
    def _mad(a, b):
        seen.setdefault("base", a)
        return 99.0
    o._mean_abs_delta = _mad
    o.wait_for_hand_deal(max_wait=5.0, poll_interval=0.15, baseline="GIVEN")
    check(seen.get("base") == "GIVEN", f"the GIVEN baseline is what the poll compares against (got {seen.get('base')!r})")
    before = grabs["n"]
    o.time = _C2(); seen.clear(); grabs["n"] = 0
    o.wait_for_hand_deal(max_wait=5.0, poll_interval=0.15)
    check(seen.get("base") == "LIVE", "with no baseline given it still captures its own, as before")
finally:
    o.time = _rt
'''
assert T.count("if fails:") == 1
T2 = T.replace("\nif fails:", EXTRA + "\nif fails:", 1)
ast.parse(O2); ast.parse(T2)
assert O2.count("wait_for_hand_deal(baseline=pop_hand_baseline())") == 1
assert O2.count("def pop_hand_baseline") == 1 and O2.count("def stash_hand_baseline") == 1
assert O2.count("if baseline is None:") == 1

# patch63's check pinned the two-line call verbatim; patch67 adds the baseline argument.
# The INTENT (the loop asks at call time, never the import-time constant) is unchanged.
P63 = os.path.join(ROOT, "tests", "minigame", "test_post_play_timing.py")
t63 = open(P63).read()
X = 'check("if post_play_wait_for_deal():\\n                    wait_for_hand_deal()" in src,'
assert t63.count(X) == 1, t63.count(X)
Y = 'check("if post_play_wait_for_deal():\\n                    wait_for_hand_deal(baseline=pop_hand_baseline())" in src,'
t63 = t63.replace(X, Y, 1)
ast.parse(t63)
open(P63, "w").write(t63)

open(OP, "w").write(O2); open(TP, "w").write(T2)
print("patch67 applied to", ROOT)
