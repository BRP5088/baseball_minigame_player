"""(c) mutants for LEG_TRIM_UNITS_BY_LEG, run on SNOOPY's copy (FOOTGUN 4: newline='' on every write)."""
import hashlib, os, glob, subprocess, sys
P = "graph_walk.py"; T = os.path.join("tests", "routing", "test_leg_trim.py")
orig = open(P, newline="").read(); sha = hashlib.sha256(orig.encode()).hexdigest()
env = {**os.environ, "BASEBALL_TEST_RUN": "1"}
base = subprocess.run([sys.executable, "-B", T], capture_output=True, text=True, env=env)
print("baseline:", "OK" if base.returncode == 0 else "RED\n" + (base.stdout + base.stderr)[-1500:], flush=True)
if base.returncode:
    sys.exit(3)
nl = "\r\n" if "\r\n" in orig else "\n"
MUT = [("A _trimmed returns steps unchanged", "    if not units or units <= 0:" + nl + "        return steps" + nl, "    if True:" + nl + "        return steps" + nl),
       ("B walk_link skips the trim", "    steps = _trimmed(steps, LEG_TRIM_UNITS_BY_LEG.get((a, b), 0.0))" + nl, "    steps = _trimmed(steps, 0.0)" + nl),
       ("C keyed the wrong way round", "LEG_TRIM_UNITS_BY_LEG.get((a, b), 0.0)", "LEG_TRIM_UNITS_BY_LEG.get((b, a), 0.0)")]
def pyc():
    for f in glob.glob(os.path.join("__pycache__", "graph_walk*")):
        os.remove(f)
ok = True
try:
    for name, old, new in MUT:
        n = orig.count(old)
        if n != 1:
            print(f"SKIP {name}: anchor count {n}", flush=True); ok = False; continue
        open(P, "w", newline="").write(orig.replace(old, new)); pyc()
        r = subprocess.run([sys.executable, "-B", T], capture_output=True, text=True, env=env)
        failed = sorted({l.split(" ")[1].split(".")[-1][:48] for l in (r.stdout + r.stderr).splitlines() if l.startswith(("FAIL:", "ERROR:"))})
        ok &= bool(r.returncode)
        print(f"{'CAUGHT' if r.returncode else 'SURVIVED'} {name}: {failed[:2]}", flush=True)
finally:
    open(P, "w", newline="").write(orig); pyc()
    print("restored:", hashlib.sha256(open(P, newline="").read().encode()).hexdigest() == sha, flush=True)
print("MUTANTS DONE", "ALL CAUGHT" if ok else "SOME SURVIVED", flush=True)
