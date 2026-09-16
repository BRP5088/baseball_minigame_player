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
    import glob as _glob
    from PIL import Image as _Image
    crops = sorted(_glob.glob(os.path.join(_ROOT, "agent_progress/deal-frames",
                                           "*", "loss_*", "f*.png")))
    drove = False
    for c in crops[::97]:
        fresh_process()
        try:
            os.remove(o.HAND_MEMORY_FILE)
        except OSError:
            pass
        cards, _why = o.local_hand_cards(_Image.open(c).convert("RGB"),
                                         phase="batting")
        if cards and any(x.get("kind") == "player" for x in cards):
            drove = True
            break
    want("a real hand was driven through local_hand_cards", drove,
         "no archived crop produced a player card -- check cannot bite")
    if drove:
        want("reading a hand through local_hand_cards writes the file",
             os.path.exists(o.HAND_MEMORY_FILE),
             "the memory was populated in-process but never reached disk")

finally:
    try:
        os.remove(o.HAND_MEMORY_FILE)
    except OSError:
        pass
    o.HAND_MEMORY_FILE = REAL

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
