# Snoopy — offloaded mutation testing on the Windows box

**Read this before running any mutation sweep while the console is live.** Like
`GRAVEYARD.md`, it exists so the footguns below are never relearned, and it is
deliberately NOT loaded into context automatically.

## Why a second machine at all

Mutation testing writes a source file thousands of times and Sophos rescans it
every time. On this Mac that is an I/O spike, an I/O spike degrades Python's
`sleep()`, and `slow_traverse` holds the stick and SLEEPS OUT every push — so a
spike during a live run walks the character into a wall and the log records it
as a routing failure (CLAUDE.md §10.13). Snoopy is **2x slower** than the Mac at
ORB (CPU-only; the 3080 contributes nothing). Its value is not speed. **Its value
is being a different machine**: nothing it does touches the Mac's disk.

Snoopy cannot reduce Claude usage; subagents are API calls and do not run there.

## The machine

    host        Brett@snoopy          (answers on `snoopy` and `snoopy.local`)
    key         ~/.ssh/id_ed25519_snoopy   — ALWAYS pass `-i`. There is no
                snoopy entry in ~/.ssh/config, and a global IdentityFile there
                points at a key that does not exist, so bare `ssh snoopy` fails
                with "no such identity: id_rsa.pem" and then permission denied.
    shell       PowerShell. Bash syntax fails to parse, and PowerShell EATS
                double quotes inside `python -c "..."`. Send scripts over
                STDIN instead: `cat <<'PY' | ssh ... 'python.exe -'`. No quoting
                survives otherwise.
    python      C:\baseball\venv\Scripts\python.exe   3.12.10, Windows AMD64, 16 CPUs
    repo copy   C:\baseball\repo      (shipped, see below; NOT a git checkout)
    shim        C:\baseball\shims     (must be on PYTHONPATH, see below)
    logs        C:\baseball\baseline.log, C:\baseball\mutants.log
    ollama      http://snoopy:11434   qwen2.5vl:7b — the ban-screen reader's LAN rung

A first `ssh` after Snoopy has been idle can time out while it wakes; `ping`
answers first. Retry once before diagnosing.

Log lines echoed through a shell show `C:aseballepo` for `C:\baseball\repo` —
`\b`, `\r`, `\t`, `\f` being interpreted. Cosmetic; the file is fine.

## FOOTGUN 1 — `os.kill(pid, 0)` is TerminateProcess on Windows

On Unix `os.kill(pid, 0)` sends no signal; it only asks whether the process
exists. **On Windows any signal other than CTRL_C/CTRL_BREAK is
`TerminateProcess` — including 0.** The liveness probe KILLS the process it is
checking.

Two sites use it as a liveness probe:

    console_lock.py:87          holder()      — is the lock's owner alive?
    input_controller.py:1657    chiaki_pid()  — is the cached chiaki pid alive?

(`kill_runaways.py:77` uses `os.kill(pid, 9)` and MEANS to kill; that one is
fine either way.)

Consequences on Snoopy, under `BASEBALL_TEST_RUN=1`:

- `tests/harness/test_console_exclusive.py` plants a real sleeper pid and asks
  `holder()` whether it is alive. On Windows that terminates the sleeper. The
  test then passes or fails for the WRONG reason.
- `_harness.run_trial` calls `console_lock.acquire()` every trial, which calls
  `holder()` on a lock file holding **its own pid**. The second trial in one
  process would terminate itself.
- `chiaki_pid()` is guarded: `can_use_background_input()` returns False under
  the test flag before the pid is consulted. Do not rely on that staying true.

**So the baseline runner excludes any test whose source matches**
`run_trial\(|console_lock|os\.kill\(`, and `tests/cpp/` (needs clang++ and the
gitignored `chiaki-ng-src/`). Those tests run on the Mac, offline, when the
console is idle. Do not "fix" this by making `os.kill` portable in production:
production never runs on Windows, and a change there for the sake of a test
box is the wrong trade.

## FOOTGUN 2 — `import fcntl` at the top of `analog_replay.py`

`fcntl` is Unix-only. `analog_replay.py:27` imports it at module level, so on
Windows every test that transitively imports `analog_replay` dies at import —
`test_at_table_threshold.py` was the first casualty. Its ONLY use is
`analog_replay.py:171-172`, clearing `O_NONBLOCK` on the FIFO fd.

The fix is a shim on Snoopy, **never in the repo**:

    C:\baseball\shims\fcntl.py

    F_GETFL = 3
    F_SETFL = 4
    LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8
    def fcntl(fd, op, arg=0): return 0
    def flock(fd, op): return None
    def lockf(fd, op, *args): return None

