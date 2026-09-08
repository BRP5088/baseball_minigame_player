"""Compile and run the frame-dump WRITER's own checks. OFFLINE.

WHY THIS FILE EXISTS AT ALL. The frame dump shipped with four mutants against
it, and all four mutated `frame_dump.py` -- the READER. The writer's throttle,
its busy guard, its seqlock write ordering, its format refusals and the packed
plane layout that the reader now trusts were verified by READING framedump.cpp
and by fixtures the reader's own test wrote by hand. Two hand-written
implementations agreeing with each other says nothing about the C++ that
actually produces the bytes on the rig.

So this drives the real `chiaki-patch/framedump.cpp` with real AVFrames and
reads the mapping back through a second, independent parse of the layout.

IT NEVER SKIPS, and every scenario is a FRESH PROCESS, because FrameDumpStart()
latches on purpose. Absent clang++, absent ffmpeg headers, absent chiaki-ng-src,
a compile error, an empty run, or an INCONCLUSIVE concurrency sample are each a
FAIL that names the fix -- an unverifiable claim is not a passing one, which is
the rule tests/cpp/test_injectinput_cpp.py was written to enforce next door.

MUTANTS CAUGHT (2026-09-08, framedump.cpp restored after each; see
agent_progress/closed-loop/frame_dump/progress.md for the exact edits):
  * the throttle's `return` deleted        -> throttle checks FAIL
  * seq_before stored AFTER the pixel copy -> the torn-frame check FAILS
  * av_image_copy_to_buffer align 1 -> 32  -> the PACKED stride checks FAIL
  * the oversize refusal deleted           -> the "never truncated" check FAILS
  * the busy guard's compare_exchange made
    unconditional (always "held")          -> the torn-frame check FAILS
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ok = True


def check(label, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + label + (("  -- " + detail) if detail else ""))
    if not cond:
        ok = False


def die(label, detail):
    check(label, False, detail)
    print("\nFAILED")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. The toolchain. FAIL, never skip.
# ---------------------------------------------------------------------------
CXX = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("g++")
if not CXX:
    die("a C++ compiler is available",
        "no clang++ or g++ on PATH. This is NOT a skip: without it the frame "
        "dump's writer has no automated check at all. Install the Xcode command "
        "line tools (xcode-select --install), or set CXX.")
check("a C++ compiler is available", True, CXX)

PATCH_DIR = os.path.join(_ROOT, "chiaki-patch")
SRC_DIR = os.path.join(_ROOT, "chiaki-ng-src")
FD_CPP = os.path.join(PATCH_DIR, "framedump.cpp")

if not os.path.isfile(FD_CPP):
    die("chiaki-patch/framedump.cpp is present",
        "%s is missing. The frame-dump patch is one of the five-edit shapes "
        "CLAUDE.md 1 describes; without this file there is nothing to test."
        % FD_CPP)
check("chiaki-patch/framedump.cpp is present", True)

# libavutil, from the same formula CLAUDE.md 1's build recipe uses. Not a skip
# for the same reason as the compiler: chiaki-ng is built from source on this
# machine, so ffmpeg@7 is already a hard requirement of the project.
FFMPEG = os.environ.get("FFMPEG_PREFIX") or "/opt/homebrew/opt/ffmpeg@7"
FF_INC = os.path.join(FFMPEG, "include")
FF_LIB = os.path.join(FFMPEG, "lib")
if not os.path.isdir(os.path.join(FF_INC, "libavutil")):
    die("libavutil headers are available",
        "%s/libavutil does not exist. framedump.cpp is compiled against "
        "libavutil (av_frame_*, av_image_copy_to_buffer), the same library the "
        "application links. Set FFMPEG_PREFIX, or `brew install ffmpeg@7` per "
        "CLAUDE.md 1." % FF_INC)
check("libavutil headers are available", True, FF_INC)

# The test compiles chiaki-patch/framedump.cpp -- the persistent copy. That is
# only meaningful if it is still the file the application builds, which is
# tests/cpp/test_injectinput_cpp.py's job; this is the one line that keeps this
# file honest if that one is ever removed.
_SRC_COPY = os.path.join(SRC_DIR, "gui", "src", "framedump.cpp")
if os.path.isfile(_SRC_COPY):
    with open(FD_CPP, "rb") as fa, open(_SRC_COPY, "rb") as fb:
        _same = fa.read() == fb.read()
    check("the file compiled here is the file the application builds", _same,
          "chiaki-patch/framedump.cpp vs chiaki-ng-src/gui/src/framedump.cpp")
else:
    check("the file compiled here is the file the application builds", False,
          "%s is missing -- chiaki-ng-src/ is gitignored; get it with the recipe "
          "in CLAUDE.md 1" % _SRC_COPY)

# ---------------------------------------------------------------------------
# 2. Compile.
# ---------------------------------------------------------------------------
BUILD = tempfile.mkdtemp(prefix="framedump_test_")
BIN = os.path.join(BUILD, "test_framedump")
CMD = [CXX, "-std=c++17", "-Wall",
       "-I" + PATCH_DIR,
       "-I" + FF_INC,
       os.path.join(_ROOT, "tests", "cpp", "test_framedump.cpp"),
       FD_CPP,
       "-L" + FF_LIB, "-lavutil",
       "-o", BIN]
try:
    build = subprocess.run(CMD, cwd=_ROOT, capture_output=True, text=True, timeout=180)
except subprocess.TimeoutExpired:
    shutil.rmtree(BUILD, ignore_errors=True)
    die("the writer's C++ check compiles", "clang++ did not finish in 180s")
except OSError as exc:
    shutil.rmtree(BUILD, ignore_errors=True)
    die("the writer's C++ check compiles", "cannot run the compiler %r: %s" % (CXX, exc))

if build.returncode != 0 or not os.path.exists(BIN):
    for line in (build.stderr or build.stdout or "").splitlines()[:25]:
        print("    " + line)
    shutil.rmtree(BUILD, ignore_errors=True)
    die("the writer's C++ check compiles",
        "exit %d from: %s" % (build.returncode, " ".join(CMD)))
check("the writer's C++ check compiles", True)
for line in (build.stderr or "").splitlines()[:15]:
    print("    warn: " + line)

# ---------------------------------------------------------------------------
# 3. Run each scenario in its OWN process.
# ---------------------------------------------------------------------------
# FrameDumpStart() latches g_started deliberately, so one process can only ever
# open one mapping. A fresh process per scenario is therefore the only honest
# way to test more than one -- and it means no scenario can pass on state a
# previous one left behind.
#
# The dump files live in this run's own scratch directory, which goes away with
# it however the run ends -- including run_tests.sh's SIGKILL, which no handler
# catches. It also keeps the traffic a long way from /tmp/chiaki_frame.bin, the
# mapping a live chiaki is writing while this runs.
SCENARIOS = ["disabled", "nv12", "i420", "throttle", "refusals", "concurrent"]

env = dict(os.environ)
env["BASEBALL_TEST_RUN"] = "1"
env.pop("CHIAKI_FRAME_DUMP", None)   # each scenario names its own path
env["DYLD_LIBRARY_PATH"] = FF_LIB + ":" + env.get("DYLD_LIBRARY_PATH", "")

rows = []
for name in SCENARIOS:
    dump = os.path.join(BUILD, "dump_%s.bin" % name)
    print("  --- scenario %s ---" % name)
    try:
        run = subprocess.run([BIN, name, dump], capture_output=True, text=True,
                             timeout=180, env=env)
    except subprocess.TimeoutExpired:
        shutil.rmtree(BUILD, ignore_errors=True)
        die("the writer's C++ check finishes",
            "scenario %s was still running after 180s" % name)

    out = run.stdout or ""
    for line in out.splitlines():
        print("    " + line)
    for line in (run.stderr or "").splitlines():
        print("    [stderr] " + line)

    for line in out.splitlines():
        m = re.match(r"^RESULT\s+(PASS|FAIL|INCONC)\s+(correctness|timing)\s*\|", line)
        if m:
            parts = [p.strip() for p in line.split("|")]
            rows.append((name, m.group(1), parts[1] if len(parts) > 1 else "?"))

    # THE SUMMARY LINE IS WHAT PROVES THE RUN REACHED THE END. A binary that
    # crashed on its first check leaves zero FAIL lines and reads exactly like a
    # clean pass -- the shape CLAUDE.md 10.1 catalogues.
    m = re.search(r"^SUMMARY pass=(\d+) fail=(\d+) inconc=(\d+) total=(\d+)$",
                  out, re.M)
    if not m:
        shutil.rmtree(BUILD, ignore_errors=True)
        die("scenario %s ran to completion" % name,
            "no SUMMARY line (exit %d). The binary died partway, so the checks "
            "that did not print cannot be counted as passes." % run.returncode)
    p, f, i, t = (int(x) for x in m.groups())
    counted = sum(1 for r in rows if r[0] == name)
    if counted != t:
        shutil.rmtree(BUILD, ignore_errors=True)
        die("scenario %s: every result line was read" % name,
            "the binary counted %d, this driver parsed %d -- output was lost"
            % (t, counted))
    if t == 0:
        shutil.rmtree(BUILD, ignore_errors=True)
        die("scenario %s asserted something" % name,
            "zero checks ran, which is not a pass")

shutil.rmtree(BUILD, ignore_errors=True)

# ---------------------------------------------------------------------------
# 4. Score.
# ---------------------------------------------------------------------------
# A FLOOR ON THE WORK, so trimming scenarios cannot quietly empty this file.
check("every scenario ran", len({r[0] for r in rows}) == len(SCENARIOS),
      "%d of %d: %s" % (len({r[0] for r in rows}), len(SCENARIOS),
                        ", ".join(sorted({r[0] for r in rows}))))
check("the writer's checks have work to do", len(rows) >= 25,
      "%d result line(s)" % len(rows))

failed = [r for r in rows if r[1] == "FAIL"]
for _s, _v, name in failed:
    print("    FAILED: " + name)
check("the frame-dump writer behaves as framedump.h specifies", not failed,
      "%d failure(s) of %d" % (len(failed), len(rows)))

# INCONCLUSIVE IS NOT A PASS. The concurrency scenario reports it when the
# machine was too loaded to gather a sample, and a run that proved nothing must
# not read as a run that proved something.
inconc = [r for r in rows if r[1] == "INCONC"]
for _s, _v, name in inconc:
    print("    INCONCLUSIVE: " + name)
check("no check was inconclusive", not inconc,
      "%d inconclusive -- re-run on a quieter machine; this is NOT a pass"
      % len(inconc))

print("\nall green" if ok else "\nFAILED")
sys.exit(0 if ok else 1)
