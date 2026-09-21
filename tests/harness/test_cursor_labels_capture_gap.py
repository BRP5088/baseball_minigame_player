"""`tools/cursor_labels_from_lifts.py` labelled a frame as "the cursor is on
this slot" whenever the NEXT frame showed that slot newly risen. I-42's census
(agent_progress/census/cursor_vlm/, main checkout) found that assumption false
28 times out of 81: a cursor caught MID-TRAVEL between slots produces the same
"one slot newly rose" transition as a cursor that was genuinely parked and then
pressed select, and the tool could not tell them apart. Two independent,
glow-free checks fix it -- CAPTURE GAP and NO-FLICKER -- and this file proves
each one is load-bearing with a synthetic frame sequence per shape, driven with
`check(name, cond)` (name first, condition second -- CLAUDE.md's nine-signature
trap, so this file's own copy is checked below rather than trusted).

Cases 1-4, one call to `labels_for` each, with `_selected` and `glob.glob`
stubbed so no image is ever opened:

    1. a clean selection: the fan is quiet for >=2 frames, then one slot rises
       and holds -- KEPT
    2. a rise one frame after a move: some OTHER slot changed in the frame
       right before the labelled one -- REJECTED, capture_gap
    3. a flicker re-rise: the SAME slot was risen within the last
       FLICKER_WINDOW frames, dropped, and rises again -- REJECTED, flicker
    4. the original HOLD filter still fires on its own: a clean, unflickered
       rise that drops immediately -- REJECTED, transient

**Cases 5-8, added after a skeptic review (`agent_progress/issues/I-42/skeptic.md`)
found two of ITS OWN mutants escaped cases 1-4** -- a real coverage gap, not a
code defect: cases 1-4 pin that the two checks exist and matter, but not the
EXACT frame pair each one compares, and not the EXACT `FLICKER_WINDOW`
boundary. Both closed here, without touching the shipped mechanism:

    5. capture-gap wrong-pair swap (hist[-3]==hist[-2] in place of
       hist[-2]==hist[-1]): a case where the correct pair disagrees (REJECT)
       but the ADJACENT wrong pair agrees (would wrongly pass) -- REJECTED,
       capture_gap
    6. capture-gap wrong-pair swap (hist[-3]==hist[-1] in place of
       hist[-2]==hist[-1]): same idea, the OTHER plausible off-by-one --
       REJECTED, capture_gap
    7. flicker-window boundary, inside: the rising slot was last risen
       EXACTLY `FLICKER_WINDOW` frames before the labelled frame -- inside
       the window -- REJECTED, flicker
    8. flicker-window boundary, outside: the rising slot was last risen
       EXACTLY `FLICKER_WINDOW + 1` frames before the labelled frame -- one
       frame outside the window -- KEPT

Mutants to run by hand (CLAUDE.md 10.9 -- break it, watch it fail, restore),
all four from the skeptic review, `__pycache__` deleted and sha256 verified
between and after each:

    force `gap_ok = True`                          (drop capture_gap)   -> case 2 fails
    force `flickered = False`                       (drop flicker)      -> case 3 fails
    `hist[-2]==hist[-1]` -> `hist[-3]==hist[-2]`     (wrong-pair swap A) -> case 5 fails
    `hist[-(fw+1):-1]` -> `hist[-fw:-1]`            (flicker off-by-one) -> case 7 fails

(a fifth, `hist[-2]==hist[-1]` -> `hist[-2]==sel` (compares against the RISE
frame's own sel, not the labelled frame) and a sixth, discarding every reason
to `None`, were already caught by cases 1-4 in the skeptic's own run.)
"""
import glob as glob_module
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import cursor_labels_from_lifts as clf   # noqa: E402

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


def _name(i):
    return "f%02d.jpg" % i


def run_case(seq):
    """seq: list of frozenset-or-None, one per synthetic frame. Stubs glob and
    _selected so labels_for runs over exactly this sequence, in order, with no
    file ever touched. Returns (kept_names, rejected) where rejected maps
    frame name -> reason."""
    names = [_name(i) for i in range(len(seq))]
    by_name = dict(zip(names, seq))

    real_glob = glob_module.glob
    real_selected = clf._selected

    def fake_glob(pattern, **kw):
        return list(names)   # already sorted by construction (zero-padded)

    def fake_selected(path):
        base = os.path.basename(path)
        return by_name[base]

    glob_module.glob = fake_glob
    clf._selected = fake_selected
    try:
        kept, rejected = clf.labels_for("fake_run_dir")
    finally:
        glob_module.glob = real_glob
        clf._selected = real_selected

    kept_names = {os.path.basename(f) for f, _slot in kept}
    rej_map = {os.path.basename(f): reason for f, _slot, reason in rejected}
    return kept_names, rej_map


E = frozenset()


# --- case 1: clean selection, kept --------------------------------------------
# quiet for 4 frames, slot 2 rises at index 4, holds through index 7 (HOLD=3)
seq1 = [E, E, E, E, frozenset({2}), frozenset({2}), frozenset({2}), frozenset({2})]
kept1, rej1 = run_case(seq1)
check("case 1 (clean selection): labelled frame f03 is KEPT",
      "f03.jpg" in kept1)
check("case 1: nothing else was wrongly rejected as capture_gap or flicker",
      not any(r in ("capture_gap", "flicker", "capture_gap+flicker")
              for f, r in rej1.items() if f == "f03.jpg"))


