# Apply ONLY when no live run imports graph_walk (rule 10.21)

    .venv/bin/python drafts/pending_after_ab/patch_control_frames.py
    .venv/bin/python drafts/pending_after_ab/patch_control_frames_test.py
    BASEBALL_TEST_RUN=1 .venv/bin/python -B tests/routing/test_success_control_frames.py
    BASEBALL_TEST_RUN=1 .venv/bin/python -B tests/routing/test_goal_leg_frames.py

Why: da5b7ec made follow_verified's success frame the leg END and dropped
`before`, which tests/routing/test_success_control_frames.py pins as the
START-pose control (§8(i)). The 2026-09-07 suite caught it (142/143). The
patch writes BOTH frames on BOTH outcomes: success/start_<node> + success/ok_<node>
on arrival, start_<node> + fail_<node> on failure. Mutation-test after
applying (console free by then): drop the start_ write -> the START checks
fail; write `before` as ok_ -> the LEG-END check fails.

## Second item: at_table() OCR path (patch_at_table_ocr.py)

    .venv/bin/python drafts/pending_after_ab/patch_at_table_ocr.py
    BASEBALL_TEST_RUN=1 .venv/bin/python -B tests/routing/test_at_table_ocr_path.py
    BASEBALL_TEST_RUN=1 .venv/bin/python -B tests/routing/test_at_table_threshold.py

Numbers: overnight/census/prompt_ocr_ab.json (0 false positives on 693
clean-node frames and the quest-log anchor; recall alone 341/1289, so it is
an addition after the mask, never a replacement). Mutants to run: drop the
`return ocr_says_prompt(img)` line -> both bright-background cases fail;
OCR_MIN_WORDS 2 -> 1 -> re-score NEG_NODES before trusting anything.

## (c) Jukebox leg trim (patch_leg_trim.py) -- after (a) ends

    .venv/bin/python drafts/pending_after_ab/patch_leg_trim.py
    BASEBALL_TEST_RUN=1 .venv/bin/python -B tests/routing/test_leg_trim.py
    mutants: _trimmed returns steps unchanged; walk_link skips the trim; the
      keyed lookup uses (b, a) -- each must fail the test
    nohup .venv/bin/python -B overnight/ab_jukebox_trim.py > overnight/ab_jukebox_trim.log 2>&1 &

## After the fast extend run (2026-09-07 late)

1. Loop yield: `python -c "import json;r=json.load(open('overnight/ab_fast_extend.json'))['runs'][1:];print(sum(1 for x in r if (x.get('setup_seconds') or 999)<30),'of',len(r),'setups under 30s')"`
   -- under half: set RETURN_LOOP = False in overnight/ab_fast.py.
2. `patch_ab_fast_reset_after_arrival.py` (no return after an arrival).
3. `patch_stop_early.py` -- FIRST HALF ONLY (signature); the loop-body edit and
   follow()'s call need the anchors read at landing time (they are in the
   walk_link step loop and the GOAL_LEG_AS_RECORDED branch). Then the test in
   tests/routing/test_goal_leg_frames.py: stop_when True on the 3rd step ->
   3 steps walked, extension skipped; without stop_when -> all steps.
