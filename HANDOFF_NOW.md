# State at 2026-09-07 09:40 — read this first

## Running now
**Nothing — the goal-leg A/B is PAUSED at the user's request** (stream looked
sluggish while offline CPU sweeps ran beside it). 14 of 20 trials are banked in
`overnight/ab_goal_leg.json` (trial 15 was in flight and is lost). Resume with:

    nohup .venv/bin/python -B overnight/ab_goal_leg.py --resume >> overnight/ab_goal_leg.log 2>&1 &

`--resume` continues the same interleaved order from the banked count. While it
runs: NO CPU-bound offline work except the suite (§10.13a, corrected).

**Dashboard:** https://claude.ai/code/artifact/6f8d087b-dd3e-4b8b-b34b-ef5faaf07278
Rebuild + push state after every trial (or on any plan change):

    .venv/bin/python -B tools/dashboard.py [--paused]      -> overnight/dashboard_state.json
    Artifact write_db  collection=dash doc_id=state  file_path=overnight/dashboard_state.json

Comments on the page sent to Claude wake this session (auto-replies armed).
The page also has an INBOX: at every board update, `Artifact read_db
collection=dash doc_id=inbox` (messages: [{ts, when, text}]); answer by
appending {ts, when, to, text} to `overnight/dashboard_replies.json`, rebuild,
write_db. "Ask the board" on the page is the viewer's own Claude with only the
board's data -- not this session.

## Waiting for the run to end (do these first, in order)
1. Apply `drafts/pending_after_ab/` (README there): the control-frame fix the
   suite caught (142/143, test_success_control_frames.py). Mutation-test it.
2. `table_prompt` OCR path: apply `drafts/pending_after_ab/patch_at_table_ocr.py`
   (README there). The mask cannot see the prompt over the light table top or
   over the dealer's body; OCR reads both with 0 false positives on every
   negative on disk (overnight/census/prompt_ocr_ab.json). Local-contrast masks
   were measured and refused (prompt_mask_ab.json).
3. Score the A/B TWICE: (a) as the harness scored it (overnight/ab_goal_leg.json,
   at_table() after the sweep, Fisher p); (b) post hoc with
   `tools/goal_leg_sheet.py`, which re-reads every PRE-sweep frame with the mask
   AND OCR and reports "prompt on screen at the leg's end" per arm -- the
   leg-level criterion the shipped detector cannot see (5 legs in: shipped 1/3,
   recorded 1/2, harness 0/5). Write OPEN-21 with both and say which is which.

## Done this morning (all committed)
- `locate()` may never confirm the GOAL by appearance (dfb1b6e, 697c7ac): the
  OPEN-14 trial-6 hole, with trial 6's own frame as a fixture.
- Goal leg: `GOAL_LEG_AS_RECORDED` flag (ships False), the goal's leg-end frame
  is now PRE-sweep, the success frame is the leg end and not `before` (da5b7ec).
- Hand-walk entry points deleted at the user's request; `tools/doctor.py` and
  `tools/calibrate_window.py` keep the two subcommands that guard the rig and
  a money path (ab5c1fe).

## Rules in force
No flagship sub-agents for routine work (Haiku); no drafting; never mutate the
checkout while `console_lock` is held (10.17/10.21); no mutation sweeps on the
Mac while the console is live (Snoopy_testing.md); save patch scripts before
running them (10.19).

## Tonight's results, committed
- Leg-1 flags cost 8/10 arrivals; reverted (aa773dc, p = 0.000714).
- OPEN-5: attempts=9 9/9 vs attempts=3 5/10 to bar_jukebox (d0b6143, p = 0.0325).
- OPEN-14: 1 real arrival of 3 valid; 7/10 censored; the `locate()` hole (38a17af).
- Reset diagnostic measured the wrong transport; fixed at the root (d3bf513).
- Console interlock (`console_lock.py`); keep_awake stands down during runs.
- QA_AUDIT.md: four guards no test can reach, by mutant (2251c49); orphans (f0de600).
- A test globbed a live run's sink and broke overnight (7b8f918).
