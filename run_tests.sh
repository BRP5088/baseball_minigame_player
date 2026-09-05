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

# Per-test wall clock. macOS ships no `timeout`, but perl is always present.
#
# IT MUST BE SIGKILL FROM A PARENT, NOT SIGALRM INTO THE TEST. The obvious
# wrapper -- alarm, then exec the test -- REPLACES this process, so SIGALRM is
# delivered to the test itself. cysignals, pulled in transitively through the
# vision stack, installs a SIGALRM handler that raises AlarmInterrupt, so the
# test died with an ordinary Python traceback and exit 1. A HANG was therefore
# indistinguishable from a FAILURE, and the "it never finished, so it proved
# nothing" branch below could never run. Found 2026-09-05 when
# tests/routing/test_leg_turn_tolerance.py hit the ceiling under load and was
# reported as a plain FAIL. Nothing can install a handler for SIGKILL.
# Pinned by tests/harness/test_suite_timeout_kills.py.
#
# Without this, ONE hung test blocks the entire suite forever. On 2026-09-01
# tests/test_input_timing.py spun in `while ACTION_DELAY < MAX_ACTION_DELAY`
# after a change made that condition unreachable; five copies accumulated at
# 486% CPU alongside the live game, and the suite reported pass counts from
# runs that had never finished.
TEST_TIMEOUT=${TEST_TIMEOUT:-300}

TIMEOUT_PL=$(cat <<'PERL'
my $t = shift;
my $pid = fork();
die "fork failed: $!" unless defined $pid;
if ($pid == 0) { exec @ARGV; exit 127 }
$SIG{ALRM} = sub { kill 'KILL', $pid; waitpid($pid, 0); exit 142 };
alarm $t;
waitpid($pid, 0);
my $st = $?;
alarm 0;
exit($st & 127 ? 128 + ($st & 127) : $st >> 8);
PERL
)

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

