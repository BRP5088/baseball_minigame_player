"""Pre-live-run checks. Run this before starting a session.

Every check here corresponds to a failure that is SILENT or near-silent at
runtime — the kind that wastes a whole evening because the loop keeps going and
looks busy. Nothing here touches the game: no keypress, no vision call, no
match. Safe to run any time.

    python3 preflight.py
"""

import json
import os
import subprocess
import sys
import warnings as _warnings

_warnings.filterwarnings("ignore", category=DeprecationWarning)

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-preflight")

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY_COST = 50

problems = []   # blocks the run
advisories = []  # worth knowing, does not block


def ok(msg):
    print(f"  \033[32mPASS\033[0m  {msg}")


def bad(msg, detail=""):
    print(f"  \033[31mFAIL\033[0m  {msg}")
    problems.append(f"{msg}{(' — ' + detail) if detail else ''}")


def warn(msg):
    print(f"  \033[33mWARN\033[0m  {msg}")
    advisories.append(msg)


print("\n--- 1. Screen capture -------------------------------------------")
# The nastiest silent failure: without Screen Recording permission the capture
# returns a window-less desktop, so read_game_state keeps "working" while every
# settle gate is effectively disabled and every crop reads the wrong thing.
try:
    import Quartz
    if Quartz.CGPreflightScreenCaptureAccess():
        ok("Screen Recording permission granted")
    else:
        bad("Screen Recording permission NOT granted for this interpreter",
            "settle gates silently disabled; grant it in System Settings > "
            "Privacy & Security > Screen Recording, then restart the terminal")
except Exception as e:
    warn(f"could not check Screen Recording permission ({e})")

# Every crop in orchestrator is FRACTIONAL, so the wrong display means every
# region silently lands on the wrong pixels. mss caches monitors for the
# process lifetime and monitors[1] is hardcoded.
try:
    import mss
    with mss.mss() as m:
        mon = m.monitors[1]
        aspect = mon["width"] / mon["height"]
        expected = 1728 / 1117
        line = f"capture display monitors[1] = {mon['width']}x{mon['height']} (aspect {aspect:.2f})"
        if abs(aspect - expected) > 0.15:
            bad(line, f"calibrated for aspect {expected:.2f} — fractional crops "
                      "will target the wrong pixels")
        else:
            ok(line)
        if len(m.monitors) > 2:
            others = ", ".join(f"{x['width']}x{x['height']}"
                               for x in m.monitors[2:])
            warn(f"{len(m.monitors) - 2} other display(s) attached ({others}) — "
                 "if the game moves to one, monitors[1] is still what gets captured")
except Exception as e:
    bad(f"mss capture unavailable ({e})", "the loop falls back to pyautogui at ~8x the cost")

# Right display, but is the GAME where it was when the card regions were
# calibrated? Every region in orchestrator is a fraction of the WHOLE DESKTOP
# CAPTURE, so they encode the chiaki window's position, not just the display.
# Measured: a 58px displacement changed nothing, 110px silently FLIPPED a
# ban-grid cell — banning a different card, with no error raised.
try:
    import input_controller as _ic
    _fits, _drift, _rect, _ref = _ic.window_drift()
    if _rect is None:
        warn("the chiaki window is not open, so its position cannot be checked "
             "— start the stream, then re-run preflight")
    elif _ref is None:
        warn(f"no calibrated window position recorded for this machine yet "
             f"(window is at {tuple(int(v) for v in _rect)}). Once the regions "
             f"are known good, run: python3 -c 'import input_controller as i; "
             f"i.save_window_reference()'")
    elif _fits:
        ok(f"chiaki window within {_drift:.0f}pt of its calibrated position")
    else:
        bad(f"the chiaki window has moved {_drift:.0f}pt from where the card "
            f"regions were calibrated (limit {_ic.WINDOW_DRIFT_MAX_PT:.0f}pt)",
            "card regions will land on the wrong pixels and can ban the wrong "
            "card silently — put the window back, or recalibrate")
except Exception as e:
    warn(f"could not check the chiaki window position ({e})")