with `$env:PYTHONPATH="C:\baseball\shims"`. Under `BASEBALL_TEST_RUN` the FIFO
is a scratch REGULAR FILE and every input path is held off, so a no-op here is
**exact**, not an approximation. Nothing on Snoopy ever talks to the console.

## What Snoopy CANNOT run, and why that is correct

- Tests anchored on gitignored corpora: `demos/` (347 MB), `screenshot_log/`
  (2.8 GB). They are not shipped. Those tests fail on Snoopy with "missing
  anchor frame ... a test that cannot run must not report success" — which is
  the right answer, and such a test is NOT in the mutation baseline.
- OCR through `tesserocr` (no Windows wheel installed) and anything needing the
  tesseract binary.
- Anything above. A mutant is only meaningful against a test that is GREEN on
  Snoopy first; the driver enforces that.

## The workflow

1. **Ship the tracked tree** (one read burst on the Mac — do it between live
   runs, or with the user's explicit OK):

       git ls-files -z | grep -zvE '^overnight/(drives/|.*\.log$|resetfail/)' \
         | tar -c --null -T - -f - \
         | ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy \
             'tar -x -f - -C C:\baseball\repo'

   Do NOT exclude `overnight/*failframes*`: those are tracked frames that
   `test_failure_kind.py` and `test_frozen_stream_is_invalid.py` are built on
   (28 MB). Excluding them cost a re-ship on 2026-09-07.

2. **Baseline** — `C:\baseball\run_baseline.py`. **RUN IT IN THE FOREGROUND OF AN
   SSH SESSION YOU KEEP OPEN.** The first version of this file said to launch
   it detached with `Start-Process -WindowStyle Hidden` "so a dropped SSH session
   cannot kill it". Measured false, twice: Windows OpenSSH terminates every
   process of a session when that session ends, and `Start-Process` does not
   escape it. Both runner "deaths" line up exactly with the launching session
   closing — the first wrote its 14 fast results in the seconds before, the
   second was killed 12 s in, and a test spawned the same way died at the same
   7 lines of output. Run in the foreground, the same runner finished the other
   27 tests in 159 s with exit 0. From the Mac, hold the session with a
   long-lived `ssh` (a Monitor with `persistent: true` does this); the run's
   duration IS the session's duration. `Invoke-CimMethod Win32_Process Create`
   is the untested alternative if a session cannot be held.

   It selects `tests/*/test_*.py` importing graph_walk / places / table_prompt /
   failure_kind / pose / slow_traverse / worldmap, applies the exclusions above,
   runs each once with a 300 s ceiling, writes PASS/FAIL/TIMEOUT/ERROR per file
   to `baseline.log`, ends with `BASELINE DONE`, and RESUMES: files already in
   the log are skipped, so a killed run costs one test.

   **`venv\Scripts\python.exe` is a launcher stub**: it spawns the real
   interpreter (`C:\Program Files\Python312\python.exe`) as a child and waits.
   Every "python" here is a two-process tree. `p.pid` is the stub; a timeout kill
   must be `taskkill /PID <stub> /T /F` or the interpreter survives it.

   2026-09-07 baseline: **32 PASS, 9 FAIL, 0 TIMEOUT/ERROR** of 41. The FAILs,
   all excluded from mutation and all correct to exclude:

       demos/ anchors missing (gitignored, unshipped):  test_at_table_threshold,
           test_orb_localiser, test_table_prompt, test_add_non_disruption
       needs the real chiaki window:                    test_frozen_stream_is_invalid
       scans the whole overnight/ tree (partly unshipped): test_harness_restores_shipped_value,
           test_overnight_start_hint
       NOT ESTABLISHED why (9 checks each):             test_reference_pose_flag,
           test_yaw_nulled_before_align

   So a mutant in `table_prompt.py` comes back `NO-TEST` on Snoopy; judge those
   on the Mac when the console is idle.

3. **Mutants** — `C:\baseball\run_mutants.py`, same foreground launch. Each mutant is
   `(file, line, must_contain, replacement)`: one line in, one line out, so
   nothing below moves; the line is replaced ONLY if it contains the expected
   text, otherwise `SKIP` — a shifted line number must not mutate the wrong
   statement. Tests are the baseline's PASS files whose source names one of the
   mutant's symbols; each is re-run green on the clean tree first. Originals
   are pinned by sha256 and restored after every mutant, and `__pycache__` is
   deleted between mutants because CPython validates `.pyc` on (mtime, size)
   and a same-size edit runs stale bytecode (CLAUDE.md §10.10). Results in
   `mutants.log`: `CAUGHT`, `SURVIVED`, `NO-TEST`, `SKIP`, then `MUTANTS DONE`.

4. **Watch from the Mac** with network-only polling (no Mac disk):

       ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'Get-Content C:\baseball\mutants.log -Tail 3'

## The one rule that makes any of this necessary

**Never mutate a file in the main checkout while a live run is up.**
`_harness.run_trial` spawns `python <script> --one-trial <arm>` per trial, and
that child imports `graph_walk.py` fresh from disk. A mutant on disk for ten
seconds is the code the next trial runs, and nothing reports it: the trial is
scored as an arm result. See CLAUDE.md §10.17. A git worktree under the
scratchpad is isolated from that (the first attempt on 2026-09-07 used one, and
was stopped anyway because the I/O is the same disk); Snoopy is isolated from
both.

## FOOTGUN 3 — the runner itself dies silently, and "slow" and "hung" look identical

First launch, 2026-09-07: the baseline runner recorded 14 results in 8 minutes,
then wrote NOTHING for 40 minutes against a 300 s per-test ceiling. The log's
last line was a normal result; the heartbeat did not exist yet; the watcher
saw "no change" and a 300 s ceiling made "still running" plausible. When
finally checked, there was no Python process on Snoopy at all: the runner had
died at 00:58:03 on `test_graph_walk.py` without writing a line. §10.1's shape
exactly, one machine over.

ESTABLISHED: it died, silently, with no log line, 8 minutes after launch.
ASSUMED (not reproduced — the rewrite removes both candidates regardless):

- `subprocess.run(..., text=True)` decodes the child's output with the locale
  codec, which is **cp1252 on Windows**. This suite prints UTF-8 arrows and
  dashes. One byte cp1252 cannot decode raises `UnicodeDecodeError` inside the
  runner, uncaught, and the runner exits. `test_graph_walk.py` is the first
  chatty test in selection order.
- `capture_output=True` uses pipes. A grandchild that inherits the pipe keeps it
  open after the child is killed, and `communicate()` then waits past the
  timeout forever.

What the runner does now, and why each line exists:

    encoding utf-8, errors=replace      cannot raise on output
    output to a temp FILE, not a pipe   a grandchild cannot hang it
    taskkill /PID <pid> /T /F           timeout kills the TREE, not one process
    try/except per test -> ERROR line   a runner bug is a row, not a death
    C:\baseball\runner.state heartbeat  "RUNNING <test> since HH:MM:SS" — the
                                        file that makes hung and slow differ
    resumable                           skips files already recorded, so a
                                        crash costs the current test, not all
    PYTHONIOENCODING=utf-8 in the child so the child does not die the same way

**Check the heartbeat before believing a slow test is slow:**

    ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'Get-Content C:\baseball\runner.state'

If it names a test and the timestamp is older than the ceiling, the runner is
dead, and `Get-CimInstance Win32_Process -Filter "name='python.exe'"` will show
nothing. Relaunch; it resumes.

**Re-running a test that was recorded before its inputs existed:** the runner
skips anything already in the log, so delete that test's line from
`baseline.log` and relaunch. (Two tests were recorded FAIL before their tracked
frames were shipped; see FOOTGUN under "ship".)

## FOOTGUN 4 — a text-mode write on Windows turns LF into CRLF, and the sha check calls it a bad restore

The first mutant of the 2026-09-07 sweep reported `RESTORE MISMATCH`. It was
not a bad restore. `open(p).read()` in text mode folds `\r\n` to `\n`;
`open(p, "w").write(orig)` in text mode emits `\r\n` on Windows. The file came
off the Mac as LF, went back as CRLF, and the byte hash changed while the
content did not: `graph_walk.py` afterwards was 2,308 CRLF lines and 0 LF, with
a `\r\n`-normalised sha256 of `F58E6AD109734572` — identical to Mac HEAD — and
no `# MUTANT` marker anywhere. Every later mutant restores CRLF to CRLF and
matches, so only the FIRST mutant on each file reports it.

Python does not care about the endings, so the sweep's verdicts stand. The
driver now reads and writes with `newline=""` so the bytes round-trip. To
compare a Snoopy copy against Mac HEAD, hash with `\r\n` normalised to `\n`, or
you will chase a difference that is not one.
