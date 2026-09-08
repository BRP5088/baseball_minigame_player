"""Docs for the 12:25 restart: the §8 row for batch 26 and patch51; the HANDOFF restart block."""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
CM = os.path.join(ROOT, "CLAUDE.md"); HN = os.path.join(ROOT, "HANDOFF_NOW.md")
cm = open(CM).read(); hn = open(HN).read()
old_row = "    a780ed6  11:46         25     running                             the door step ON, plain 25: rescue + yaw + door step\n"
new_row = """    a780ed6  11:46   12 + 8   12/12 + 7/8   83.7 s / 86.1 s   12      the door step ON, plain 25 in two parts: part 1 stopped at 12
                                                                        by the user's VPN reconnecting (chiaki: "Takion failed to send
                                                                        data packet"; trials 13-14 INVALID on the dead stream, not
                                                                        counted), part 2 stopped at 8 by the user's restart. 19 of 20
                                                                        valid; the one loss t1 of part 2: a +10.6 deg STOP YAW at the
                                                                        LAST stop (196, the look fit TWO ahead at 198), then the final
                                                                        approach never found the prompt (patch51's case, below)
    2d0f4e0  12:25          -     not run yet                          patch51 STOP_YAW_SKIP_LAST_STOP = True: no stop yaw at the plan's
                                                                        LAST turn-only stop -- nothing clears it after that, so it rides
                                                                        the whole final approach under the end turn. Census of the 196
                                                                        stop over 266 walks: head-on or strafed 225 arrived / 1 ended
                                                                        without the prompt / 1 failed; looked and YAWED (6) 4 arrived /
                                                                        2 ended at 204 without the prompt. The strafe runs there instead
                                                                        (marker yaw_skipped.reason = "last stop"); 4 mutants caught.
                                                                        Landed at the restart boundary; THE NEXT PLAIN 25 MEASURES IT
"""
assert cm.count(old_row) == 1
old_hdr = "**Updated 2026-09-08 11:50. DEAD RECKONING IS PAUSED BY THE USER; the closed loop is running its 25.**\n"
new_hdr = """**Updated 2026-09-08 12:27 -- THE USER IS RESTARTING THE MAC. NOTHING IS RUNNING. Read this block first.**

## RESTART BLOCK (12:27) -- what was stopped, what is committed, what to do on return

**State at the stop.** Batch 26 part 2 (a780ed6, plain 25) was stopped by me at 8 trials for the
user's restart: 7 of 8 arrived (t1 the last-stop yaw loss); with part 1 (12/12 before the VPN drop) that
is 19 of 20 valid on the door-step build. Archived as `overnight/chain_trials_batch26_part{1,2}.*`.
The harness, all five log monitors, the frame-dump workflow and a frame reader were stopped; chiaki was
left running and the restart closes it. The PS5 will auto-sleep.

**Committed before the restart (2d0f4e0):** patch51 `STOP_YAW_SKIP_LAST_STOP = True` (no stop yaw at
the plan's LAST turn-only stop; the strafe runs instead, marker `yaw_skipped.reason = "last stop"`;
4 mutants caught on a cp scratch copy; 213 tests OK), the tools/ edits the a780ed6 door-step tests
import (they had been left unstaged), and every scratchpad script under
`drafts/pending_after_ab/scratch_saved/` (`land51.sh`, `land_next.sh`, `swap_chiaki_framedump.sh`,
`mut51.py`), because `/private/tmp` does not survive a reboot. **patch51 has NOT run live.**

**UNCOMMITTED, deliberately -- the frame-dump build (the user's "why not do it now"):**
`chiaki-patch/framedump.{h,cpp}`, `chiaki-patch/gui/src/qmlbackend.cpp` (untracked) and edits to
`chiaki-patch/README.md`, `chiaki-patch/gui/CMakeLists.txt`, `chiaki-patch/gui/src/main.cpp`,
`tests/cpp/test_injectinput_cpp.py`; the Python half waits in `drafts/pending_after_ab/apply_patch49.py`
(untracked). The workflow was in the BUILDER'S ROUND 2 (fixing two confirmed skeptic findings: the dump
was taken BEFORE `prepareFrameForPresentation` so macOS VideoToolbox did a second hw readback per
frame; `FrameDumpStop`/`FrameDumpEnabled` unreferenced) when it was stopped mid-edit. Its notes, scripts
and the mutant log are in `agent_progress/closed-loop/frame_dump/` (gitignored, on disk):
`progress.md` (Established / Assumed, both rounds), `edit_patch49_round2.py`, `edit_patch49_tests.py`
(12:24, possibly incomplete), `mutants_cpp_round2.log` (1 caught of 7, then ABORTED on sleep overrun
112.84 ms -- a live trial is worth more than a mutant). **Treat all of it as unverified**: the new
binary was never swapped in, `chiaki-ng-build/` is still the injector-only build. On return, a fresh
skeptic pass over `chiaki-patch/` + `tests/cpp/` + `apply_patch49.py` from the notes, THEN
`swap_chiaki_framedump.sh` at a batch boundary, never during one.

**On return, in order:**
1. `git status` -- expect exactly the frame-dump files above dirty and nothing else in the import
   path. `find . -type l -not -path './.venv/*' -not -path './paddle_venv/*'` -> none.
2. `./restart_chiaki.sh` (the alias `chiaki-analog`; standing permission to wake the PS5), then
   `.venv/bin/python -B tools/doctor.py`. The game window must be on the FRONT Space (capture is
   on-screen only; patch48 waits 120 s for a missing window and re-runs the trial number).
3. `PATH="$PWD/.venv/bin:$PATH" ./run_tests.sh` once (the last full suite predates patch51; the four
   files it touches were run green at the landing).
4. Launch the plain 25 on 2d0f4e0: `env -u BASEBALL_TEST_RUN PYTHONUNBUFFERED=1 nohup .venv/bin/python
   -B overnight/chain_trials.py --chain route_user_1853 --trials 25 > overnight/chain_trials.log 2>&1 &`
   -- this is patch51's first measurement. Watch for `STOP YAW skipped (last stop)` at k=196 and count
   arrivals from a 196 look-around stop against the 4-of-6 baseline.
5. Reader on every failed trial (the user's rule); the unfinished reader note for b26p2 t1 is
   `agent_progress/closed-loop/review/notes_b26p2_t1.md` (empty sections -- redo it).
6. Then the frame-dump skeptic pass (above), and after it lands, the user's endorsed design: LOOK
   WHILE PUSHING (sample the dump at ~20 Hz during a push; end the push early when the picture stops
   changing or the target scene arrives; stop-or-continue first, steering never), A/B'd with
   `--arms off,on --flag`.

**Rules in force, unchanged:** no edits to `chain_walk.py`, `chain.py`, `table_prompt.py`, `compass.py`,
`overnight/chain_trials.py`, `overnight/_harness.py` while a batch runs (10.17 / rule 21); land at
boundaries via a saved script; all anchor asserts before any write (rule 19); scratch trees are cp
copies under the scratchpad (10.16a); Opus builders, Sonnet skeptics/readers; `at_table()` changes are
measured on every route frame on disk; mutation testing on Snoopy or after the batch.

"""
assert hn.count(old_hdr) == 1
cm = cm.replace(old_row, new_row); hn = hn.replace(old_hdr, new_hdr)
open(CM, "w").write(cm); open(HN, "w").write(hn); print("docs edited")
