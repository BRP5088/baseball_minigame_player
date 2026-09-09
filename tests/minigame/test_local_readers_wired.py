"""The local readers must actually CORRECT the paid model's answer, and say so.

WHY THIS FILE EXISTS. apply_local_readers() runs on a $50 path and its whole job is to
change a field. A correction that silently does nothing is indistinguishable from no
correction at all -- this project's signature failure (CLAUDE.md 10.1) -- so the checks
below assert the OVERRIDE HAPPENS, not merely that the function is present.

TWO DIFFERENT CLAIMS, kept apart on purpose:
  OVERRIDE   discards_left. Measured against the USER'S OWN EYES over eight boards
             spanning every disagreement shape: local 8 of 8, paid 0 of 8. It feeds
             should_redraw(), so it decides DISCARD against PLAY.
  FILL ONLY  runners and phase. Local agrees 97.2% and 96.1% with the paid model over 360
             turns, and agreement is not evidence about who is right on the rest -- so
             these only supply a field the paid model left EMPTY.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


FIX = os.path.join(_ROOT, "test_fixtures", "discards")
truth = json.load(open(os.path.join(FIX, "truth.json")))

# ---- 1. THE OVERRIDE FIRES, on real boards, with the paid model's own wrong answer -----
fired = 0
for b in truth["boards"]:
    sb = Image.open(os.path.join(FIX, b["file"])).convert("RGB")
    state = {"screen": "turn", "discards_left": b["paid_said"]}
    orchestrator.apply_local_readers(state, {"scoreboard": sb})
    check(f"{b['file']}: {b['paid_said']} corrected to {b['discards_left']}",
          state["discards_left"] == b["discards_left"],
          f"got {state['discards_left']}")
    fired += state["discards_left"] != b["paid_said"]
check("the override actually fired on every board where the paid model was wrong",
      fired == len(truth["boards"]), f"{fired} of {len(truth['boards'])}")

# ---- 2. IT DOES NOT FIRE OFF A TURN SCREEN. Applying turn readers to a ban screen would
# produce confident nonsense, so the screen gate is part of the guard.
sb = Image.open(os.path.join(FIX, truth["boards"][0]["file"])).convert("RGB")
for screen in ("ban_screen", "result", "match_start_prompt", "other"):
    st = {"screen": screen, "discards_left": 2}
    orchestrator.apply_local_readers(st, {"scoreboard": sb})
    check(f"no correction on a {screen} screen", st["discards_left"] == 2,
          f"became {st['discards_left']}")

# ---- 3. RUNNERS AND PHASE ONLY FILL, NEVER OVERRIDE. Agreement is not evidence about
# who is right where they differ, so a value the paid model already gave is left alone.
# The hand crop must be one the phase reader ANSWERS on, or this branch never runs and the
# check is decorative -- a mutant that made phase OVERRIDE instead of fill survived exactly
# that way. hand030 reads "pitching", so the state is seeded with the OPPOSITE.
HANDS = os.path.join(_ROOT, "test_fixtures", "hand_digits")
hand = Image.open(os.path.join(HANDS, "hand030.png")).convert("RGB")
import local_state                                                      # noqa: E402
local_phase, _ = local_state.read_phase(hand)
check("the fixture chosen actually yields a local phase", local_phase == "pitching",
      str(local_phase))
st = {"screen": "turn", "phase": "batting", "runners": [{"name": "x"}]}
orchestrator.apply_local_readers(st, {"scoreboard": sb, "hand": hand})
check("an existing phase is NOT overridden, even when local reads a different one",
      st["phase"] == "batting", f"became {st.get('phase')}")
check("existing runners are left alone", st["runners"] == [{"name": "x"}], str(st["runners"]))
# and it DOES fill an empty one, or "fill only" would be indistinguishable from "never"
st2 = {"screen": "turn", "runners": [{"name": "x"}]}
orchestrator.apply_local_readers(st2, {"scoreboard": sb, "hand": hand})
check("an EMPTY phase is filled from the banners", st2.get("phase") == "pitching",
      str(st2.get("phase")))

# ---- 4. IT NEVER RAISES INTO THE TURN LOOP, whatever it is handed.
for bad in ({}, {"screen": "turn"}, {"screen": "turn", "discards_left": None}):
    try:
        orchestrator.apply_local_readers(dict(bad), {})
        orchestrator.apply_local_readers(dict(bad), None)
        ok = True
    except Exception as e:
        ok = False
        print(f"      raised: {e}")
    check(f"survives being handed {bad}", ok)

# ---- 5. IT IS ACTUALLY CALLED. Without this the whole file passes while nothing runs.
import inspect                                                          # noqa: E402
src = inspect.getsource(orchestrator.read_game_state)
check("read_game_state calls apply_local_readers", "apply_local_readers(state)" in src)
check("and does so BEFORE validation, so a corrected value is what gets validated",
      src.index("apply_local_readers(state)") < src.index("validate_game_state(state)"))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
