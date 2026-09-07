#!/bin/zsh
# Stop the fast (a) run at the next trial boundary (user: pause dead-reckoning work, 2026-09-07).
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
LOG=overnight/ab_fast_extend.log; PARENT=74810; t0=$(date +%s)
while :; do
  n=$(grep -cE '^\[ *[0-9]+\]' $LOG); el=$(( $(date +%s) - t0 ))
  if [ "$n" -ge 6 ] || [ $el -ge 480 ]; then break; fi
  sleep 5
done
echo "boundary at $(date +%H:%M:%S): $n trial lines, ${el}s waited"
kill -INT $PARENT 2>/dev/null; sleep 4
pgrep -f 'ab_fast.py --one-trial' | xargs -r kill 2>/dev/null; sleep 1
pgrep -fl 'ab_fast.py' || echo "ab_fast: no processes"
env -u BASEBALL_TEST_RUN .venv/bin/python -B -c "import analog_replay as ar; ar.clear(); import console_lock as c; print('lock holder:', c.holder())" 2>&1 | tail -2
tail -3 $LOG | cut -c1-120
