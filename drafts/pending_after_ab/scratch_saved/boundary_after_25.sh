#!/bin/zsh
# THE BOUNDARY after the plain 25 on patch51 (2d31263). Archives, tallies, and
# runs the perception profile. It does NOT relaunch: the next launch depends on
# the frame-dump go/no-go, so that stays a human decision.
#   usage: zsh drafts/pending_after_ab/scratch_saved/boundary_after_25.sh batch27
set -e
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
B="${1:-batch27}"
if pgrep -f 'overnight/chain_trials.py' >/dev/null; then
  echo "HARNESS STILL RUNNING -- refusing (this is the point of the guard)"; exit 1
fi

echo "== archiving as $B"
cp overnight/chain_trials.log  "overnight/chain_trials_$B.log"
cp overnight/chain_trials.json "overnight/chain_trials_$B.json"

echo "\n== tally"
grep -o '^\[ *[0-9]*\] [A-Z]*' "overnight/chain_trials_$B.log" | tr '\n' ' '; echo
printf "arrived: "; grep -c '^\[.*\] ARRIVED' "overnight/chain_trials_$B.log" || true
printf "failed:  "; grep -c '^\[.*\] FAILED'  "overnight/chain_trials_$B.log" || true
printf "invalid: "; grep -c '^\[.*\] INVALID' "overnight/chain_trials_$B.log" || true
echo "walk seconds on arrivals (sorted):"
grep -o 'walk [0-9.]*' "overnight/chain_trials_$B.log" | cut -d' ' -f2 | sort -n | tr '\n' ' '; echo

echo "\n== patch51's own instrument: did the LAST-STOP rule ever fire?"
printf "  'STOP YAW skipped (last stop)' lines: "
grep -c 'STOP YAW skipped (last stop)' "overnight/chain_trials_$B.log" || true
echo "  how the 196 stop was verified each trial:"
grep -E 'k=196 ->' "overnight/chain_trials_$B.log" | grep -oE 'turned-[a-z]+' | sort | uniq -c
echo "  mid-route STOP YAW firings (unaffected by patch51):"
grep -c 'STOP YAW [-+]' "overnight/chain_trials_$B.log" || true

echo "\n== failures, with their reasons"
grep '^\[.*\] FAILED' "overnight/chain_trials_$B.log" | cut -c1-200 || echo "  none"

echo "\n== PERCEPTION PROFILE (the 0.9s nobody has ever split)"
.venv/bin/python -B tools/profile_perception.py --chain route_user_1853 -n 20 \
  2>&1 | tee "overnight/census/perception_profile_$B.txt"

echo "\nDONE. Next launch is a decision, not a default:"
echo "  - frame dump GO?   swap at this boundary, then a plain 25 on the new binary"
echo "  - frame dump NO?   another plain 25 on 2d31263 to accumulate patch51 firings"
