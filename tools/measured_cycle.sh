#!/bin/zsh
# ONE cycle of the continuous loop, with everything it produced kept in ONE directory so
# two runs can be compared without untangling shared files.
#
#   overnight/runs/<stamp>/
#       run.json       the build: git sha, whether the tree was dirty, and every timing
#                      constant in force at launch -- so a result can never be attributed
#                      to a build nobody recorded
#       cycle.log      the run's output, every line stamped with wall time
#       events.jsonl   every capture, press, OCR, paid read and reveal episode, each
#                      carrying the dump frame it saw
#       stream.mp4     the whole cycle at 60 fps, with frames.jsonl to join on `seq`
#       summary.json   written at the end by tools/summarise_run.py
#
# usage: zsh tools/measured_cycle.sh [label]
set -e
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f 'overnight/chain_trials.py' >/dev/null || pgrep -f 'run_cycles.py' >/dev/null; then
  echo "a console process is already running -- refusing"; exit 1
fi
LABEL="${1:-cycle}"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN="overnight/runs/${STAMP}_${LABEL}"
mkdir -p "$RUN"
source ~/.zshrc.secrets
[ -n "$PERSONAL_ANTHROPIC_API_KEY" ] || { echo "PERSONAL_ANTHROPIC_API_KEY not set -- refusing"; exit 1; }
export BASEBALL_API_BUDGET=200          # ~$2.40 hard ceiling; run_cycles refuses below 120
export BASEBALL_EVENT_LOG="$PWD/$RUN/events.jsonl"
unset BASEBALL_TEST_RUN

.venv/bin/python -B - "$RUN" "$LABEL" <<'PY'
import json, subprocess, sys, os
run, label = sys.argv[1], sys.argv[2]
import orchestrator as o, reveal_watch as rw, run_cycles as rc
sha = subprocess.run(["git","rev-parse","--short","HEAD"],capture_output=True,text=True).stdout.strip()
dirty = bool(subprocess.run(["git","status","--porcelain","--untracked-files=no"],
                            capture_output=True,text=True).stdout.strip())
json.dump({
    "label": label, "git_sha": sha, "tree_dirty": dirty,
    "api_budget": int(os.environ.get("BASEBALL_API_BUDGET", 0)),
    "constants": {
        "HAND_DEAL_THRESHOLD": o.hand_deal_threshold(),
        "POST_PLAY_DEAL_MAX_WAIT": o.POST_PLAY_DEAL_MAX_WAIT,
        "POST_PLAY_MIN_WAIT": o.POST_PLAY_MIN_WAIT,
        "post_play_wait_for_deal": o.post_play_wait_for_deal(),
        "REVEAL_EDGE_THRESHOLD": o.REVEAL_EDGE_THRESHOLD,
        "REVEAL_MAX_WAIT": o.REVEAL_MAX_WAIT,
        "PEAK_SETTLE_SEC": rw.PEAK_SETTLE_SEC,
        "CLOSE_GAP": rw.CLOSE_GAP,
        "WALK_ATTEMPTS": rc.walks_per_cycle(),
    },
}, open(os.path.join(run, "run.json"), "w"), indent=1)
print(f"== build {sha}{' (DIRTY)' if dirty else ''}; constants recorded in {run}/run.json")
PY

.venv/bin/python -B tools/record_stream.py "$RUN" > "$RUN/recorder.out" 2>&1 &
REC=$!
sleep 2
echo "== $RUN  (recorder pid $REC)"
echo "== record before: $(.venv/bin/python -B -c "import json;d=json.load(open('progress_testing.json'));print(d['balance'],d['wins'],d['losses'],d['match_in_progress'])")"
PYTHONUNBUFFERED=1 .venv/bin/python -B run_cycles.py 1 2>&1 \
  | .venv/bin/python -u -c 'import sys,time
for l in sys.stdin: sys.stdout.write(f"{time.time():.3f} {l}"); sys.stdout.flush()' \
  | tee "$RUN/cycle.log"
kill -INT $REC 2>/dev/null || true
wait $REC 2>/dev/null || true
echo "== record after:  $(.venv/bin/python -B -c "import json;d=json.load(open('progress_testing.json'));print(d['balance'],d['wins'],d['losses'])")"
.venv/bin/python -B tools/summarise_run.py "$RUN"
