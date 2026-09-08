#!/bin/zsh
# At batch 19's boundary: archive; if patch44 is marked READY (touch $S/p44.READY), apply it, test,
# commit and launch the A/B (--arms off,on --flag STOP_LOOK_YAW, 20 trials = 10 an arm);
# otherwise relaunch the plain rescue build for another 25.
set -e
S="/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad"
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f chain_trials.py >/dev/null; then echo "HARNESS STILL RUNNING -- refusing"; exit 1; fi
cp overnight/chain_trials.log overnight/chain_trials_batch19.log
cp overnight/chain_trials.json overnight/chain_trials_batch19.json
if [ -f "$S/p44.READY" ]; then
  .venv/bin/python -B drafts/pending_after_ab/apply_patch44.py "$PWD"
  for f in tests/routing/test_chain_walk.py tests/routing/test_chain_locate.py tests/harness/test_no_undefined_names.py tests/harness/test_overnight_start_hint.py tests/harness/test_harness_restores_shipped_value.py; do
    echo "== $f"; BASEBALL_TEST_RUN=1 .venv/bin/python -B "$f" 2>&1 | tail -2
  done
  git add chain_walk.py tests/routing/test_chain_walk.py overnight/chain_trials.py drafts/pending_after_ab/apply_patch44.py
  git add -A tools 2>/dev/null || true
  git commit -q -m "patch44: STOP_LOOK_YAW (ships off) -- a looked stop turns by px/PX_PER_DEG instead of strafing, offset carried to the next stop; the harness gains --flag NAME for arms

The census behind it (agent_progress/closed-loop/review/after_look129_census.*):
after the 129 look's strafe left, the first head-on fit still reads dx -300 px
on 93 of 96 arrivals -- the sidestep changes nothing; the offset is a heading
error, the shape the end turn already handles in the tail. Three of the five
stairs losses tonight are the same mechanism at the 39 stop. A/B next.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
  git log --oneline -1
  ARGS="--arms off,on --flag STOP_LOOK_YAW --trials 20"
else
  echo "patch44 not READY: plain relaunch"
  ARGS="--trials 25"
fi
env -u BASEBALL_TEST_RUN .venv/bin/python -B -c "import ensure_stream; print('ensure_live ->', ensure_stream.ensure_live())" 2>&1 | tail -1
(env -u BASEBALL_TEST_RUN PYTHONUNBUFFERED=1 nohup .venv/bin/python -B overnight/chain_trials.py --chain route_user_1853 ${=ARGS} > overnight/chain_trials.log 2>&1 &)
sleep 15; pgrep -f chain_trials.py | head -1; date '+%H:%M:%S'; echo "launched with: $ARGS"
