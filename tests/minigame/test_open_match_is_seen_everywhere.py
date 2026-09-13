"""THE $50 GUARD WAS ONLY EVER CHECKED ON ONE FILE, AND NOT THE RIGHT ONE.

`match_in_progress` is what stops a run pressing `start_match` believing the $50 was
already paid -- the state where the money leaves the in-game wallet, `balance` is never
debited and `max_spend` cannot stop it (CLAUDE.md). preflight escalated it from warn to
bad in 2026-09-04 for exactly that reason.

It read `sys.argv[1]`, defaulting to `progress.json`. THIS PROJECT KEEPS TWO PROGRESS FILES
ON PURPOSE -- "recent training uses progress_testing.json" -- so running `preflight.py`
with no argument, which is how it is actually run, reported READY while
progress_testing.json held the flag. A guard that cannot fire the way the tool is used.

Verified live 2026-09-13: bare `preflight.py` said READY; `preflight.py
progress_testing.json` said FAIL, on the same tree, at the same moment.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, json, ast, tempfile, shutil
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator as o

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


tmp = tempfile.mkdtemp(prefix=f"openmatch_{os.getpid()}_")
try:
    def write(name, **kw):
        with open(os.path.join(tmp, name), "w") as f:
            json.dump(dict({"wins": 0, "losses": 0, "draws": 0, "balance": 200}, **kw), f)

    print("1. a flag in a NON-default file is still found")
    write("progress.json", match_in_progress=False)
    write("progress_testing.json", match_in_progress=True, bans_done_this_match=False)
    found = o.open_match_files(tmp)
    check([f for f, _ in found] == ["progress_testing.json"],
          f"the testing file is reported even though progress.json is clean ({found})")
    check(found and found[0][1] is False, f"and its bans flag comes with it ({found})")

    print("2. CONTROL: no flag anywhere means nothing is reported")
    write("progress_testing.json", match_in_progress=False)
    check(o.open_match_files(tmp) == [],
          "a clean tree reports nothing — otherwise section 1 passes by always answering")

    print("3. every file is scanned, not just the two known names")
    write("progress_taylere.json", match_in_progress=True, bans_done_this_match=True)
    found = o.open_match_files(tmp)
    check([f for f, _ in found] == ["progress_taylere.json"],
          f"a third progress file is scanned too ({found})")
    check(found and found[0][1] is True, "and a True bans flag is carried through")

    print("4. an unreadable file is not a CLAIM that a match is open")
    with open(os.path.join(tmp, "progress_broken.json"), "w") as f:
        f.write("{not json")
    found = o.open_match_files(tmp)
    check([f for f, _ in found] == ["progress_taylere.json"],
          f"corrupt JSON is skipped, not treated as a flag ({found})")

    print("5. preflight consults it, and BLOCKS rather than warns")
    src = open(os.path.join(_ROOT, "preflight.py")).read()
    check("open_match_files" in src, "preflight calls open_match_files")
    tree = ast.parse(src)
    # the call must be followed by bad(), not warn(): a warning does not block a run, which
    # is the exact mistake this guard was fixed for once already, in 2026-09-04
    seg = src[src.index("open_match_files"):]
    seg = seg[:seg.index("print(") if "print(" in seg else len(seg)]
    check("bad(" in seg and "warn(" not in seg.split("bad(")[0],
          "and the verdict on an open match is bad(), not warn() — a warning does not "
          "block, which is the mistake this guard already had once")

    print("6. the real tree is scanned by the same call")
    real = o.open_match_files(_ROOT)
    check(isinstance(real, list),
          f"it runs against the project as well ({[f for f, _ in real] or 'nothing open'})")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
