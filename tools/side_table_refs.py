"""(b) Can the NEIGHBOURING TABLE be a place the localiser confirms? Check, then write.

The recorded goal leg lands there two walks in three (OPEN-22); a place the
router can name from that pose, plus a short leg to the dealer, lets the
route finish from wherever the leg ends. This builds `bar_side_table` from the
frames that show it and applies the same three questions the admission gates
ask, over a TEMPORARY copy of places/ so nothing on disk changes until
--write, and only if every check passes:

  A  leave-one-out: each candidate names bar_side_table with MIN_RATIO margin
     (the first set of four frames at four different headings FAILED this: this
     localiser matches a pose only from its own approach angle, so each heading
     needs a twin -- hence five headings x two walks)
  B  non-disruption: no existing reference frame and none of the route's
     leg-end frames at the four nodes newly names bar_side_table
  C  discrimination: frames known to be at the DEALER's table do not name it

    .venv/bin/python -B tools/side_table_refs.py           # report only
    .venv/bin/python -B tools/side_table_refs.py --write   # copy refs into places/bar_side_table/
"""
import glob
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

NAME = "bar_side_table"
CANDIDATES = [   # the landing pose at the neighbouring table, five headings x two walks (OPEN-22 walks 1 and 2)
    "overnight/prompt_zone_frames/pz_w1_x+0.00_y+0.00_h0_1788804265269.jpg",
    "overnight/prompt_zone_frames/pz_w1_x+0.00_y+0.00_h1_1788804267176.jpg",
    "overnight/prompt_zone_frames/pz_w1_x+0.00_y+0.00_h2_1788804269350.jpg",
    "overnight/prompt_zone_frames/pz_w1_x+0.00_y+0.00_h3_1788804270881.jpg",
    "overnight/prompt_zone_frames/pz_w1_x+0.00_y+0.00_h4_1788804272689.jpg",
    "overnight/prompt_zone_frames/pz_w2_x+0.00_y+0.00_h0_1788804786897.jpg",
    "overnight/prompt_zone_frames/pz_w2_x+0.00_y+0.00_h1_1788804788610.jpg",
    "overnight/prompt_zone_frames/pz_w2_x+0.00_y+0.00_h2_1788804790255.jpg",
    "overnight/prompt_zone_frames/pz_w2_x+0.00_y+0.00_h3_1788804791800.jpg",
    "overnight/prompt_zone_frames/pz_w2_x+0.00_y+0.00_h4_1788804794465.jpg",
]
DEALER_TABLE = [  # known to be at the dealer's table: must NOT name the side table
    "test_fixtures/table_prompt_cases/prompt_low_ink_recorded_goalleg_t6.jpg",
    "test_fixtures/table_prompt_cases/prompt_on_bright_table_goalleg_t1.jpg",
    "test_fixtures/table_prompt_cases/prompt_over_dealer_dealer_circle_f0020.jpg",
]


def main():
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    from PIL import Image
    import places
    write = "--write" in sys.argv
    for f in CANDIDATES + DEALER_TABLE:
        assert os.path.isfile(f), f
    tmp = tempfile.mkdtemp(prefix="places_")
    shutil.copytree(places.PLACES_DIR, os.path.join(tmp, "places"))
    cand_dir = os.path.join(tmp, "places", NAME)
    os.makedirs(cand_dir)
    for i, f in enumerate(CANDIDATES):
        shutil.copy(f, os.path.join(cand_dir, f"ref{i:02d}.jpg"))
    orig_dir = places.PLACES_DIR
    report = {"name": NAME, "candidates": CANDIDATES, "A": [], "B": {"checked": 0, "named": []}, "C": []}
    ok = True
    try:
        places.PLACES_DIR = os.path.join(tmp, "places")
        # A: leave-one-out -- score each candidate against a set that excludes it
        for i, f in enumerate(CANDIDATES):
            held = os.path.join(cand_dir, f"ref{i:02d}.jpg"); aside = held + ".aside"
            os.rename(held, aside)
            try:
                room, score, margin = places.identify(Image.open(f).convert("RGB"))
            finally:
                os.rename(aside, held)
            good = room == NAME and margin >= places.MIN_RATIO
            report["A"].append({"frame": f, "room": room, "score": score, "margin": round(margin, 2), "ok": good})
            ok &= good
            print(f"  A  {os.path.basename(f)[:40]:42} -> {room!s:15} {score:6.1f}/{margin:.2f}  {'ok' if good else 'FAIL'}")
        # B: non-disruption over every existing reference and the route's leg-end frames
        others = sorted(glob.glob(os.path.join(orig_dir, "*", "*.jpg")))
        legs = sorted(f for f in glob.glob("overnight/*failframes*/at_*.jpg") if not os.path.basename(f).startswith("at_dealer_table"))
        for f in others + legs:
            room, score, margin = places.identify(Image.open(f).convert("RGB"))
            report["B"]["checked"] += 1
            if room == NAME:
                report["B"]["named"].append({"frame": f, "score": score, "margin": round(margin, 2)})
        named = report["B"]["named"]
        ok &= not named
        print(f"  B  {report['B']['checked']} existing reference + route leg-end frames: {len(named)} newly name {NAME}  {'ok' if not named else 'FAIL'}")
        for n in named[:6]:
            print(f"       {n['frame']} {n['score']}/{n['margin']}")
        # C: the dealer's table must stay distinct
        for f in DEALER_TABLE:
            room, score, margin = places.identify(Image.open(f).convert("RGB"))
            good = room != NAME
            report["C"].append({"frame": f, "room": room, "score": score, "margin": round(margin, 2), "ok": good})
            ok &= good
            print(f"  C  {os.path.basename(f)[:40]:42} -> {room!s:15} {score:6.1f}/{margin:.2f}  {'ok' if good else 'FAIL'}")
    finally:
        places.PLACES_DIR = orig_dir
    report["ok"] = ok
    os.makedirs("overnight/census", exist_ok=True)
    json.dump(report, open("overnight/census/side_table_refs.json", "w"), indent=1)
    print(f"\n  {'ALL CHECKS PASS' if ok else 'CHECKS FAILED'} -> overnight/census/side_table_refs.json")
    if write and ok:
        dst = os.path.join(orig_dir, NAME)
        if os.path.exists(dst):
            sys.exit(f"refusing: {dst} exists")
        shutil.copytree(cand_dir, dst)
        print(f"  wrote {len(CANDIDATES)} references to {dst}")
    elif write:
        print("  --write refused: checks failed")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
