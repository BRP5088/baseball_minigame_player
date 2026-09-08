"""Mutants for patch51 on the p51 SCRATCH copy. Restore in a finally (10.10a)."""
import os, subprocess, sys, shutil, hashlib
S = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(S, "p51")
PY = "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball/.venv/bin/python"
C = os.path.join(ROOT, "chain_walk.py")
orig = open(C).read()
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()[:12]
MUT = [
 ("gate removed",
  "if (STOP_LOOK_YAW and near_fit and not last_stop\n",
  "if (STOP_LOOK_YAW and near_fit\n"),
 ("gate fires at EVERY stop (<=)",
  "and pi == last_stop_j)\n",
  "and pi <= last_stop_j)\n"),
 ("reason dropped from the marker",
  "                            if last_stop:\n                                looked[\"yaw_skipped\"][\"reason\"] = \"last stop\"\n",
  "                            if False:\n                                looked[\"yaw_skipped\"][\"reason\"] = \"last stop\"\n"),
 ("flag ignored (rule hard on)",
  "last_stop = (STOP_YAW_SKIP_LAST_STOP\n",
  "last_stop = (True\n"),
]
def run():
    for d in ("__pycache__", "tests/routing/__pycache__", "tests/__pycache__"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
    p = subprocess.run([PY, "-B", "-m", "unittest", "tests.routing.test_chain_walk"],
                       cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, BASEBALL_TEST_RUN="1"))
    out = p.stderr
    fails = [l.split()[1] for l in out.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
    return p.returncode, fails
try:
    rc, f = run(); print("baseline rc", rc, f); assert rc == 0
    allc = True
    for name, a, b in MUT:
        assert orig.count(a) == 1, (name, orig.count(a))
        m = orig.replace(a, b)
        open(C, "w").write(m)
        rc, f = run()
        caught = rc != 0
        allc &= caught
        print(("  CAUGHT " if caught else "  SURVIVED") + f" {name} ({len(m)-len(orig):+d} bytes) " + str(f[:3]))
        open(C, "w").write(orig)
finally:
    open(C, "w").write(orig)
    print("restored:", sha(open(C).read()) == sha(orig), "| all caught:", allc)
