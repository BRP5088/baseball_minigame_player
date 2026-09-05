#!/bin/bash
# Run the whole offline suite. No API calls, no PS5 input — safe any time.
#
# Tests live in tests/<area>/test_*.py (routing, minigame, rig, harness).
# THE SEARCH IS RECURSIVE. It used to be `for f in tests/test_*.py`, which
# matched nothing once the files moved into subdirectories.
cd "$(dirname "$0")"

# Parallelism. Default 4, not nproc: this is a work machine with Sophos
# Anti-Virus, and four parallel mutation sweeps once drove the load average to
# 273-333 and the suite to ~2 files per FOUR MINUTES. Raise with JOBS=n if the
# machine is idle; use JOBS=1 to reproduce the old sequential behaviour exactly.
#
# NEVER run this while taking live console measurements. Under saturation
# Python's sleep degrades from ~5ms to as much as 242ms, which corrupts every
# walked leg.
JOBS=${JOBS:-4}

# Per-test wall clock. macOS ships no `timeout`, but perl is always present and
# alarm(2) does the same job: exec the test, kill it on SIGALRM (exit 142).
#
# Without this, ONE hung test blocks the entire suite forever. On 2026-09-01
# tests/test_input_timing.py spun in `while ACTION_DELAY < MAX_ACTION_DELAY`
# after a change made that condition unreachable; five copies accumulated at
# 486% CPU alongside the live game, and the suite reported pass counts from
# runs that had never finished.
TEST_TIMEOUT=${TEST_TIMEOUT:-300}

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

# One test, run in a child. Exported so xargs can call it.
run_one() {
    f="$1"
    # A stable, filesystem-safe name for this test's result files.
    key=$(echo "$f" | tr '/' '_')
    # BASEBALL_TEST_RUN makes orchestrator stamp any match-log row written from
    # here as _synthetic, even if the test forgot to redirect the log.
    # The key is pinned UNCONDITIONALLY, not ${VAR:-dummy}: this shell exports
    # the real key, so a default would never have applied and the offline suite
    # ran with live credentials.
    #
    # Both assignments must stay on the continuation with no comment between
    # them. A comment after a trailing backslash ENDS the continuation, which
    # silently dropped BASEBALL_TEST_RUN from the child environment — the suite
    # then ran with background input live and sent real keystrokes into the
    # running game. Comments go above the `if`, never inside it.
    if BASEBALL_TEST_RUN=1 \
       PERSONAL_ANTHROPIC_API_KEY="dummy-offline-test" \
       perl -e 'alarm shift; exec @ARGV' "$TEST_TIMEOUT" python3 "$f" \
       > "$OUT/$key.out" 2>&1; then
        echo "PASS" > "$OUT/$key.status"
    else
        rc=$?
        if [ $rc -eq 142 ]; then echo "HUNG" > "$OUT/$key.status"
        else echo "FAIL" > "$OUT/$key.status"; fi
    fi
}
export -f run_one
export OUT TEST_TIMEOUT

# Collect first so the count is known before anything runs — see the zero-tests
# check below.
# HARNESS_LAST: A WELL-MOTIVATED CHANGE THAT MEASURED WORSE. Default is 0.
#
# test_no_side_effects.py re-executes every OTHER test file in subprocesses, so
# with it inside the parallel pass every heavy file runs TWICE — test_map_admit
# is ~51s of genuine ORB work, charged twice, at peak concurrency of 4 outer +
# 8 inner. Running it alone at the end looked obviously better.
#
# Measured 2026-09-04, 94 files, same machine, back to back:
#
#     HARNESS_LAST=1 (alone at the end)   322s
#     HARNESS_LAST=0 (folded in)          241s
#
# The split is 81s SLOWER. The double execution costs CPU but not WALL CLOCK,
# because it overlaps; serialising the harness just adds its whole duration to
# the end. The fixture races that concurrency caused were fixed independently by
# pid-suffixing the /tmp sinks, so the split had no remaining benefit.
#
# Kept as a flag rather than deleted: it is the honest record, and it is the
# right shape if the harness ever stops re-running the suite.
main_files=$(find tests -name 'test_*.py' -type f -not -path 'tests/harness/*' | sort)
harness_files=$(find tests/harness -name 'test_*.py' -type f 2>/dev/null | sort)
files=$(printf '%s\n%s\n' "$main_files" "$harness_files" | grep -c . >/dev/null; \
        printf '%s\n%s' "$main_files" "$harness_files" | grep .)
ran=$(echo "$files" | grep -c . )

if [ "$ran" -eq 0 ]; then
    echo "--- NO TESTS RAN (found no tests/**/test_*.py)"
    exit 1
fi

# HARNESS_LAST=1 runs tests/harness/ alone after the parallel pass; =0 folds it
# in. A/B'd 2026-09-04 because the "obvious" answer was wrong — see below.
if [ "${HARNESS_LAST:-0}" = "1" ]; then
    echo "$main_files" | grep . | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
    if [ -n "$harness_files" ]; then
        for hf in $harness_files; do run_one "$hf"; done
    fi
else
    echo "$files" | grep . | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}
fi

# Report in a stable order, grouped by area, so a diff between two runs is
# readable. Results are printed AFTER the run because parallel output would
# otherwise interleave mid-line.
fail=0
last_dir=""
for f in $files; do
    d=$(dirname "$f")
    if [ "$d" != "$last_dir" ]; then printf "\n%s\n" "$d"; last_dir="$d"; fi
    key=$(echo "$f" | tr '/' '_')
    status=$(cat "$OUT/$key.status" 2>/dev/null || echo "FAIL")
    printf "  %-38s %s\n" "$(basename $f)" "$status"
    if [ "$status" != "PASS" ]; then
        fail=1
        if [ "$status" = "HUNG" ]; then
            echo "    killed after ${TEST_TIMEOUT}s — it never finished, so it"
            echo "    proved nothing. A suite that waits forever reports nothing."
        fi
        sed 's/^/    /' "$OUT/$key.out" | tail -8
    fi
done

# ZERO TESTS IS A FAILURE, not a pass. Previously `fail` stayed 0 when the glob
# matched nothing, so a suite that ran nothing at all printed "all green" and
# exited 0 — indistinguishable from one where everything passed.
echo
[ $fail -eq 0 ] && echo "--- all green ($ran files, JOBS=$JOBS)" \
                || echo "--- FAILURES above ($ran files, JOBS=$JOBS)"
exit $fail
