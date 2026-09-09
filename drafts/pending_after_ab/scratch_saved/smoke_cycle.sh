#!/bin/zsh
# ONE CYCLE of the continuous loop, as a smoke test. Real money is capped here.
#   usage: zsh drafts/pending_after_ab/scratch_saved/smoke_cycle.sh
set -e
cd "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
if pgrep -f 'overnight/chain_trials.py' >/dev/null; then echo "a trial harness is running -- refusing"; exit 1; fi
# The key comes from the user's own secrets file, exactly as preflight instructs.
# Its value never appears in any log or output: only its presence is checked.
source ~/.zshrc.secrets
[ -n "$PERSONAL_ANTHROPIC_API_KEY" ] || { echo "PERSONAL_ANTHROPIC_API_KEY not set after sourcing -- refusing"; exit 1; }
# THE REAL-MONEY CAP. 200 vision calls at ~$0.012 = ~$2.40 hard ceiling; a match
# costs 20-89 calls, so this is two to four matches. run_cycles refuses below 120.
export BASEBALL_API_BUDGET=200
mkdir -p overnight/events
export BASEBALL_EVENT_LOG="$PWD/overnight/events/cycle_$(date +%Y%m%d_%H%M).jsonl"
echo "== event log: $BASEBALL_EVENT_LOG"
unset BASEBALL_TEST_RUN
echo "== record before: balance $(.venv/bin/python -B -c "import json;print(json.load(open('progress_testing.json'))['balance'])"), match_in_progress $(.venv/bin/python -B -c "import json;print(json.load(open('progress_testing.json'))['match_in_progress'])")"
.venv/bin/python -B -c "import ensure_stream as es; print('ensure_live ->', es.ensure_live())" 2>&1 | tail -1
echo "== launching ONE cycle at $(date '+%H:%M:%S'); log -> overnight/smoke_cycle.log"
PYTHONUNBUFFERED=1 .venv/bin/python -B run_cycles.py 1 2>&1 | .venv/bin/python -u -c 'import sys,time
for l in sys.stdin: sys.stdout.write(f"{time.time():.3f} {l}"); sys.stdout.flush()' | tee overnight/smoke_cycle.log
echo "== record after:  balance $(.venv/bin/python -B -c "import json;print(json.load(open('progress_testing.json'))['balance'])"), wins $(.venv/bin/python -B -c "import json;print(json.load(open('progress_testing.json'))['wins'])"), losses $(.venv/bin/python -B -c "import json;print(json.load(open('progress_testing.json'))['losses'])")"
