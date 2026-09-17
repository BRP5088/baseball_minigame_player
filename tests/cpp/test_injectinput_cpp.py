"""Compile and run tests/cpp/test_injectinput.cpp, and check that the patch it
tests is the patch the application actually builds.

WHY THIS FILE EXISTS (OPEN-11). tests/cpp/ held a C++ check of the injector's
timed hold that ran only if somebody remembered a clang++ line sitting in a
comment. A check that runs when remembered is a check that does not run: it is
the same class as the four bugs in CLAUDE.md 10.1 where the code did nothing and
doing nothing looked exactly like working. run_tests.sh discovers tests as
tests/**/test_*.py, so being a .py file IS the wiring — no special case in the
runner, no second list to keep in sync, and the runner's own per-test SIGKILL
ceiling and live progress line apply here like everywhere else.

WHAT IT GUARDS THAT THE C++ CANNOT GUARD ITSELF.

The C++ test compiles chiaki-patch/injectinput.cpp. The application builds
chiaki-ng-src/gui/src/injectinput.cpp. Those are two files on disk and NOTHING
kept them equal — so the checks could go on passing against a copy that had
drifted from the code actually running on the rig, and both halves would look
healthy. That is the documented failure mode of this whole subsystem: of the
patch's five edits, two fail SILENTLY, and one of them is a CMakeLists line,
because sources there are LISTED and not globbed. A patch that fails quietly is
how this project lost a day.

So every file chiaki-patch/ carries is compared byte-for-byte against its
counterpart in the build tree, and a difference is a FAILURE naming both paths.

WHAT IT REFUSES TO DO QUIETLY. It never skips. No clang++, no build tree, a
compile error, a binary that prints nothing, a timing sample that could not be
taken — each is a FAIL with the reason, because a skip that reads as a pass is
the exact shape this project keeps getting caught by.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + detail) if detail else ""))
    if not cond:
        FAILS.append(name)


def die(name, detail):
    """A failure that makes everything after it meaningless."""
    check(name, False, detail)
    print("\n%d FAILED" % len(FAILS))
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. The toolchain. FAIL, never skip.
# ---------------------------------------------------------------------------
# clang++ ships with the Xcode command line tools, which this project already
# requires — chiaki-ng is built from source here. Treating its absence as a skip
# would mean the injector's only automated check silently stopped running while
# the suite went on printing "all green", which is precisely OPEN-11 again one
# level down.
CXX = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
if not CXX:
    die("a C++ compiler is available",
        "no clang++ or g++ on PATH. This is NOT a skip: without it the "
        "injector's timed-hold checks do not run at all. Install the Xcode "
        "command line tools (xcode-select --install), or set CXX.")
check("a C++ compiler is available", True, CXX)

# ---------------------------------------------------------------------------
# 2. The patch on disk must be the patch that gets built.
# ---------------------------------------------------------------------------
# chiaki-patch/<x> -> chiaki-ng-src/<y>. The two new files land in gui/src/;
# the three edited ones replace their upstream originals in place.
#
# Keeping this list beside the README's own table is deliberate: the README is
# prose and cannot fail. If a sixth file joins the patch, it belongs here too,
# and the check below refuses to run against an empty or shrunken list so that
# deleting a row cannot silently disable the guard.
PATCH_FILES = [
    ("injectinput.cpp", "gui/src/injectinput.cpp"),
    ("injectinput.h", "gui/src/injectinput.h"),
    ("streamsession.cpp", "gui/src/streamsession.cpp"),
    ("gui/CMakeLists.txt", "gui/CMakeLists.txt"),
    ("gui/src/main.cpp", "gui/src/main.cpp"),
    # THE FRAME DUMP (2026-09-08). chiaki writes its decoded frames to a
    # memory-mapped file so the Python side stops capturing the screen -- a
    # macOS Space switch takes chiaki's window off the window list and killed
    # six walks in thirty-five minutes. Same five-edit shape as the injector,
    # and the same two silent ones: gui/CMakeLists.txt (sources are LISTED)
    # and the FrameDumpStart() call in main.cpp.
    ("framedump.cpp", "gui/src/framedump.cpp"),
    ("framedump.h", "gui/src/framedump.h"),
    # qmlbackend.cpp is patched for the FIRST time here. It is the ONLY caller
    # of chiaki_ffmpeg_decoder_pull_frame, which CONSUMES from the codec, so it
    # is the one place a decoded frame can be copied without taking it away
    # from the renderer -- streamsession.cpp only emits a signal.
    ("gui/src/qmlbackend.cpp", "gui/src/qmlbackend.cpp"),
    # THE PRESS INSTRUMENTATION (2026-09-17), and it is a MEASURING TOOL rather
    # than a feature -- it is what proved the console receives about one press in
    # six and declines to act on it, while NOTHING we send is lost. Four
    # hypotheses died to that log: stale frames fooling the cursor reader,
    # chiaki's isAutoRepeat, its edge-collapse dedup, and a null CGEventSource.
    #
    # feedbacksender.c is the FIRST file patched outside gui/. It logs every
    # button EDGE chiaki actually transmits; streamsession.cpp logs every key its
    # Qt handler accepts or discards, and the pair localises a lost press to a
    # boundary instead of leaving it a mystery.
    #
    # main.cpp's setvbuf is the reason any of it can be believed. The log is
    # chiaki's stdout redirected to a file, so libc block-buffered it: 3 seconds
    # and 6 presses once produced ZERO bytes, and a run read that silence as "no
    # input reached chiaki" -- a confident wrong conclusion about a bug that did
    # not exist. Two measurements were thrown away to that before it was fixed.
    ("lib/src/feedbacksender.c", "lib/src/feedbacksender.c"),
]

PATCH_DIR = os.path.join(_ROOT, "chiaki-patch")
SRC_DIR = os.path.join(_ROOT, "chiaki-ng-src")

# chiaki-ng-src/ is gitignored — it is a checkout of upstream with the patch on
# top, and it is where the headers this test compiles against live. Without it
# there is nothing to compile and nothing to compare, so this is a hard failure
# rather than a skip: an unverifiable claim is not a passing one.
if not os.path.isdir(SRC_DIR):
    die("the chiaki-ng build tree is present",
        "%s does not exist. The C++ test cannot compile (injectinput.h includes "
        "<chiaki/controller.h> from chiaki-ng-src/lib/include) and the patch "
        "cannot be compared against what the application builds. Get it with the "
        "recipe in CLAUDE.md 1: git clone --recursive "
        "https://github.com/streetpea/chiaki-ng.git chiaki-ng-src" % SRC_DIR)
check("the chiaki-ng build tree is present", True)

# A GUARD ON THE GUARD, BY COVERAGE RATHER THAN BY COUNT.
#
# If PATCH_FILES were emptied or trimmed, every comparison below would vacuously
# succeed and this file would report a clean patch while checking nothing
# (CLAUDE.md 10.12). The obvious defence is a floor on len(PATCH_FILES) — and
# that is what this used to be, and it is not enough. Demonstrated 2026-09-06:
# REPLACING the gui/src/main.cpp row with a second copy of the injectinput.h row
# keeps the count at five, leaves main.cpp compared against nothing, and the
# whole run still prints "all green" at exit 0. A near-duplicate ("./injectinput.h")
# defeats a len(set(...)) floor the same way, because it is a distinct tuple
# naming the same file.
#
# So the assertion is COVERAGE: the patch-side paths listed here must be exactly
# the files that actually exist in chiaki-patch/. A row that is deleted,
# duplicated, near-duplicated, or renamed leaves some real file unlisted and
# fails here by name; a new patched file added to the directory and forgotten
# fails here too, which the old floor could never catch.
_listed = set()
for _rp, _rs in PATCH_FILES:
    _listed.add(os.path.normpath(_rp))

_on_disk = set()
for _dirpath, _dirnames, _filenames in os.walk(PATCH_DIR):
    for _fn in _filenames:
        _rel = os.path.relpath(os.path.join(_dirpath, _fn), PATCH_DIR)
        # README.md documents the patch; it is not part of it.
        if os.path.normpath(_rel) == "README.md":
            continue
        _on_disk.add(os.path.normpath(_rel))

_unlisted = sorted(_on_disk - _listed)
_phantom = sorted(_listed - _on_disk)
check("the divergence check covers every file in chiaki-patch/",
      not _unlisted and not _phantom,
      ("%d listed, %d on disk" % (len(_listed), len(_on_disk)))
      + ("; NOT COMPARED: %s" % ", ".join(_unlisted) if _unlisted else "")
      + ("; LISTED BUT ABSENT: %s" % ", ".join(_phantom) if _phantom else ""))

# The count floor is kept as well. Coverage alone would be satisfied by an empty
# chiaki-patch/ and an empty list. Five was the injector patch's own documented
# size (five edits across three files, plus its two new files); the frame dump
# added three more files, so the floor is eight. IT IS A FLOOR, NOT THE EXACT
# COUNT: the exact count would turn every future patched file into a failure
# here instead of at the coverage check above, which names the file.
check("the divergence check has files to compare", len(_listed) >= 8,
      "%d distinct patch-side paths" % len(_listed))

diverged, missing = [], []
for rel_patch, rel_src in PATCH_FILES:
    p = os.path.join(PATCH_DIR, rel_patch)
    s = os.path.join(SRC_DIR, rel_src)
    if not os.path.isfile(p):
        missing.append("chiaki-patch/%s is missing" % rel_patch)
        continue
    if not os.path.isfile(s):
        missing.append("chiaki-ng-src/%s is missing" % rel_src)
        continue
    with open(p, "rb") as fh:
        a = fh.read()
    with open(s, "rb") as fh:
        b = fh.read()
    if a != b:
        diverged.append("chiaki-patch/%s (%d bytes) != chiaki-ng-src/%s (%d bytes)"
                        % (rel_patch, len(a), rel_src, len(b)))

for m in missing:
    print("    " + m)
check("every patched file exists on both sides", not missing)

for d in diverged:
    print("    " + d)
    print("      `cd chiaki-ng-src && git diff` is the authority (chiaki-patch/"
          "README.md). Whichever side is right, copy it over the other — the "
          "tests below are only meaningful about the rig if they compile the "
          "same source the application does.")
check("chiaki-patch matches the sources the application builds", not diverged)

# ---------------------------------------------------------------------------
# 3. Compile.
# ---------------------------------------------------------------------------
BUILD = tempfile.mkdtemp(prefix="injectinput_test_")
BIN = os.path.join(BUILD, "test_injectinput")
CMD = [CXX, "-std=c++17", "-Wall",
       "-I" + PATCH_DIR,
       "-I" + os.path.join(SRC_DIR, "lib", "include"),
       os.path.join(_ROOT, "tests", "cpp", "test_injectinput.cpp"),
       os.path.join(PATCH_DIR, "injectinput.cpp"),
       "-o", BIN]
try:
    build = subprocess.run(CMD, cwd=_ROOT, capture_output=True, text=True, timeout=180)
except subprocess.TimeoutExpired:
    die("the C++ check compiles", "clang++ did not finish in 180s")
except OSError as exc:
    # CXX pointing at something unlaunchable used to raise here and print a
    # traceback. The run still failed, so nothing passed wrongly — but a suite
    # whose whole point is that every failure names its own reason should not
    # hand back a stack trace for a one-line cause.
    die("the C++ check compiles", "cannot run the compiler %r: %s" % (CXX, exc))

if build.returncode != 0 or not os.path.exists(BIN):
    for line in (build.stderr or build.stdout or "").splitlines()[:25]:
        print("    " + line)
    die("the C++ check compiles", "exit %d from: %s" % (build.returncode, " ".join(CMD)))
check("the C++ check compiles", True)
# Warnings are printed but do not fail: the point of this file is the injector's
# behaviour, and a compiler upgrade should not be able to fail the rig's checks.
for line in (build.stderr or "").splitlines()[:15]:
    print("    warn: " + line)

# ---------------------------------------------------------------------------
# 4. Run it.
# ---------------------------------------------------------------------------
# The FIFO is put inside this run's own scratch directory, so it is removed with
# that directory however the run ends — including run_tests.sh's SIGKILL, which
# no handler can catch. It also keeps parallel copies apart under JOBS=4, and it
# keeps the test traffic a long way from /tmp/chiaki_input, the live pipe a
# running chiaki reads.
env = dict(os.environ)
env["CHIAKI_INJECT_INPUT"] = os.path.join(BUILD, "inject.fifo")
env["BASEBALL_TEST_RUN"] = "1"
# run_tests.sh already enforces a SIGKILL ceiling from a parent process; this
# inner timeout only stops a wedged binary from eating the whole budget and
# hiding every other result here.
try:
    run = subprocess.run([BIN], capture_output=True, text=True, timeout=120, env=env)
except subprocess.TimeoutExpired:
    shutil.rmtree(BUILD, ignore_errors=True)
    die("the C++ check finishes", "the binary was still running after 120s")

out = run.stdout or ""
for line in out.splitlines():
    print("    " + line)
for line in (run.stderr or "").splitlines():
    print("    [stderr] " + line)
shutil.rmtree(BUILD, ignore_errors=True)

# ---------------------------------------------------------------------------
# 5. Score it — and refuse to score an empty run.
# ---------------------------------------------------------------------------
# A binary that crashed on its first line, or one whose output was truncated,
# would otherwise leave zero FAIL lines and read exactly like a clean pass. The
# SUMMARY line the binary prints last is what proves the run reached the end,
# and cross-checking it against the parsed lines is what proves nothing was lost
# in between.
rows = []
for line in out.splitlines():
    m = re.match(r"^RESULT\s+(PASS|FAIL|INCONC)\s+(correctness|timing)\s*\|", line)
    if m:
        parts = [p.strip() for p in line.split("|")]
        rows.append((m.group(1), m.group(2), parts[1] if len(parts) > 1 else "?",
                     parts[2] if len(parts) > 2 else ""))

m = re.search(r"^SUMMARY pass=(\d+) fail=(\d+) inconc=(\d+) total=(\d+)$",
              out, re.M)
if not m:
    die("the C++ check ran to completion",
        "no SUMMARY line: the binary exited %d after printing %d result line(s). "
        "Zero failures here would mean nothing." % (run.returncode, len(rows)))
n_pass, n_fail, n_inconc, n_total = (int(x) for x in m.groups())
check("the C++ check ran to completion", True,
      "%d checks" % n_total)
check("every result line was captured", len(rows) == n_total,
      "parsed %d, binary counted %d" % (len(rows), n_total))

# A floor, not the exact count: the exact count is what the .cpp happens to emit
# today and pinning it would turn every added check into a failure. The floor is
# there so that a binary rewritten down to two checks cannot pass as a full run.
check("the C++ check is not a stub", n_total >= 12, "%d checks" % n_total)

correctness = [r for r in rows if r[1] == "correctness"]
timing = [r for r in rows if r[1] == "timing"]
check("it has correctness checks, not only timing ones", len(correctness) >= 8,
      "%d correctness, %d timing" % (len(correctness), len(timing)))

# CORRECTNESS AND TIMING ARE SCORED SEPARATELY, ON PURPOSE.
#
# The old version's "still held" assertions had 20-70ms of margin against
# 150-200ms deadlines, so on a loaded machine a real regression and a busy CPU
# produced the same FAIL — and the honest reading of either was a shrug. The
# .cpp now bounds every timing assertion by measured clocks, so load can only
# make one INCONCLUSIVE. Reporting the two classes apart is the other half:
# whatever the machine was doing, a correctness failure below is a regression.
bad_correct = [r for r in correctness if r[0] != "PASS"]
for r in bad_correct:
    print("    %s  %s  -- %s" % (r[0], r[2], r[3]))
check("every CORRECTNESS check passed", not bad_correct,
      "%d of %d failed. These do not depend on timing: load cannot cause them."
      % (len(bad_correct), len(correctness)) if bad_correct else "")

bad_timing = [r for r in timing if r[0] == "FAIL"]
for r in bad_timing:
    print("    %s  %s  -- %s" % (r[0], r[2], r[3]))
check("every TIMING check passed", not bad_timing,
      "%d of %d failed. A timing check only fails when the injector released "
      "or held at a moment this process MEASURED, so this is a regression too, "
      "not a slow machine." % (len(bad_timing), len(timing)) if bad_timing else "")

# INCONCLUSIVE IS NOT A PASS. It means a sample could not be taken in time, so
# that check measured nothing — and a check that measures nothing while
# reporting green is the failure this whole file exists to prevent.
#
# IT DOES NOT NAME A CAUSE IT CANNOT SEE. "Too loaded" is only one explanation:
# a broken injector can also starve a timing check of its sample, because the
# behaviour it was waiting for never happens. Mutation-tested — reintroducing
# the `clear` bug produced one correctness FAIL and one INCONCLUSIVE, and an
# unconditional "this machine was too loaded" would have been a confident wrong
# diagnosis printed right underneath the real one. So the correctness verdict,
# which is load-proof, decides which sentence gets printed.
inconclusive = [r for r in rows if r[0] == "INCONC"]
for r in inconclusive:
    print("    INCONC  %s  -- %s" % (r[2], r[3]))
if bad_correct:
    why = ("%d timing check(s) took no sample. DO NOT read that as a load "
           "problem: %d correctness check(s) failed above, and a broken "
           "injector starves a timing check of its sample by never doing the "
           "thing it is waiting for. Fix the correctness failures first, then "
           "re-run." % (len(inconclusive), len(bad_correct)))
else:
    # DO NOT ASSERT THE MACHINE HERE EITHER. The correctness checks passing
    # narrows the field but does not close it: mutation-tested 2026-09-05, making
    # `clear` set active = false — THE regression the release window exists to
    # prevent — produces exactly this state, one INCONCLUSIVE with every
    # correctness check green, because no correctness check in the .cpp covers
    # it. An unconditional "points at the machine rather than the code" would
    # therefore print a confident wrong diagnosis of a real bug, which is the
    # same mistake this branch's sibling above was already fixed for.
    why = ("%d timing check(s) could not take a sample. Every correctness check "
           "passed, so a loaded machine is the LIKELIER cause — but it is not "
           "the only one: a regression no correctness check here covers can also "
           "starve a timing check of its sample. Re-run on a quiet machine "
           "(CLAUDE.md 10.13: never run heavy sweeps and this at the same time); "
           "if it survives that, read the INCONC detail above, which names what "
           "else fits." % len(inconclusive))
check("every TIMING check could actually be sampled", not inconclusive,
      why if inconclusive else "")

# The binary's own exit code, cross-checked against what was parsed. If they
# disagree, one of the two is lying and neither can be trusted.
check("the binary's exit code agrees with its results",
      (run.returncode != 0) == bool(n_fail or n_inconc),
      "exit %d with fail=%d inconc=%d" % (run.returncode, n_fail, n_inconc))

print("\nall green" if not FAILS else "\n%d FAILED" % len(FAILS))
sys.exit(1 if FAILS else 0)
