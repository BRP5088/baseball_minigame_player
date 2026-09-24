"""read_result() on END-OF-MATCH screens filed in the reveal folders, and on every MID-MATCH frame.

THE REPORT THIS SETTLES (2026-09-24). I-65c r7's full-frame census scored read_result over the
reveal folders as if every frame were a negative, and flagged six frames at 0.806-0.984 as
"false positives on mid-match reveal banners". They are not. Every one was opened and shows
the END-OF-MATCH screen: the medallion, the arched WINNER/LOSER word, a CLOSE prompt, ALL FIVE
round dots lit, and a final scoreboard that agrees with the word (1-2 and 0-3 losses; 4-1 and
2-0 wins). The game shows NO per-play banner: reveal6/ is a late-match sequence of 25 frames
with no banner after any play, and WINNER appears only in its last two, after the final play.
test_reveal_watch.py already called the two loser_* frames the "end-of-round LOSER screen", and
test_result_ocr_whole_word.py calls negative_win_screen_no_banner "a real WIN-match frame" --
its "negative" is about its OCR band, not about being a result screen.

WHAT THIS FILE PINS
-------------------
1. Those six (plus screens/result__0) ARE result screens, with the outcome the scoreboard says.
   A future "fix" that suppresses them breaks the only signal that a match has ended.
2. read_result says is_result False on every MID-MATCH frame in the tracked reveal corpora --
   the reveal/reveal6/live sets of reveal_kind_truth, reveal_episode, reveal_occlusion -- and
   on every other screen in screens/. 0 of 344 on 2026-09-24 in the main checkout.

NOT GLOBBED: reveal_kind_truth/auto/ is orchestrator.REVEAL_KIND_DIR -- a live run writes there
(RIG.md: a test must never glob such a directory). Its 200 frames read False on 2026-09-24.

SPEED. The template search is ~100 ms a frame at 1920 on one core, ~17 s serially here, so the
frames are scored in a SPAWN process pool. Each worker calls read_result itself, end to end, so
OCR stays on that process's main thread (READERS.md). Each frame is loaded once, in its worker.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"      # inherited by the spawned workers

import glob

FIX = os.path.join(_ROOT, "test_fixtures")

# End-of-match screens, with the outcome read off each frame's final scoreboard by eye.
POSITIVES = {
    "reveal_episode/loser_t0225.30.jpg": "loss",                    # 1-2
    "reveal_episode/loser_t0231.38.jpg": "loss",                    # 1-2, six seconds later
    "reveal_kind_truth/reveal6/f_010369.jpg": "win",                # 4-1, arch fading in
    "reveal_kind_truth/reveal6/f_010868.jpg": "win",                # 4-1, settled
    "reveal_occlusion/reveal10_edge075.jpg": "loss",                # 0-3
    "result_screens/negative_win_screen_no_banner_20260921.jpg": "win",  # 2-0, fading in
    "screens/result__0.jpg": "loss",                                # 2-3
}

# Mid-match (and other non-result) frames. The floors are the TRACKED counts, so a
# glob that silently finds nothing -- a moved folder, a bad pattern -- fails here.
NEGATIVE_GLOBS = [
    ("reveal_kind_truth/reveal/*.jpg", 23),
    ("reveal_kind_truth/reveal6/*.jpg", 23),        # 25 minus the two end screens
    ("reveal_kind_truth/live/**/*.jpg", 55),
    ("reveal_episode/*.jpg", 4),
    ("reveal_occlusion/reveal*.jpg", 10),           # not _contact_sheet.jpg: not a frame
    ("screens/*.jpg", 19),
]


def _score(rel):
    from PIL import Image
    import local_state
    r = local_state.read_result(Image.open(os.path.join(FIX, rel)).convert("RGB"))
    return rel, r["is_result"], r["outcome"], r["why"]


def main():
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp

    fails = []

    def check(ok, msg):
        print(("PASS " if ok else "FAIL ") + msg)
        if not ok:
            fails.append(msg)

    for rel in POSITIVES:
        if not os.path.exists(os.path.join(FIX, rel)):
            raise SystemExit(f"FIXTURE MISSING: {rel} -- this test may not pass by finding nothing")

    negatives = []
    for pat, floor in NEGATIVE_GLOBS:
        got = sorted(os.path.relpath(p, FIX)
                     for p in glob.glob(os.path.join(FIX, pat), recursive=True))
        got = [p for p in got if p not in POSITIVES]
        check(len(got) >= floor, f"{pat}: {len(got)} mid-match frames found (floor {floor})")
        negatives += got

    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1),
                             mp_context=mp.get_context("spawn")) as ex:
        results = {rel: rest for rel, *rest in ex.map(_score, list(POSITIVES) + negatives,
                                                      chunksize=4)}

    for rel, want in POSITIVES.items():
        is_result, outcome, why = results[rel]
        check(is_result is True and outcome == want,
              f"END SCREEN {rel} reads as a {want} result (got is_result={is_result}, "
              f"outcome={outcome}; {why})")

    hits = [(rel, results[rel]) for rel in negatives if results[rel][0] is not False]
    for rel, (is_result, outcome, why) in hits:
        check(False, f"MID-MATCH {rel}: is_result={is_result}, outcome={outcome} ({why})")
    check(not hits, f"read_result is False on all {len(negatives)} mid-match frames "
                    f"({len(hits)} are not)")

    if fails:
        print(f"\n{len(fails)} FAILED")
        raise SystemExit(1)
    print("\nall green")


if __name__ == "__main__":     # spawned workers re-import this file; they must not run it
    main()
