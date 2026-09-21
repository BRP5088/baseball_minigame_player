"""The hand memory survives a PROCESS boundary, and only when the hand corroborates it.

WHY. `_hand_memory` was a module-level dict with no persistence, so a crawl that
runs one process per action wiped it between every turn -- the feature worked and
never once had the chance to fire. Demonstrated: reading a hand populates the dict,
and a fresh interpreter starts at {}.

THE DANGER IS THE OPPOSITE ONE. A remembered card is consulted ONLY for a slot the
reader cannot see, so a WRONG remembered card is never audited by the thing it is
standing in for. A file from a different hand must therefore be refused, and it is
refused by the code's own audit rule -- every slot readable NOW must agree with what
the file claims -- rather than by a staleness timer, which would be an invented
constant (match_log.jsonl carries no timestamps to derive one from).

Plain asserts: this suite has four incompatible check() signatures and a reversed
call to a name-first one can never fail.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import orchestrator as o

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


# Keep the real file out of the way; this test writes its own.
REAL = o.HAND_MEMORY_FILE
o.HAND_MEMORY_FILE = os.path.join(
    os.path.dirname(REAL), f"hand_memory_test_{os.getpid()}.json")


_real_save = o._save_hand_memory


def _save_ignoring_test_flag(phase=None):
    """Checks 1-12 are ABOUT the file, so they must be able to write one even
    though this process is a test. Check 13 restores the real function and
    asserts the guard.

    IT IS NOT ENOUGH TO CLEAR THE ENV VAR. _running_under_test() also returns
    True when sys.argv[0] is a test_*.py file, which this is -- so the first
    version of this wrapper lifted nothing and check 6 died on a missing file.
    Stub the predicate itself.
    """
    real_pred = o._running_under_test
    o._running_under_test = lambda: False
    try:
        return _real_save(phase)
    finally:
        o._running_under_test = real_pred


o._save_hand_memory = _save_ignoring_test_flag


def fresh_process():
    """Simulate a new crawl process: empty dict, load not yet attempted."""
    o._hand_memory.clear()
    o._hand_memory_loaded = False


def rows(*pairs):
    """read_hand-shaped rows; None power means the reader could not see it."""
    return [{"kind": "player", "digit": p, "secondary": s, "x": 100 + 180 * i, "y": 160}
            for i, (p, s) in enumerate(pairs)]


try:
    # 1. IT WRITES THROUGH.
    fresh_process()
    o._hand_memory[1] = {"power": "8", "secondary": 1, "art": None}
    o._save_hand_memory("batting")
    want("a mutation reaches disk", os.path.exists(o.HAND_MEMORY_FILE))

    # 2. A NEW PROCESS ADOPTS IT when a readable card corroborates it.
    fresh_process()
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._save_hand_memory("batting")
    fresh_process()
    n = o._load_hand_memory(rows(("1", None), (None, None), ("5", 2)), "batting")
    want("a corroborated file is adopted", n >= 1 and 2 in o._hand_memory,
         f"adopted {n}, memory {o._hand_memory}")

    # 3. A DISAGREEING FILE IS REFUSED ENTIRELY. This is the case that plays a
    #    wrong card, so it must fail closed -- not adopt the slots that happen
    #    to agree.
    fresh_process()
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._hand_memory[3] = {"power": "9", "secondary": 0, "art": None}
    o._save_hand_memory("batting")
    fresh_process()
    n = o._load_hand_memory(rows((None, None), (None, None), ("4", 3)), "batting")
    want("a file that disagrees with a readable card is refused",
         n == 0 and not o._hand_memory, f"adopted {n}, memory {o._hand_memory}")

    # 4. NOTHING READABLE -> NOT USED. Accepting here means trusting an arbitrary
    #    file on exactly the frame where the error would be invisible.
    fresh_process()
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._save_hand_memory("batting")
    fresh_process()
    n = o._load_hand_memory(rows((None, None), (None, None), (None, None)), "batting")
    want("an uncorroborated file is not used", n == 0 and not o._hand_memory,
         f"adopted {n}")

    # 5. THE HALF BOUNDARY. A new half deals a fresh five, so a pitching file must
    #    never be handed to a batting hand however well it happens to line up.
    fresh_process()
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._save_hand_memory("pitching")
    fresh_process()
    n = o._load_hand_memory(rows((None, None), (None, None), ("5", 2)), "batting")
    want("a file from the other half is refused", n == 0, f"adopted {n}")

    # 6. forget_hand_slot WRITES THROUGH. A crash between the spend and the next
    #    save would otherwise leave the played card on disk.
    fresh_process()
    o._hand_memory[1] = {"power": "8", "secondary": 1, "art": None}
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._save_hand_memory("batting")
    o.forget_hand_slot(1)
    on_disk = json.load(open(o.HAND_MEMORY_FILE))["slots"]
    want("a spent slot is removed from disk immediately", "1" not in on_disk,
         str(on_disk))

    # 7. reset DELETES the file. A new match in the SAME phase would otherwise be
    #    handed the previous match's hand.
    o.reset_hand_memory()
    want("reset removes the file", not os.path.exists(o.HAND_MEMORY_FILE))

    # 8. A POPULATED memory never reads disk -- this is what keeps a live run
    #    in-process, with no file access after match start.
    fresh_process()
    o._hand_memory[0] = {"power": "7", "secondary": 1, "art": None}
    o._save_hand_memory("batting")
    o._hand_memory[4] = {"power": "6", "secondary": 0, "art": None}   # in-process only
    before = dict(o._hand_memory)
    o._hand_memory_loaded = False
    n = o._load_hand_memory(rows(("7", 1), (None, None), (None, None)), "batting")
    want("a non-empty memory is not overwritten from disk",
         n == 0 and o._hand_memory == before, f"adopted {n}")
    # 9. THE WIRING ITSELF, END TO END THROUGH local_hand_cards.
    #    Checks 1-8 all called _save_hand_memory DIRECTLY, and a mutant that
    #    removed the save from the write site SURVIVED all of them -- the exact
    #    shape of the bug this whole change exists to fix: a feature that works
    #    and is not connected to the path that uses it (CLAUDE.md 10.9).
    from PIL import Image as _Image
    # NAMED fixtures under test_fixtures/, not a glob over agent_progress/ (gitignored,
    # and a live crawl writes there -- CLAUDE.md sec 2's "a test must never glob a
    # directory a live run writes to"). Two known-good crops, copied from
    # agent_progress/deal-frames/20260908_235423_patch65_66_67/loss_0008448_slot4/
    # (f0008425.png, f0008427.png), each independently verified to drive a player card
    # through local_hand_cards.
    crops = [os.path.join(_ROOT, "test_fixtures", "deal_frames", n)
             for n in ("hand_memory_drive_01.png", "hand_memory_drive_02.png")]
    for c in crops:
        if not os.path.exists(c):
            raise FileNotFoundError(
                f"missing hand-memory fixture: {c} -- copy it from agent_progress/"
                f"deal-frames/ again (see this test's own comment for the source path)")
    drove = False
    for c in crops:
        fresh_process()
        try:
            os.remove(o.HAND_MEMORY_FILE)
        except OSError:
            pass
        # NO phase ARGUMENT, DELIBERATELY. Passing one skips the derivation branch
        # entirely, and a mutant that stopped deriving the phase SURVIVED while this
        # said phase="batting" -- the test was exercising the argument, not the code.
        # Every real caller passes nothing, so neither does this.
        cards, _why = o.local_hand_cards(_Image.open(c).convert("RGB"))
        if cards and any(x.get("kind") == "player" for x in cards):
            drove = True
            break
    want("a real hand was driven through local_hand_cards", drove,
         "no archived crop produced a player card -- check cannot bite")
    stamp_from_real_hand = "<never written>"
    if drove:
        want("reading a hand through local_hand_cards writes the file",
             os.path.exists(o.HAND_MEMORY_FILE),
             "the memory was populated in-process but never reached disk")
        # READ IT NOW. Check 12 used to read this file at the END, by which point
        # check 10 had overwritten it with an explicitly-passed phase -- so it
        # passed whatever local_hand_cards had actually written, and a mutant that
        # stopped deriving the phase SURVIVED. The value has to be captured at the
        # moment the code under test produces it.
        if os.path.exists(o.HAND_MEMORY_FILE):
            stamp_from_real_hand = json.load(open(o.HAND_MEMORY_FILE)).get("phase")

    # 10. A LIVE RUN NEVER ADOPTS A CRAWL'S FILE. run() sets this at startup,
    #     because reset_hand_memory() only fires when a match STARTS -- a resumed
    #     match (match_in_progress, exactly the state a crawl leaves behind)
    #     would otherwise reach local_hand_cards with an empty dict and load it.
    fresh_process()
    o._hand_memory[2] = {"power": "5", "secondary": 2, "art": None}
    o._save_hand_memory("batting")
    fresh_process()
    o.MEMORY_IN_PROCESS_ONLY = True
    try:
        n = o._load_hand_memory(rows((None, None), (None, None), ("5", 2)), "batting")
    finally:
        o.MEMORY_IN_PROCESS_ONLY = False
    want("a live run refuses the file even when it corroborates",
         n == 0 and not o._hand_memory, f"adopted {n}")

    # 11. run() ACTUALLY SETS IT. Asserting the flag exists is not asserting it is
    #     wired -- the same gap that let a mutant survive at check 9. Read run()'s
    #     source and require the assignment before its first statement.
    import inspect
    src = inspect.getsource(o.run)
    body = src[src.index('"""', src.index('"""') + 3) + 3:]
    first = body.index("begin_cycle_state()")
    want("run() takes ownership of the memory before it does anything",
         "MEMORY_IN_PROCESS_ONLY = True" in body[:first]
         and "reset_hand_memory()" in body[:first],
         "run() does not claim the memory at startup")

    # 12. THE HALF STAMP IS ACTUALLY WRITTEN. It was not: no caller passes `phase`,
    #     so every file said {"phase": null} and the half check could never refuse.
    #     Verified on a real hand rather than on a hand-passed argument.
    if drove:
        want("the file carries a half stamp derived from the hand itself",
             stamp_from_real_hand in ("batting", "pitching"),
             f"phase written by local_hand_cards was {stamp_from_real_hand!r} — "
             f"the half guard cannot fire")

    # 13. AN OFFLINE READ MUST NOT WRITE THE RIG'S FILE. Reproduced for real:
    #     tools/base_timing.py scanned a 2026-09-09 recording and hand_memory.json
    #     came back holding that recording's cards, ready for the next crawl to
    #     load. Same shape as the compass/view caches the offline suite was
    #     writing until it was stopped.
    #
    #     NOTE this whole file runs under BASEBALL_TEST_RUN, so the checks above
    #     had to write via _save_hand_memory with the guard temporarily lifted.
    #     That is why this check exists at the bottom rather than being implied.
    o._save_hand_memory = _real_save          # the guard, unpatched
    fresh_process()
    try:
        os.remove(o.HAND_MEMORY_FILE)
    except OSError:
        pass
    o._hand_memory[1] = {"power": "8", "secondary": 1, "art": None}
    o._save_hand_memory("batting")
    want("a test/offline process does not write the memory file",
         not os.path.exists(o.HAND_MEMORY_FILE),
         "an offline read wrote the rig's hand_memory.json")

finally:
    try:
        os.remove(o.HAND_MEMORY_FILE)
    except OSError:
        pass
    o.HAND_MEMORY_FILE = REAL

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
