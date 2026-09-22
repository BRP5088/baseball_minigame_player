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

    console_lock.holder()                     — is the lock's owner alive?
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

## Vision labelling with Qwen3-VL (2026-09-21)

**CLAUDE.md §10.27 applies here without exception: this is a LABELLING AID,
never part of the live ladder.** Snoopy is a second machine for offline work —
labelling corpora, adjudicating frames, sweeps that would saturate the Mac
(§10.13) — not a runtime dependency of the $50 loop. Nothing on the live path
may come to depend on a model being up on another box, and a small clean
sample disqualifies a reader on the money screen but never certifies one: the
2026-09-09 qwen2.5vl sweep looked clean at 29 frames and would have shipped a
false positive on `match_start_prompt` (a $50 screen) had it not been checked
against the specific failure mode already on record. The same caution applies
here — one frame below is not a certification of anything, least of all the
"which card is raised" question, which it got wrong.

**The 2026-09-09 Ollama models (`qwen2.5vl:7b`, `qwen3-vl:8b` at
`http://snoopy:11434`) are GONE.** Ollama is not what is running on Snoopy any
more; the vision server is now Unsloth Studio's own llama.cpp fork, launched
from the desktop app, not a service you start over SSH. Do not `ssh` in and
try to `ollama run` anything — check what is actually listening first (below).

### What is running, and how to find it without touching it

Unsloth Studio (the desktop app on Snoopy) spawns Unsloth's llama.cpp fork,
`C:\Users\Brett\.unsloth\llama.cpp\build\bin\Release\llama-server.exe`, as a
child process per loaded model, and exposes its own front door on
`127.0.0.1:8888`. The loaded model as of this session is
`unsloth/Qwen3-VL-8B-Instruct-GGUF` (Q4_K_M + mmproj).

Port discovery, read-only, no process touched:

    ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'powershell -Command "Get-Process llama-server | Select-Object Id,ProcessName,StartTime,Path"'
    ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'powershell -Command "Get-NetTCPConnection -OwningProcess <pid> -State Listen | Select-Object LocalPort"'

This session: PID 26956, started 2026-09-21 11:29:24, listening on **61758**.
The port is NOT stable across a Studio restart or a model swap — always
re-discover it this way rather than hardcoding it. Confirm the loaded model
from the server's own `/props` (never assume from the desktop UI):

    ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'powershell -Command "Invoke-RestMethod -Uri http://127.0.0.1:<port>/props | ConvertTo-Json -Depth 5"'

`/props` reported `"model_alias": "unsloth/Qwen3-VL-8B-Instruct-GGUF"`,
`"model_ftype": "Q4_K - Medium"`, `"modalities": {"vision": true, ...}`,
`n_ctx` 9216, 4 slots. This is the OpenAI-compatible llama-server front door,
not a custom API — `/v1/chat/completions` takes standard
`image_url: {url: "data:image/...;base64,<...>"}` content blocks.

**The Studio front on 8888 requires auth and was NOT used.** `GET
127.0.0.1:8888/v1/models` from Snoopy itself returned
`{"error":{"message":"Not authenticated", ...}}`. No credential was supplied
or sought (that is out of scope for a read-and-call task), so **the working
front door is the llama-server port directly (61758 this session), not
8888**. If 8888 is ever preferred, it needs whatever API key Unsloth Studio
issues, found in the desktop app, not over SSH.

### PowerShell quoting: the STDIN rule extends past `python -c`

`Snoopy_testing.md`'s existing STDIN rule was written for `python -c`;
PowerShell eats double quotes there too when they carry a script rather than
a one-liner (`Invoke-RestMethod ... | ConvertTo-Json` sent as an inline
`-Command "..."` string failed with `TerminatorExpectedAtEndOfString`). Same
fix, same shape: pipe the script to `powershell -Command -`, which reads it
from STDIN and needs no quoting at all —

    cat <<'PS1' | ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'powershell -Command -'
    Invoke-RestMethod -Uri http://127.0.0.1:61758/props | ConvertTo-Json -Depth 5
    PS1

### The one call that worked

