"""The .env loader must never override what is already set.

WHY THAT MATTERS HERE
---------------------
run_tests.sh pins PERSONAL_ANTHROPIC_API_KEY to a dummy for every offline
test. If a value in .env could override an already-set variable, .env would
undo that pin and hand the whole suite live credentials.

The per-test `os.environ.setdefault(...)` calls do NOT provide this guarantee
on their own -- setdefault cannot displace a variable the shell already
exported, and this project's shell exports the real key. That is why the pin
lives in run_tests.sh, where it is unconditional.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import atexit
import os
import shutil
import tempfile

import env_loader

fails = []


def fresh(text, preset=None):
    d = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    p = os.path.join(d, ".env")
    open(p, "w").write(text)
    for k in ("ZZ_A", "ZZ_B", "ZZ_QUOTED"):
        os.environ.pop(k, None)
    if preset:
        os.environ.update(preset)
    return p, env_loader.load(p)


# --- the safety property ---------------------------------------------------
p, added = fresh("ZZ_A=from_dotenv\n", preset={"ZZ_A": "from_shell"})
if os.environ["ZZ_A"] != "from_shell":
    fails.append("a .env value OVERRODE one already in the environment — this "
                 "is exactly how a real key would replace a test's dummy and "
                 "put the offline suite on live credentials")
if "ZZ_A" in added:
    fails.append("reported setting a variable it did not set")

# --- ordinary loading ------------------------------------------------------
p, added = fresh("ZZ_A=hello\n# a comment\n\nZZ_B = spaced \n")
if os.environ.get("ZZ_A") != "hello" or os.environ.get("ZZ_B") != "spaced":
    fails.append(f"failed to load plain values (got {os.environ.get('ZZ_A')!r}, "
                 f"{os.environ.get('ZZ_B')!r}) — comments/blank lines/space "
                 "around '=' are all normal in a .env")

# --- quotes, because people copy keys in with them -------------------------
p, added = fresh('ZZ_QUOTED="sk-ant-123"\n')
if os.environ.get("ZZ_QUOTED") != "sk-ant-123":
    fails.append(f"quotes were not stripped ({os.environ.get('ZZ_QUOTED')!r}) — "
                 "the key would be sent with literal quote characters")

# --- a missing file is normal, not an error --------------------------------
try:
    if env_loader.load("/nonexistent/.env") != []:
        fails.append("a missing .env returned something other than 'nothing set'")
except Exception as e:
    fails.append(f"a missing .env raised {type(e).__name__} — the project must "
                 "still run with the key coming from the shell, as it did "
                 "before .env existed")

for k in ("ZZ_A", "ZZ_B", "ZZ_QUOTED"):
    os.environ.pop(k, None)

if fails:
    for f in fails:
        print("  FAIL:", f)
    raise SystemExit(1)
print("  .env loads values, strips quotes, tolerates a missing file, and never "
      "overrides the shell (which is what keeps the test suite offline)")
