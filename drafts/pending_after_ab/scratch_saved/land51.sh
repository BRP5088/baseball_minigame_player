#!/bin/zsh
# At batch 26 part 2's boundary: archive as batch$1; apply patch51; test; commit
# (chain_walk, the test file, the patch script, and the tools/ edits the a780ed6
# tests already depend on -- NOT chiaki-patch/ or tests/cpp/, which belong to the
# unverified frame-dump build); launch a plain 25 (or the A/B named by $2).
set -e
S="/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad"
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f chain_trials.py >/dev/null; then echo "HARNESS STILL RUNNING -- refusing"; exit 1; fi
cp overnight/chain_trials.log "overnight/chain_trials_batch$1.log"; cp overnight/chain_trials.json "overnight/chain_trials_batch$1.json"
git status --porcelain chain_walk.py tests/routing/test_chain_walk.py | grep -q . && { echo "chain_walk/test already dirty -- refusing"; exit 1; }
.venv/bin/python -B drafts/pending_after_ab/apply_patch51.py "$PWD"
for f in tests/routing/test_chain_walk.py tests/routing/test_chain_locate.py tests/harness/test_no_undefined_names.py tests/harness/test_no_import_time_test_run_flag.py; do
  echo "== $f"; BASEBALL_TEST_RUN=1 .venv/bin/python -B "$f" 2>&1 | tail -2
done
git add chain_walk.py tests/routing/test_chain_walk.py drafts/pending_after_ab/apply_patch51.py tools/live_gate_census.py tools/trial_sheet.py "overnight/chain_trials_batch$1.log" "overnight/chain_trials_batch$1.json"
git commit -q -m "Land patch51: no stop yaw at the plan's LAST turn-only stop (STOP_YAW_SKIP_LAST_STOP, ships on)

The yaw is cleared at the next turn-only stop; the last stop has none, so a
yaw there rides the whole final approach under the end turn. Census of the
196 stop over 266 walks: head-on or strafed 225 arrived / 1 ended without the
prompt / 1 failed; yawed (6) 4 arrived / 2 ended at 204 without the prompt.
The strafe runs instead, marker yaw_skipped.reason = 'last stop'. Four
mutants caught, each by a different test. Also commits the tools/ edits the
a780ed6 door-step tests already import (they were left unstaged).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git log --oneline -1
if [ -n "$2" ]; then ARGS="--arms off,on --flag $2 --trials 20"; else ARGS="--trials 25"; fi
env -u BASEBALL_TEST_RUN .venv/bin/python -B -c "import ensure_stream; print('ensure_live ->', ensure_stream.ensure_live())" 2>&1 | tail -1
(env -u BASEBALL_TEST_RUN PYTHONUNBUFFERED=1 nohup .venv/bin/python -B overnight/chain_trials.py --chain route_user_1853 ${=ARGS} > overnight/chain_trials.log 2>&1 &)
sleep 15; pgrep -f chain_trials.py | head -1; date '+%H:%M:%S'; echo "launched with: $ARGS"
