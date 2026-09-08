#!/bin/zsh
# At a batch boundary: archive as batch$1; apply patch46 and/or patch47 if marked READY
# (touch $S/p46.READY / $S/p47.READY); test; commit; launch the A/B named by $2 (a chain_walk flag)
# or a plain 25 if $2 is empty.
set -e
S="/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad"
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f chain_trials.py >/dev/null; then echo "HARNESS STILL RUNNING -- refusing"; exit 1; fi
cp overnight/chain_trials.log "overnight/chain_trials_batch$1.log"; cp overnight/chain_trials.json "overnight/chain_trials_batch$1.json"
applied=""
for n in 46 47; do
  if [ -f "$S/p$n.READY" ] && [ -f "drafts/pending_after_ab/apply_patch$n.py" ]; then
    .venv/bin/python -B "drafts/pending_after_ab/apply_patch$n.py" "$PWD" && applied="$applied $n"
  fi
done
if [ -n "$applied" ]; then
  for f in tests/routing/test_chain_walk.py tests/routing/test_chain_locate.py tests/harness/test_no_undefined_names.py; do
    echo "== $f"; BASEBALL_TEST_RUN=1 .venv/bin/python -B "$f" 2>&1 | tail -2
  done
  git add chain_walk.py tests/routing/test_chain_walk.py overnight/chain_trials.py drafts/pending_after_ab/ 2>/dev/null; git add -A tools 2>/dev/null || true
  git commit -q -m "Land patch$applied (each behind a flag that ships off): the yaw only on a look-fit at the stop (46); one more push toward the office door before the stairs turn, the user's observation (47)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
  git log --oneline -1
fi
if [ -n "$2" ]; then ARGS="--arms off,on --flag $2 --trials 20"; else ARGS="--trials 25"; fi
env -u BASEBALL_TEST_RUN .venv/bin/python -B -c "import ensure_stream; print('ensure_live ->', ensure_stream.ensure_live())" 2>&1 | tail -1
(env -u BASEBALL_TEST_RUN PYTHONUNBUFFERED=1 nohup .venv/bin/python -B overnight/chain_trials.py --chain route_user_1853 ${=ARGS} > overnight/chain_trials.log 2>&1 &)
sleep 15; pgrep -f chain_trials.py | head -1; date '+%H:%M:%S'; echo "launched with: $ARGS (applied:$applied)"
