"""Bring chiaki to the front. For unattended runs only.

chiaki does not reliably act on injected input while it is not the active
window — an overnight run stalled on exactly this, with the reset unable to
open the pause menu while sticks still worked. Focusing fixes it, and is only
appropriate when nobody is using the machine.
"""
import os
import subprocess
import time

CHIAKI = "chiaki"


def focus(log=print):
    script = (f'tell application "System Events" to set frontmost of first '
              f'process whose name contains "{CHIAKI}" to true')
    subprocess.run(["osascript", "-e", script], check=False,
                   capture_output=True)
    time.sleep(0.5)
    out = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of '
         'first application process whose frontmost is true'],
        capture_output=True, text=True).stdout.strip()
    ok = CHIAKI in out.lower()
    log(f"  frontmost: {out!r} {'(chiaki focused)' if ok else '(FAILED)'}")
    return ok
