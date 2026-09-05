"""A money read is only valid if the PAUSE MENU is confirmed open.

WHY THIS EXISTS
---------------
The health coin in the bottom-left of the world HUD reads 100 and looks exactly
like money — the READ_BALANCE_PROMPT even describes money as "a round
coin/medallion with an embossed face", which is also the health coin.

read_balance_from_pause_menu() pressed toggle_pause and captured immediately.
toggle_pause is a TOGGLE and does not always land; when it did not, the capture
was the WORLD, vision found the health coin, and the run reported the bankroll
collapsing from $246 to $100 across four cycles. The user has had to correct
this reading three times.

So: never read a number off a screen that has not been confirmed to be the
pause menu, and never accept a lone number without the currency stack that
proves vision found the right place.
"""
import os
import os as _os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import orchestrator as o

fails = []


def check(c, m):
    if not c:
        fails.append(m)


class Vision:
    """Stands in for the API. Records whether it was called at all."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        return types.SimpleNamespace(content=[
            types.SimpleNamespace(type="text", text=self.payload)])


def run(pause_opens, payload='{"counters": [246, 8, 5], "money": 246}'):
    v = Vision(payload)
    saved = (o.press, o.wait_for_screen_to_settle, o._fast_grab,
             o.capture_screenshot_b64, o.client)
    o.press = lambda *a, **k: None
    o.wait_for_screen_to_settle = lambda *a, **k: None
    o._fast_grab = lambda *a, **k: object()
    o.capture_screenshot_b64 = lambda *a, **k: "x"
    o.client = types.SimpleNamespace(messages=v)
    sys.modules["pause_menu"] = types.ModuleType("pause_menu")
    sys.modules["pause_menu"].is_pause_screen = lambda img: pause_opens
    try:
        return o.read_balance_from_pause_menu(), None, v
    except Exception as e:
        return None, e, v
    finally:
        (o.press, o.wait_for_screen_to_settle, o._fast_grab,
         o.capture_screenshot_b64, o.client) = saved


# --- the menu never opens: refuse, and do not even spend the call ---------
val, err, v = run(pause_opens=False)
check(err is not None,
      f"read a balance of {val!r} from a screen that is NOT the pause menu — "
      "that screen's only number is the HEALTH coin, which reads 100")
check(v.calls == 0,
      f"spent {v.calls} vision call(s) on a screen that was not the pause menu "
      "— money is not readable there, so the call is pure cost")

# --- the menu opens: normal read -----------------------------------------
val, err, v = run(pause_opens=True)
check(err is None and val == 246, f"pause menu open: got {val!r}, err {err!r}")

# --- a lone number with no counter stack must be refused ------------------
val, err, v = run(pause_opens=True, payload='{"money": 100}')
check(err is not None,
      f"accepted money={val!r} with no currency stack — a lone number could "
      "have come from anywhere on screen, which is how the health coin became "
      "the wallet")

# --- an honest refusal stays a refusal -----------------------------------
val, err, v = run(pause_opens=True, payload='{"counters": null, "money": null}')
check(err is not None, "vision said it could not find the stack; that must raise")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  balance read: refuses any screen that is not the pause menu (without "
      "spending a call), and refuses a number with no currency stack behind it")
