"""ensure_live must try to CLEAR what is on top before restarting chiaki.

The bug: a frozen picture went straight to a restart. Every real cause of a
frozen picture here sits ON TOP of a healthy stream — chiaki's own modal
dialog, a macOS crash window, the PS5 overlay, or chiaki idling on its host
list — and a restart fixes none of them and re-creates the dialog.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import ensure_stream as es

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def run(frozen_seq, restarts=2):
    """frozen_seq: what is_frozen() returns on each successive call."""
    calls = {"clear": 0, "restart": 0}
    seq = list(frozen_seq)

    es_ensure, es_frozen = es.ensure, es.is_frozen
    es_clear, es_dismiss = es._clear_blocking_ui, es._dismiss_overlay_if_blocking
    import subprocess
    real_run = subprocess.run
    try:
        es.ensure = lambda log=None: True          # heartbeats are fine
        es.is_frozen = lambda *a, **k: seq.pop(0) if seq else True
        def clear(log=None):
            calls["clear"] += 1
            return True
        es._clear_blocking_ui = clear
        es._dismiss_overlay_if_blocking = lambda log=None: False
        def fake_run(cmd, *a, **k):
            if cmd and "restart_chiaki.sh" in str(cmd[0]):
                calls["restart"] += 1
            class R: returncode = 0
            return R()
        subprocess.run = fake_run
        es.time.sleep = lambda *a: None
        ok = es.ensure_live(log=lambda *a: None, restarts=restarts)
    finally:
        es.ensure, es.is_frozen = es_ensure, es_frozen
        es._clear_blocking_ui, es._dismiss_overlay_if_blocking = es_clear, es_dismiss
        subprocess.run = real_run
    return ok, calls


# Frozen once, then live after the UI is cleared: must NOT restart at all.
ok, c = run([True, False])
check("a dialog is cleared instead of restarting", ok and c["restart"] == 0)
check("and clearing was actually attempted", c["clear"] >= 1)

# Never recovers: still restarts, so a genuinely dead stream is not ignored.
ok, c = run([True] * 20)
check("a truly frozen stream still restarts", not ok and c["restart"] >= 1)

# Healthy from the start: no clearing, no restart.
ok, c = run([False])
check("a healthy stream is left alone",
      ok and c["restart"] == 0 and c["clear"] == 0)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