print("\n--- 2. Money ----------------------------------------------------")
progress_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "progress.json")
try:
    with open(progress_file) as f:
        prog = json.load(f)
    bal = prog.get("balance")
    label = os.path.basename(progress_file)
    if bal is None:
        warn(f"{label} has no balance — it will be read from the pause menu")
    elif bal < ENTRY_COST:
        bad(f"{label} balance is ${bal}, below the ${ENTRY_COST} entry cost",
            "the run will stop immediately without playing a turn; top up "
            f"in-game and edit 'balance' in {label}")
    else:
        ok(f"{label}: ${bal} on hand ({bal // ENTRY_COST} match(es) affordable), "
           f"{prog.get('wins', 0)}W/{prog.get('losses', 0)}L/{prog.get('draws', 0)}D")

    # A paid match that never finished. The flag makes the NEXT result screen
    # score correctly after a crash — but if the match is genuinely over (you
    # finished it by hand, or reloaded the save), it is stale, and every rerun
    # will keep trying to score a result that is not coming. Nothing else
    # surfaces it, so it is only ever fixed by hand-editing JSON.
    if prog.get("match_in_progress"):
        _bans = bool(prog.get("bans_done_this_match"))
        # bad(), NOT warn(). This was a warning until 2026-09-04, and a warning
        # does not block a run.
        #
        # MEASURED, and reproduced offline: a STALE flag plus a real dealer
        # prompt makes orchestrator's recovery path press `start_match`
        # believing the $50 was already paid. The money leaves the in-game
        # wallet, `balance` is never debited, `save_progress` is never called,
        # and `max_spend` cannot stop it — run_one_match.py's promise that "no
        # new money is ever spent, whatever the tracked balance says" does not
        # hold in that state.
        #
        # And the stale state was the NORMAL one: 25 call sites reload the save
        # and only run_cycles repaired the record, so every navigation run left
        # this armed. reset_environment(progress_file=...) now clears it, but
        # this gate has to hold for records written before that fix, and for
        # the reloads that still pass no progress file.
        bad(f"{label} says a paid match was in progress when it was last "
            f"written (bans placed: {_bans}).",
            "If that match is genuinely still on screen, this is correct and "
            "the next result will score properly — run with the flag as it is. "
            "If it is NOT (you reloaded the save, or a navigation run did), it "
            "is STALE, and starting now can spend an UNTRACKED $50 that "
            "max_spend cannot prevent. CHECK THE SCREEN, then clear it with: "
            f"python3 clear_match_state.py {label}")
except FileNotFoundError:
    warn(f"{progress_file} does not exist — first run, balance read from pause menu")
except Exception as e:
    bad(f"could not read {progress_file} ({e})")

print("\n--- 3. Credentials & dependencies -------------------------------")
import env_loader
env_loader.load()   # preflight checks the key WITHOUT importing
                    # orchestrator, so it needs its own load or it would
                    # report "not set" for a key .env provides
real_key = os.environ.get("PERSONAL_ANTHROPIC_API_KEY", "")
if real_key and real_key != "dummy-preflight":
    ok(f"PERSONAL_ANTHROPIC_API_KEY set ({real_key[:8]}...{real_key[-4:]})")
else:
    bad("PERSONAL_ANTHROPIC_API_KEY is not set in this shell",
        "source ~/.zshrc.secrets before running")

try:
    import pytesseract
    pytesseract.get_tesseract_version()
    ok("tesseract available (scoreboard, runner and ban-name OCR)")
except Exception as e:
    warn(f"tesseract unavailable ({e}) — local OCR falls back to the vision API")

try:
    import hand_digit_reader
    if hand_digit_reader.check_paddle_venv():
        ok("PaddleOCR venv reachable (hand-digit reader)")
    else:
        warn("PaddleOCR venv not reachable — hand digits fall back to vision")
except Exception as e:
    warn(f"could not check the PaddleOCR venv ({e})")

print("\n--- 4. Code health ----------------------------------------------")
try:
    import orchestrator
    ok(f"orchestrator imports cleanly ({len(orchestrator.KNOWN_BAN_ROSTER)} roster entries)")
    # These are the constants a silent regression moves.
    t = orchestrator.REVEAL_EDGE_THRESHOLD
    # The band is a change-detector, NOT a proven separation. A census of the
    # 3700 frames of the 2026-08-26 run found 447 non-reveal frames above it
    # (a hand-verified idle turn screen reads 0.0844), so the classes overlap
    # and no threshold divides them — see test_settle_regions.py. Reported as
    # "unchanged", not "safe", so this line stops implying a margin it has
    # never had.
    if 0.0615 < t < 0.0692:
        ok(f"REVEAL_EDGE_THRESHOLD={t} unchanged (overlapping classes; the "
           "detector tolerates it because early fires are ~0.6s at most)")
    else:
        bad(f"REVEAL_EDGE_THRESHOLD={t} outside [0.0615, 0.0692]",
            "the reveal threshold moved from the value that ran live")
    if orchestrator.SETTLE_REGION_SETS.get("turn") == ("hand",):
        ok("turn settle gate is hand-alone (measured best)")
    else:
        warn(f"turn settle gate is {orchestrator.SETTLE_REGION_SETS.get('turn')}, "
             "expected ('hand',)")
except Exception as e:
    bad(f"orchestrator failed to import ({e})")

# Say so before blocking for ~4 minutes. This step is the whole reason
# preflight feels like a hang, and it captures the suite's output, so without
# this line there is nothing on screen at all while it runs.
print("  ...running the offline test suite (17 files, ~40s)", flush=True)
r = subprocess.run(["bash", os.path.join(HERE, "run_tests.sh")],
                   capture_output=True, text=True, cwd=HERE)
if r.returncode == 0:
    n = r.stdout.count("PASS")
    ok(f"offline test suite green ({n} files)")
else:
    failed = [l.split()[0] for l in r.stdout.splitlines() if "FAIL" in l]
    bad(f"offline test suite FAILING: {', '.join(failed)}", "run ./run_tests.sh for detail")

print("\n" + "=" * 66)
if problems:
    print(f"NOT READY — {len(problems)} blocker(s):\n")
    for p in problems:
        print(f"  * {p}")
else:
    print("READY.")
if advisories:
    print(f"\n{len(advisories)} warning(s):\n")
    for w in advisories:
        print(f"  * {w}")
print("=" * 66 + "\n")
sys.exit(1 if problems else 0)
