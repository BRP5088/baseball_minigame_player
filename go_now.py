"""Navigate to the minigame table from WHEREVER the character currently is.

    python3 go_now.py

For fast iteration: the human positions the character (e.g. near Wanda) and this
tries to reach the table from there. No reset, no re-walking the three legs that
already work — those cost ~90s per attempt and are not what is failing.

Reports, briefly:
  - where it thought it was
  - which legs it walked and what confirmed them
  - whether the dealer prompt came up
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(shots=None):
    import compass
    import ensure_stream
    import graph_walk
    import places
    import table_prompt as tp
    import worldmap

    if not ensure_stream.ensure_live(log=print):
        print("no live picture — is chiaki up and the console awake?")
        return 2

    m = worldmap.WorldMap.load()
    img = compass.fast_capture()
    if tp.at_table(img):
        print("already at the table")
        return 0

    where, detail = graph_walk.locate(m, img=img, log=lambda *a: None)
    room, n, ratio = places.identify(img)
    print(f"start: locate={where!r} ({detail}); raw identify={room!r} "
          f"({n} matches, ratio {ratio})")

    t0 = time.time()
    res = graph_walk.go_to_table(m, log=print, shots=shots, allow_reset=False)
    took = time.time() - t0

    print(f"\n{'ARRIVED' if res['arrived'] else 'did not arrive'} "
          f"in {took:.0f}s  (reached {res.get('reached')!r}, "
          f"reason {res.get('reason')!r})")
    for leg in res.get("legs", []):
        blockers = leg.get("blockers") or []
        print(f"  {leg['a']:16} -> {leg['b']:16} verdict={leg['verdict']} "
              f"({leg['detail']})"
              + (f"  blocked x{len(blockers)}"
                 f" [{','.join(str(b['cleared_by']) for b in blockers)}]"
                 if blockers else ""))
    return 0 if res["arrived"] else 1


if __name__ == "__main__":
    sys.exit(main(shots=(sys.argv[1] if len(sys.argv) > 1 else None)))
