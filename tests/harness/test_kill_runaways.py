"""The runaway killer must never touch Python that is not this project's.

WHY THIS EXISTS
---------------
The user runs Python for work on this machine. A cleanup that matched "python"
broadly would kill their work, which is far worse than the problem it solves.

The problem is real: on 2026-09-02 a test process from the previous session had
been spinning for 1 day 7 hours (1867 minutes of CPU, a full core), slowing the
machine and the game stream with it.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import kill_runaways as kr

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# --- CPU time parsing, the thing that decides whether anything is killed ---
for text, want in (("1867:41.69", 1867.7), ("01-07:10:11", 1870.2),
                   ("0:05.20", 0.087), ("12:34", 12.57), ("2-00:00:00", 2880.0)):
    got = kr._cpu_minutes(text)
    check(abs(got - want) < 1.5,
          f"ps TIME {text!r} parsed as {got:.2f} min, expected ~{want} — this "
          f"number decides what gets killed")

# --- SCOPING: only this project, only python ------------------------------
import subprocess
import types

FAKE = """  PID TIME     COMMAND
  101 2000:00  /usr/bin/python3 /Users/someone/work/etl_job.py
  102 2000:00  /usr/bin/python3 {proj}/tests/test_input_timing.py
  103 0:01.00  /usr/bin/python3 {proj}/go_now.py
  104 2000:00  /usr/bin/node {proj}/whatever.js
  105 2000:00  /usr/bin/python3 /Users/someone/work/{leaf}_lookalike.py
""".format(proj=_ROOT, leaf=os.path.basename(_ROOT))

_real = subprocess.run
subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=FAKE)
try:
    hits = kr.find(cpu_minutes=20.0)
finally:
    subprocess.run = _real

pids = sorted(p for p, _, _ in hits)
check(pids == [102],
      f"matched pids {pids}, expected only [102]. 101 and 105 are the user's "
      f"OWN work Python and must never be touched; 103 is this project's but "
      f"only 1 second of CPU (running normally, not stuck); 104 is not Python.")

# The threshold must actually gate: with a huge threshold, nothing matches.
subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=FAKE)
try:
    none = kr.find(cpu_minutes=10 ** 6)
finally:
    subprocess.run = _real
check(none == [],
      f"a threshold of a million minutes still matched {none} — the CPU-time "
      f"gate is what separates 'stuck' from 'busy'")

# --- Default must be REPORT, not kill -------------------------------------
killed = []
_real_kill = os.kill
os.kill = lambda pid, sig: killed.append(pid)
subprocess.run = lambda *a, **k: types.SimpleNamespace(stdout=FAKE)
try:
    kr.main(do_kill=False)
finally:
    os.kill = _real_kill
    subprocess.run = _real
check(killed == [],
      f"the default run killed {killed}; it must report and leave the decision "
      f"to a deliberate --kill")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  kill_runaways: parses ps CPU time, matches ONLY this project's stuck "
      "python (never the user's work), gates on CPU time, and reports by default")
