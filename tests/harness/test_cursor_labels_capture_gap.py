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

Four cases, one call to `labels_for` each, with `_selected` and `glob.glob`
stubbed so no image is ever opened:

    1. a clean selection: the fan is quiet for >=2 frames, then one slot rises
       and holds -- KEPT
    2. a rise one frame after a move: some OTHER slot changed in the frame
       right before the labelled one -- REJECTED, capture_gap
    3. a flicker re-rise: the SAME slot was risen within the last
       FLICKER_WINDOW frames, dropped, and rises again -- REJECTED, flicker
    4. the original HOLD filter still fires on its own: a clean, unflickered
       rise that drops immediately -- REJECTED, transient

Mutants to run by hand (CLAUDE.md 10.9 -- break it, watch it fail, restore):
drop the capture_gap check (force `gap_ok = True`) and case 2 should start
passing (test fails); drop the flicker check (force `flickered = False`) and
case 3 should start passing (test fails). Restore by sha256 after either.
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


print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
