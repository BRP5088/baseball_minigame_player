#!/bin/zsh
# Land patch43 + patch43b at a batch boundary: archive, apply, test, commit, relaunch.
set -e
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f chain_trials.py >/dev/null; then echo "HARNESS STILL RUNNING -- refusing"; exit 1; fi
cp overnight/chain_trials.log overnight/chain_trials_batch18.log
cp overnight/chain_trials.json overnight/chain_trials_batch18.json
.venv/bin/python -B drafts/pending_after_ab/apply_patch43.py "$PWD"
.venv/bin/python -B drafts/pending_after_ab/apply_patch43b.py "$PWD"
for f in tests/routing/test_chain_walk.py tests/routing/test_chain_locate.py tests/harness/test_no_undefined_names.py; do
  echo "== $f"; BASEBALL_TEST_RUN=1 .venv/bin/python -B "$f" 2>&1 | tail -2
done
git add chain_walk.py tests/routing/test_chain_walk.py tools/collision_census.py tools/turn_review.py drafts/pending_after_ab/apply_patch43.py drafts/pending_after_ab/apply_patch43b.py
git commit -q -m "patch43+43b: a LOST rescue -- back out 1.0 s, look 0/-25/+25 over the whole chain behind the last credible k at the strong gate, once per walk

Fires only where the walk was already lost; every firing is a measurement.
Built by an Opus builder, two Sonnet skeptics (a time-cap overrun, a stale
end_yaw, turn-early not re-armed, two readers blind to the new rows -- all
fixed), a recheck READY; 165 tests, eleven mutants caught plus the
whole-chain window's (43b, from the b16 t19 reader: a wrong wide fit makes
last_cred_k the wrong place).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git log --oneline -1
env -u BASEBALL_TEST_RUN .venv/bin/python -B -c "import ensure_stream; print('ensure_live ->', ensure_stream.ensure_live())" 2>&1 | tail -1
(env -u BASEBALL_TEST_RUN PYTHONUNBUFFERED=1 nohup .venv/bin/python -B overnight/chain_trials.py --chain route_user_1853 --trials 25 > overnight/chain_trials.log 2>&1 &)
sleep 15; pgrep -f chain_trials.py | head -1; date '+%H:%M:%S'