# --- case 2: rise one frame after a move, rejected as capture_gap -------------
# slot 1 rises then drops right before the labelled frame (f03), so f02 != f03
# -- the fan was NOT quiet for 2 frames before slot 2's rise at f04.
seq2 = [E, E, frozenset({1}), E, frozenset({2}), frozenset({2}), frozenset({2}), frozenset({2})]
kept2, rej2 = run_case(seq2)
check("case 2 (rise after a move): f03 is REJECTED, not kept",
      "f03.jpg" not in kept2)
check("case 2: rejected specifically for capture_gap",
      rej2.get("f03.jpg") == "capture_gap")


# --- case 3: flicker re-rise, rejected as flicker -----------------------------
# slot 3 rises at f01, drops at f02, stays down through f05 (quiet for the 2
# frames right before the re-rise), then rises AGAIN at f06 -- a flicker, not
# a new selection. Capture-gap passes (f04 == f05); only flicker should catch
# it.
seq3 = [E, frozenset({3}), E, E, E, E,
        frozenset({3}), frozenset({3}), frozenset({3}), frozenset({3})]
kept3, rej3 = run_case(seq3)
check("case 3 (flicker re-rise): f05 is REJECTED, not kept",
      "f05.jpg" not in kept3)
check("case 3: rejected specifically for flicker (capture_gap passed)",
      rej3.get("f05.jpg") == "flicker")


# --- case 4: the original HOLD filter still fires on its own -----------------
# quiet, clean rise of slot 4 at f03, but it drops again at f04 (k=1) -- never
# held for HOLD frames, so it must still be caught as "transient" even though
# neither new check has anything to say about it.
seq4 = [E, E, E, frozenset({4}), E, E, E]
kept4, rej4 = run_case(seq4)
check("case 4 (HOLD persistence): f02 is REJECTED, not kept",
      "f02.jpg" not in kept4)
check("case 4: rejected specifically as transient (not capture_gap/flicker)",
      rej4.get("f02.jpg") == "transient")


# --- case 5: capture-gap wrong-pair swap A (hist[-3]==hist[-2]) --------------
# hist[-3]==hist[-2]=={5} (both risen, same slot) while hist[-2]!=hist[-1]
# ({5} != E) -- the CORRECT pair (hist[-2] vs hist[-1]) disagrees and must
# REJECT, but the skeptic's mutant A (`hist[-3]==hist[-2]` in place of
# `hist[-2]==hist[-1]`) would find hist[-3]==hist[-2] TRUE and wrongly pass.
# slot6 (a different slot, unrelated to the target) is what rises at f01 to
# keep the frame sequence simple; the target slot2 never appears before its
# own rise, so flicker cannot fire and this isolates capture_gap.
seq5 = [E, frozenset({6}), frozenset({6}), E,
        frozenset({2}), frozenset({2}), frozenset({2}), frozenset({2})]
kept5, rej5 = run_case(seq5)
check("case 5 (wrong-pair swap A, hist[-3]==hist[-2]): f03 is REJECTED",
      "f03.jpg" not in kept5)
check("case 5: rejected specifically for capture_gap",
      rej5.get("f03.jpg") == "capture_gap")


# --- case 6: capture-gap wrong-pair swap B (hist[-3]==hist[-1]) --------------
# hist[-3]==hist[-1]==E while hist[-2]=={1} != hist[-1] -- the CORRECT pair
# disagrees and must REJECT, but a hypothetical mutant comparing hist[-3] to
# hist[-1] (instead of hist[-2] to hist[-1]) would find them EQUAL and wrongly
# pass. Target slot3 never appears before its own rise, so flicker cannot fire.
seq6 = [E, E, frozenset({1}), E,
        frozenset({3}), frozenset({3}), frozenset({3}), frozenset({3})]
kept6, rej6 = run_case(seq6)
check("case 6 (wrong-pair swap B, hist[-3]==hist[-1]): f03 is REJECTED",
      "f03.jpg" not in kept6)
check("case 6: rejected specifically for capture_gap",
      rej6.get("f03.jpg") == "capture_gap")


# --- cases 7/8: the FLICKER_WINDOW boundary, both sides ----------------------
# case 7: target slot9 was last risen EXACTLY FLICKER_WINDOW frames before the
#   labelled frame -- inside `window = hist[-(fw+1):-1]` -- must REJECT.
# case 8: target slot9 was last risen EXACTLY FLICKER_WINDOW+1 frames before
#   the labelled frame -- one frame outside that window -- must be KEPT.
# Both hold the fan quiet everywhere else so capture_gap always passes,
# isolating the flicker check and its exact off-by-one boundary.
fw = clf.FLICKER_WINDOW
TARGET = frozenset({9})

# case 7: labelled frame at index fw (so hist[-(fw+1)] == frame 0 == the rise)
seq7 = [TARGET] + [E] * fw + [TARGET, TARGET, TARGET, TARGET]
kept7, rej7 = run_case(seq7)
labelled7 = _name(fw)
check("case 7 (flicker boundary, K=FLICKER_WINDOW back): %s is REJECTED"
      % labelled7, labelled7 not in kept7)
check("case 7: rejected specifically for flicker",
      rej7.get(labelled7) == "flicker")

# case 8: one frame further back -- outside the window -- must be KEPT
seq8 = [TARGET] + [E] * (fw + 1) + [TARGET, TARGET, TARGET, TARGET]
kept8, rej8 = run_case(seq8)
labelled8 = _name(fw + 1)
check("case 8 (flicker boundary, K=FLICKER_WINDOW+1 back): %s is KEPT"
      % labelled8, labelled8 in kept8)
check("case 8: not rejected for capture_gap or flicker",
      labelled8 not in rej8)


print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
