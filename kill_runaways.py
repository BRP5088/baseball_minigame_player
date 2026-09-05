"""Kill runaway processes from THIS project. Never touches other Python.

    python3 kill_runaways.py            # report only
    python3 kill_runaways.py --kill     # actually kill

WHY THIS EXISTS
---------------
On 2026-09-02 a test process from the PREVIOUS session had been spinning for
1 day 7 hours — 1867 minutes of CPU, a full core — held open by
tests/test_no_side_effects.py, which spawned it with no timeout. It slowed the
whole machine and, with it, the game stream this project depends on.

SCOPED ON PURPOSE. The user runs Python for work, so this only ever matches
processes whose command line contains this project's directory, and only those
over a CPU-time threshold. It will not touch anything else, and by default it
reports rather than kills.
"""

import os
import subprocess
import sys

PROJECT = os.path.dirname(os.path.abspath(__file__))
# A legitimate run here is minutes. Anything past this is stuck, not slow.
CPU_MINUTES = 20.0


def _cpu_minutes(t):
    """ps TIME is [dd-]hh:mm:ss or mm:ss.ss — return minutes."""
    days = 0
    if "-" in t:
        d, t = t.split("-", 1)
        days = int(d)
    bits = [float(x) for x in t.split(":")]
    while len(bits) < 3:
        bits.insert(0, 0.0)
        h, m, sec = bits
    h, m, sec = bits[-3], bits[-2], bits[-1]
    return days * 1440 + h * 60 + m + sec / 60.0


def find(cpu_minutes=CPU_MINUTES):
    """[(pid, cpu_minutes, command)] for this project's runaway processes."""
    out = subprocess.run(["ps", "-eo", "pid,time,command"],
                         capture_output=True, text=True).stdout
    hits = []
    me = os.getpid()
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, t, cmd = parts
        # SCOPING: this project only, and python only.
        if PROJECT not in cmd or "ython" not in cmd:
            continue
        if "kill_runaways" in cmd or int(pid) == me:
            continue
        try:
            mins = _cpu_minutes(t)
        except Exception:
            continue
        if mins >= cpu_minutes:
            hits.append((int(pid), mins, cmd))
    return hits


def main(do_kill=False):
    hits = find()
    if not hits:
        print(f"no runaway processes from {PROJECT}")
        return 0
    for pid, mins, cmd in hits:
        short = cmd.split(PROJECT)[-1].strip() or cmd[-60:]
        print(f"  pid {pid:6}  {mins:8.1f} min CPU  {short[:70]}")
        if do_kill:
            try:
                os.kill(pid, 9)
                print(f"    killed {pid}")
            except ProcessLookupError:
                print(f"    {pid} already gone")
            except PermissionError:
                print(f"    {pid} not ours to kill — left alone")
    if not do_kill:
        print(f"\n{len(hits)} runaway(s). Re-run with --kill to stop them.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--kill" in sys.argv))
