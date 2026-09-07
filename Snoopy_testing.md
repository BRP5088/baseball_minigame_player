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

2. **Baseline** — `C:\baseball\run_baseline.py`, launched DETACHED so a dropped
   SSH session cannot kill it (Windows OpenSSH terminates the session's job):

       Start-Process -FilePath C:\baseball\venv\Scripts\python.exe `
                     -ArgumentList "C:\baseball\run_baseline.py" -WindowStyle Hidden

   It selects `tests/*/test_*.py` importing graph_walk / places / table_prompt /
   failure_kind / pose / slow_traverse / worldmap, applies the exclusions above,
   runs each once with a 300 s ceiling, and writes PASS/FAIL/TIMEOUT per file
   to `baseline.log`, ending with `BASELINE DONE`.

3. **Mutants** — `C:\baseball\run_mutants.py`, same launch. Each mutant is
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