# One test, run in a child. Exported so xargs can call it.
run_one() {
    f="$1"
    # A stable, filesystem-safe name for this test's result files.
    key=$(echo "$f" | tr '/' '_')
    start=$(date +%s)
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
       perl -e "$TIMEOUT_PL" "$TEST_TIMEOUT" python3 "$f" \
       > "$OUT/$key.out" 2>&1; then
        echo "PASS" > "$OUT/$key.status"
    else
        rc=$?
        if [ $rc -eq 142 ]; then echo "HUNG" > "$OUT/$key.status"
        else echo "FAIL" > "$OUT/$key.status"; fi
    fi
    # LIVE PROGRESS. The suite printed nothing at all until every file had
    # finished, so a 200s run and a wedged one looked identical from outside for
    # three minutes — the same "slow step and hung step with identical output"
    # shape the timeout wrapper above exists to fix, one level up. The count is
    # derived from the status files rather than a counter variable, because each
    # run_one runs in its own xargs subshell and a shared variable would not
    # survive.
    #
    # Written to stderr so that redirecting stdout to a log still shows progress
    # on the terminal, and so it can never be mistaken for a test's own output.
    secs=$(( $(date +%s) - start ))
    n=$(ls "$OUT"/*.status 2>/dev/null | wc -l | tr -d ' ')
    st=$(cat "$OUT/$key.status")
    slow=""
    [ "$secs" -ge 30 ] && slow="  <-- slow"
    printf "  [%3d/%3d] %-6s %-44s %4ds%s\n" \
        "$n" "$TOTAL" "$st" "$(basename "$f")" "$secs" "$slow" >&2
}
export -f run_one
export OUT TEST_TIMEOUT TIMEOUT_PL TOTAL

# Collect first so the count is known before anything runs — see the zero-tests
# check below.
#
# --affected runs only the tests whose import closure reaches something git says
# changed. It is for the edit loop; it is NOT a substitute for the full suite,
# because import edges cannot see a test that reads a fixture or asserts on a
# JSON file. affected_tests.py knows that and selects everything whenever a
# non-.py file changed. The pre-commit hook still runs the real thing.
if [ "$1" = "--affected" ]; then
    echo "--- affected-only mode"
    files=$(python3 affected_tests.py)
    sel_rc=$?
    if [ $sel_rc -ne 0 ]; then
        echo "--- could not work out what changed; run without --affected"
        exit 1
    fi
    if [ -z "$(echo "$files" | grep .)" ]; then
        echo "--- nothing to run (no changes affect any test)"
        exit 0
    fi
else
    files=$(find tests -name 'test_*.py' -type f | sort)
fi
ran=$(echo "$files" | grep -c . )

if [ "$ran" -eq 0 ]; then
    echo "--- NO TESTS RAN (found no tests/**/test_*.py)"
    exit 1
fi

# SINGLE PASS. test_no_side_effects.py used to re-execute every OTHER test file
# in its own subprocesses, so the whole suite ran TWICE — once here and once
# inside it. That was ~half the CPU of a run for no extra coverage: the guard
# only needs a before/after snapshot bracketing SOME execution of the suite, and
# this script already provides one.
#
# So it is driven in two pieces instead. --snapshot writes the "before" state,
# the parallel pass runs, --check takes the "after" state and diffs. Its
# self-contained mode (no arguments) still exists and still re-runs everything;
# that is the form to use when running the guard on its own.
#
# The earlier HARNESS_LAST flag was a workaround for the double execution
# (measured 2026-09-04: serialising harness/ was 81s SLOWER, 322s vs 241s,
# because the doubling overlapped and cost CPU rather than wall clock). With the
# doubling gone there is nothing left for it to trade off, so it is gone too.
SIDE_EFFECTS="tests/harness/test_no_side_effects.py"
if [ ! -f "$SIDE_EFFECTS" ]; then
    echo "--- $SIDE_EFFECTS is missing; the side-effect guard cannot run"
    exit 1
fi
run_files=$(echo "$files" | grep -v "^${SIDE_EFFECTS}$")
n_run=$(echo "$run_files" | grep -c . )

# The denominator, known before anything runs. Includes the side-effect check,
# which is run separately below but is one of the files being reported.
TOTAL=$ran
echo "--- $ran test files, JOBS=$JOBS, ${TEST_TIMEOUT}s ceiling each" >&2
start_all=$(date +%s)

SNAP="$OUT/before_state.json"
if ! python3 "$SIDE_EFFECTS" --snapshot "$SNAP"; then
    echo "--- could not snapshot project state; refusing to run blind"
    exit 1
fi

echo "$run_files" | grep . | xargs -P "$JOBS" -I{} bash -c 'run_one "$@"' _ {}

# The diff, reported as if it were an ordinary test so it lands in the table
# below. n_run is passed so --check can refuse to certify a pass where nothing
# actually ran: on its own a clean diff cannot tell "no test wrote to project
# state" from "no test executed".
se_key=$(echo "$SIDE_EFFECTS" | tr '/' '_')
if BASEBALL_TEST_RUN=1 \
   PERSONAL_ANTHROPIC_API_KEY="dummy-offline-test" \
   perl -e "$TIMEOUT_PL" "$TEST_TIMEOUT" \
   python3 "$SIDE_EFFECTS" --check "$SNAP" "$n_run" \
   > "$OUT/$se_key.out" 2>&1; then
    echo "PASS" > "$OUT/$se_key.status"
else
    se_rc=$?
    if [ $se_rc -eq 142 ]; then echo "HUNG" > "$OUT/$se_key.status"
    else echo "FAIL" > "$OUT/$se_key.status"; fi
fi
printf "  [%3d/%3d] %-6s %-44s\n" "$ran" "$TOTAL" \
    "$(cat "$OUT/$se_key.status")" "$(basename "$SIDE_EFFECTS")" >&2

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
took=$(( $(date +%s) - start_all ))
[ $fail -eq 0 ] && echo "--- all green ($ran files, JOBS=$JOBS, ${took}s)" \
                || echo "--- FAILURES above ($ran files, JOBS=$JOBS, ${took}s)"
exit $fail