Fixture `test_fixtures/hand_reads/i37_one_lifted_20260921.png` copied over
scp (no directory needed, it lands directly under `C:\Users\Brett\`):

    scp -i ~/.ssh/id_ed25519_snoopy test_fixtures/hand_reads/i37_one_lifted_20260921.png "Brett@snoopy:C:/Users/Brett/tmp_label.png"

Then a base64-encoded `/v1/chat/completions` POST, run as a Python STDIN
script on Snoopy's own venv interpreter (`urllib.request`, stdlib only — no
new dependency for one HTTP call):

    cat <<'PY' | ssh -i ~/.ssh/id_ed25519_snoopy Brett@snoopy 'C:\baseball\venv\Scripts\python.exe -'
    import base64, json, time, urllib.request

    with open(r"C:\Users\Brett\tmp_label.png", "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    prompt = ("This is a card game screen. List the five cards in the hand fan at the "
              "bottom, left to right, as either BATTER <power>/<speed>, PITCHER "
              "<power>/<fielding>, or the tactics card's name, and say which card if "
              "any is raised above the others.")

    payload = {
        "model": "unsloth/Qwen3-VL-8B-Instruct-GGUF",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]}],
        "temperature": 0.0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:61758/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8")
    print("WALL_TIME_SECONDS:", round(time.time() - t0, 2))
    print(body)
    PY

**Measured: 3.02s wall time**, `prompt_n` 2110 tokens (the image dominates),
`predicted_n` 75, 105.8 tok/s generation on the 3080. Raw response:

    {"choices":[{"finish_reason":"stop","index":0,"message":{"role":"assistant",
    "content":"From left to right, the five cards in the hand fan at the bottom
    are:\n\n1. FIELDING PLAY\n2. PITCHER 9/2\n3. PITCHER 7/2\n4. PITCHER 9/2\n5.
    PITCHER 6/2\n\nThe card raised above the others is: FIELDING PLAY"}}],
    "usage":{"completion_tokens":75,"prompt_tokens":2110,"total_tokens":2185},
    "timings":{"prompt_ms":2073.0,"predicted_ms":699.1,"predicted_per_second":105.8}}

**Truth for that frame** (`i37_one_lifted_20260921.png`, as supplied, not
this project's own reader): Fielding Play +1 | Pitcher 9/2 (raised) | Pitcher
7 | Pitcher 9 | Pitcher 6.

**Graded exactly, not generously:**

    slot        model said        truth              verdict
    1 (kind)    FIELDING PLAY     Fielding Play +1    kind right, bonus (+1) not stated
    2 (power)   PITCHER 9/2       Pitcher 9/2          right
    3 (power)   PITCHER 7/2       Pitcher 7            power right, /2 fielding UNCONFIRMED
                                                       (truth gives no fielding for this slot)
    4 (power)   PITCHER 9/2       Pitcher 9             power right, /2 UNCONFIRMED
    5 (power)   PITCHER 6/2       Pitcher 6             power right, /2 UNCONFIRMED
    raised      FIELDING PLAY     Pitcher 9/2 (slot 2)  WRONG

So: the four player powers (9, 7, 9, 6) and the kind sequence
(fielding/pitcher x4) are correct. **The "which card is raised" question — the
one this exact prompt asked for, and the one CLAUDE.md's own cursor-reading
history (§10.36's "hover does not lift a card" correction) makes hardest —
was answered wrong**, naming the tactics card instead of the actual raised
slot. The model also invented a uniform `/2` fielding figure for slots 3-5
that the truth string never confirms one way or the other (it only confirms
`/2` for slot 2); at best that is 1 correct and 3 unconfirmed, not 4 correct.
This is n=1 and settles nothing about accuracy — it only proves the call
path works end to end, which is what this section exists to document.

### Cleanup

`tmp_label.png` deleted from `C:\Users\Brett\` after the call
(`Remove-Item ... -Force`, confirmed with `Test-Path` returning `False`). No
process on Snoopy was stopped, restarted or reconfigured to do any of this —
only `Get-Process`, `Get-NetTCPConnection`, `/props`, `scp`, and one POST to
an already-running server.

## Full suite on Snoopy (2026-09-22)

Tesseract installed, the gitignored fixtures the diff table named as missing were
shipped, and the full suite re-run at HEAD 204bb5b. User-approved for this session
(2026-09-22): install tesseract, ship the small fixtures. Read-only on the checkout
otherwise.

### Install

    winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements

Installs `C:\Program Files\Tesseract-OCR\tesseract.exe`, version **5.4.0.20240606**
(leptonica-1.84.1). **Not added to the machine PATH** — prepend it in the launching
shell before running anything that shells out to it:

    $env:PATH = "C:\Program Files\Tesseract-OCR;" + $env:PATH

`pip install tesserocr` in `C:\baseball\venv` **fails** — no Windows wheel, and the
sdist build dies with `RuntimeError: Tesseract library not found in LIBPATH: []`
(it wants pkg-config, absent here). `ocr_glyphs.backend()` falls back to `"batch"`
(not `"tesserocr"`, not `"pytesseract"` — a third mode that still spawns a
`tesseract.exe` subprocess per call), confirmed working end to end on a synthetic
image. **Do not spend time chasing a tesserocr wheel here; batch-mode pytesseract is
what Snoopy gets.**

### Fixtures shipped (the diff table's ~9 "gitignored corpora" failures, plus one the
### diff table never named)

Individually-named files only where the test names them; whole directories only
where the test globs the directory as a candidate pool (`test_map_admit.py` /
`test_add_non_disruption.py` both pass `explore/20260904_152521_bar_area` itself to
`admit()`). Staged tree: 263 files, 55M, shipped as one tar over scp, extracted into
`C:\baseball\repo`:

    94 named files, 14,419,381 bytes   demos/dealer_circle_20260828_095808/f_*.jpg
                                        (first 40 sorted, test_find_bar_is_not_a_stream_check.py),
                                        2 named demos frames (test_at_table_threshold.py),
                                        18 named demos frames from walk3_full_20260828_050731/
                                        (test_orb_localiser.py + test_jukebox_match_min.py),
                                        screenshot_log/reset_*.jpg (28 files,
                                        test_pause_menu.py), overnight/run_one_match_20260920{,b,c}.log
                                        + overnight/run_live_20260920{d,h}.log (5 files,
                                        test_run_census.py)
    1 named file,     1,468,006 bytes  diagnostics/20260910_103221_5018/screen_at_stall.png
                                        (test_result_reader.py)
    explore/20260904_152521_bar_area/  whole dir, 161 files, 24M
    route_frames/                      whole dir, 7 files, 16M (test_landmark_check.py)

**A TENTH FIXTURE, NEVER NAMED IN THE PRIOR DIFF TABLE: `places_backup_20260903_020639/`
(334.0K).** `graph_walk.py:1611` — `HUMAN_REFERENCE_DIR = "places_backup_20260903_020639"`,
gitignored (`.gitignore:103`), read by `_recorded_reference()` when
`REFERENCE_POSE == "human"`. Missing it made `test_reference_pose_flag.py` FAIL 9 of
9 checks the same way every time — `glob.glob` on the missing dir returns `[]`, the
function falls through to the `places/` lookup, and BOTH poses silently resolve to
the SAME file. This is the exact cause of the 2026-09-07 baseline's "NOT ESTABLISHED
why (9 checks each)" entry for this file — a missing gitignored fixture, not a code
defect. Shipped it (`tar -cf places_backup.tar places_backup_20260903_020639`,
334.0K); the test went from 9 FAIL to 9 PASS ("all green"), confirmed by a standalone
rerun. **Recheck `HUMAN_REFERENCE_DIR`-shaped constants (a gitignored directory named
by a single string, read by exactly one function) before trusting any "cannot
reproduce" verdict on a test that touches `graph_walk`.**

### Sync recipe

    git archive 204bb5b -o ship_204bb5b.tar                    # on the Mac
    tar -cf fixtures.tar -C <staged tree> .                    # the fixtures above
    scp -i ~/.ssh/id_ed25519_snoopy ship_204bb5b.tar Brett@snoopy:C:/baseball/
    scp -i ~/.ssh/id_ed25519_snoopy fixtures.tar Brett@snoopy:C:/baseball/

    # over a held ssh session, wipe first (no .snoopy_commit marker means an
    # incremental extract is a guess about what is already there):
    Remove-Item C:\baseball\repo -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path C:\baseball\repo | Out-Null
    cd C:\baseball\repo
    tar -xf C:\baseball\ship_204bb5b.tar
    tar -xf C:\baseball\fixtures.tar
    "204bb5b9904d5a26a15c44e7f68d5ca2aaf88880" | Out-File -Encoding ascii C:\baseball\repo\.snoopy_commit

### Runner invocation

    $env:PATH = "C:\Program Files\Tesseract-OCR;" + $env:PATH
    cd C:\baseball
    C:\baseball\venv\Scripts\python.exe run_full_suite.py

Same `run_full_suite.py` as before (see the earlier section of this file); the only
change from that recipe is the PATH prepend, which the runner's
`ENV = dict(os.environ, ...)` inherits into every child.

### Pass count

    before (a99bc6e, no tesseract, no fixtures)   284 attempted, 213 PASS / 71 FAIL / 0 TIMEOUT / 0 ERROR, 7 excluded
    after tesseract + fixtures (204bb5b)          285 attempted, 249 PASS / 35 FAIL / 1 TIMEOUT / 0 ERROR, 7 excluded
    after + places_backup (204bb5b, final)        285 attempted, 249 PASS / 35 FAIL / 1 TIMEOUT / 0 ERROR, 7 excluded

The count did not move between the last two runs: `test_reference_pose_flag.py`
fixed (9 FAIL -> 0), but `test_minigame/test_result_commit_evidence.py` — which
PASSED in the run before it — FAILED in the final run with nothing relevant changed
between them. Reran it three times standalone: **FAIL, PASS, FAIL** — a genuine
flake, not caused by tesseract or the fixtures. All five failing checks are case
"(G)", about a stash/timestamp (`ns`) match, e.g. `"CONTROL: A's own ns does not
match the (now B) stash"`. Not investigated further; flag it as a pre-existing
timing-sensitive test on this platform, not a fixture gap.

### Remaining failures, by cause (35 FAIL + 1 TIMEOUT, HEAD 204bb5b)

**Environmental/by-design, no code change indicated (13 files):** no C++ toolchain
or `chiaki-ng-src` (`test_framedump_cpp`, `test_injectinput_cpp`,
`test_button_bits_match_keymap`, `test_keymap_matches_chiaki`); not a git checkout
(`test_affected_tests`, `test_state_files_are_real`, `test_every_tracked_file_parses`);
the `fcntl` shim doesn't cover `os.O_NONBLOCK`/`os.mkfifo`
(`test_analog_replay`, `test_injected_input`, `test_fifo_open_bound`); genuinely
Unix/macOS-only (`test_no_real_input_under_test_run`, `test_focus_protection`,
`test_turn_control` — confirmed by rerun: `frontmost really is chiaki but has_focus
said False`, the macOS Quartz focus check).

**Windows-specific, reproducible, one-line fix each, NOT applied per this session's
brief (10 files):**

    FOOTGUN 5 (file-handle lock)   test_reload_wallet_guard, test_readable_hand_gate,
                                   test_reveal_frame_kept, test_reveal_kind_capture
      Windows locks an open file handle against rename/delete/reopen; POSIX allows
      it. `PermissionError: [WinError 32] ... being used by another process`. Fix:
      close the handle before rotating/deleting that path.

    FOOTGUN 6 (mss headless)       test_decisions, test_orchestrator_diagnostics,
                                   test_should_redraw_incomplete, test_pause_money_local
      `mss.exception.ScreenShotError: ... BitBlt` — no attached interactive desktop
      over SSH. `test_pause_money_local` confirmed by rerun:
      `FAIL expected PaidModelDisabled, got OSError('screen grab failed')` — the
      code reaches a real capture call before the guard under test. Fix: stub the
      capture call in these tests.

    FOOTGUN 7 (cp1252 default encoding)   test_probe_select_budget, test_tactics_select_fallback
      `open(path)` with no `encoding=` defaults to the Windows locale codepage, not
      UTF-8; an em-dash in the mutation anchor decodes to garbage and the substring
      search finds 0 matches instead of 1. Fix: `open(path, encoding="utf-8")`.

    hardcoded Unix /tmp path        test_result_ocr_whole_word, test_frame_dump
      A forward-slash `/tmp/...` literal survives string-concat with a Windows path
      and resolves nowhere. Fix: `tempfile.gettempdir()`.

    path-separator bug              test_goal_leg_frames
      Looks for a `"success/"` substring that Windows `os.path.join` never produces.
      Fix: compare path components, not a substring.

    no TIMEOUT_PL wrapper           test_suite_timeout_kills
      Exercises run_tests.sh's perl SIGKILL one-liner, no Windows equivalent.

    Windows permission semantics    test_atomic_results
      A simulated "write cannot happen" (POSIX chmod) doesn't reproduce the same way.

    FOOTGUN 8 (two-phase test)      test_no_side_effects  (TIMEOUT, 300.1s both runs)
      Needs run_tests.sh's own `--snapshot`/`--check` two-phase call; its bare
      self-contained mode re-executes the whole suite as children and inherits
      every failure above. A runner-design gap, not a defect in the guard.

**Real content differences — Windows tesseract 5.4.0 (`batch` backend, no
tesserocr) reads differently than whatever produced the Mac's reference numbers (6
files, none investigated past the point of confirming it's not a missing fixture):**

    test_ocr_word_mode.py                 architecture test expects the in-process
                                          tesserocr reader; batch backend spawns a
                                          process per call and its handle cache
                                          shows cross-call PSM contamination that
                                          cannot exist with tesserocr
    test_ocr_glyphs.py                    18/208 glyphs disagree between the "slow"
                                          and "fast" paths (backend=batch)
    test_transition_screens_recognised.py 4 FAILED, stalls on "Unrecognized screen"
    test_at_table_ocr_path.py             test_the_top_route_negatives_stay_rejected:
                                          OCR reads 0 words where the fixture needs >=1
    test_compass_accuracy.py              "with both guards off, all 3 wrong bearings
                                          come back" -- only 2 of 3 reproduce under
                                          this tesseract build
    test_landmarks.py                     2 fails: at_baseball_table says False on a
                                          real prompt frame; sees_lb_building confirms
                                          only 4/9 shop-front frames (floor 5)

### Two new PowerShell STDIN footguns found this session

**Running a `.ps1` file over ssh is blocked by execution policy.**
`powershell -File C:\baseball\script.ps1` over ssh fails with `UnauthorizedAccess:
running scripts is disabled on this system`. The existing STDIN pattern
(`cat script | ssh ... 'powershell -Command -'`) is not just a quoting convenience,
it is the only way in — `-File` never worked here at all.

**A multi-line `$x = @(...)` array literal over STDIN silently produces ZERO
output**, reproducing the 2026-09-21 session's finding exactly (see above) — hit
again this session, independently, before finding the existing note. Collapse to
one line: `$x = @("a", "b", "c")`. Cheap check before trusting an empty STDIN
result: does the script contain a multi-line `@(`.

### Answer to "can Snoopy now run the pre-cycle suite"

**Improved from 213/284 (75%) to 249/285 (87%), and every remaining gap is
environmental, a Windows-specific one-line fix, a runner-design gap, or an
OCR-engine version difference — none is Snoopy's Python disagreeing with the Mac's
on project logic.** Cannot run without further work: the 4 file-handle-lock tests,
the 4 mss-headless tests, the 2 cp1252 tests, the 2 hardcoded-/tmp tests, the
path-separator test, `test_suite_timeout_kills`, `test_atomic_results`,
`test_no_side_effects` (needs the two-phase call ported), the 4 C++-toolchain tests
(need `chiaki-ng-src/`, gitignored), the 3 git-checkout tests (repo copy is not a
`.git` checkout), the 3 Unix/macOS-only tests, and the 3 `fcntl`-shim-gap tests. The
6 OCR-difference tests would need either a Windows tesserocr wheel (none exists) or
per-platform tolerance in those tests. `test_result_commit_evidence.py` flaked
2/3 runs for an apparently unrelated timing reason and needs its own investigation.
