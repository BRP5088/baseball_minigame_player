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
