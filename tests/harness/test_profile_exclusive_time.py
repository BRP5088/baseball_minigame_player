"""A profile whose rows nest must not be summed. This pins the arithmetic.

WHAT THIS GUARDS. `overnight/profile_trial.py` timed nested functions --
turn_to calls read_bearing calls fast_capture -- and reported only INCLUSIVE
time. Summing those rows counts the same microseconds once per level, so the
leftover it printed as "unaccounted" was an artefact of the arithmetic, not a
component of the run. It came out at 65%, and that residual was written up as
the open question the file existed to answer (OPEN-8).

The fix records EXCLUSIVE time too: each frame subtracts whatever was spent
inside other wrapped functions below it. The property that makes the table
readable is that the exclusive column SUMS TO ELAPSED TIME, and that is what is
checked here -- against a synthetic call tree with known sleeps, so the answer
is known in advance rather than inferred from the output.

Offline: no console, no capture, no imports from the vision stack.
"""
import os
import sys
import time
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import profile_trial as pt

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


def reset():
    pt.STATS.clear()
    del pt._FRAMES[:]


# A three-level call tree with known costs:
#   outer  = 0.05 of its own work, then calls middle twice
#   middle = 0.03 of its own work, then calls inner once
#   inner  = 0.02
# So: inner 2 x 0.02 = 0.04, middle 2 x 0.03 = 0.06 exclusive,
#     outer 0.05 exclusive, and the whole tree is 0.15.
NS = types.SimpleNamespace()


def inner():
    time.sleep(0.02)


def middle():
    time.sleep(0.03)
    NS.inner()


def outer():
    time.sleep(0.05)
    NS.middle()
    NS.middle()


NS.inner, NS.middle, NS.outer = inner, middle, outer

reset()
pt.wrap(NS, "inner", "inner")
pt.wrap(NS, "middle", "middle")
pt.wrap(NS, "outer", "outer")

t0 = time.perf_counter()
NS.outer()
elapsed = time.perf_counter() - t0

calls = {k: v[0] for k, v in pt.STATS.items()}
incl = {k: v[1] for k, v in pt.STATS.items()}
excl = {k: v[2] for k, v in pt.STATS.items()}

check("every wrapped function was counted, with the right call counts",
      calls == {"outer": 1, "middle": 2, "inner": 2})

# TOLERANCE. sleep() only guarantees a LOWER bound and this is a shared machine,
# so every assertion is one-sided or generously banded. CLAUDE.md 10.13: under
# saturation sleep degrades from ~5ms to as much as 242ms, so a tight two-sided
# band here would be a threshold sitting inside one population.
# EVERY TIMING ASSERTION BELOW IS A RELATIVE IDENTITY, NOT A BAND.
#
# The first version of this file asserted absolute windows ("outer's exclusive
# is between 0.04 and 0.11"). Those are thresholds sitting inside one
# population: sleep() only guarantees a LOWER bound, and CLAUDE.md 10.13 records
# it degrading from ~5ms to 242ms under saturation on this machine. It duly
# failed once during a 763s suite run and passed on every re-run -- a flaky
# guard, which is worse than none because it teaches the reader to ignore it.
#
# What is checked instead is arithmetic that must hold at ANY speed: exclusive
# time is inclusive time minus the children's inclusive time. Load inflates
# every term together, so it cannot move these.
TOL = 0.05          # 5% of the quantity being compared, never a fixed number

check(f"outer's INCLUSIVE time covers the whole tree "
      f"({incl['outer']:.3f}s vs {elapsed:.3f}s elapsed)",
      abs(incl["outer"] - elapsed) < elapsed * TOL)

check(f"outer's EXCLUSIVE time is its inclusive MINUS its children "
      f"({excl['outer']:.3f} vs {incl['outer'] - incl['middle']:.3f})",
      abs(excl["outer"] - (incl["outer"] - incl["middle"])) < elapsed * TOL)

check(f"and that is a THIRD of its inclusive time, not all of it "
      f"({excl['outer']/incl['outer']:.2f} of it) -- the bug being guarded "
      f"would make this 1.00",
      excl["outer"] / incl["outer"] < 0.5)

check(f"middle's exclusive is its inclusive minus inner's "
      f"({excl['middle']:.3f} vs {incl['middle'] - incl['inner']:.3f})",
      abs(excl["middle"] - (incl["middle"] - incl["inner"])) < elapsed * TOL)

check(f"inner is a leaf, so its exclusive equals its inclusive "
      f"({excl['inner']:.3f} vs {incl['inner']:.3f})",
      abs(excl["inner"] - incl["inner"]) < incl["inner"] * TOL)

total_excl = sum(excl.values())
check(f"THE EXCLUSIVE COLUMN SUMS TO ELAPSED TIME "
      f"({total_excl:.3f}s of {elapsed:.3f}s) -- this is the property that "
      f"makes the residual real",
      abs(total_excl - elapsed) < elapsed * TOL)

total_incl = sum(incl.values())
check(f"and the INCLUSIVE column does not ({total_incl:.3f}s vs "
      f"{elapsed:.3f}s) -- which is the bug being guarded",
      total_incl > elapsed * 1.5)

# The one absolute assertion, and it is one-sided ON THE SAFE SIDE. sleep()
# guarantees a lower bound, so load can only make this MORE true. It exists so
# that a tree which never actually slept cannot satisfy the ratios above by
# comparing noise to noise.
check(f"the tree really did sleep for its 0.15s of work ({elapsed:.3f}s)",
      elapsed >= 0.14)

# --- the frame stack must not leak, or every later row is wrong -------------
check("the frame stack is empty after the tree unwinds", not pt._FRAMES)

# An exception must still pop the frame. If it does not, the next top-level
# call inherits a stale parent and its exclusive time goes negative.
def boom():
    raise ValueError("x")


NS2 = types.SimpleNamespace(boom=boom)
reset()
pt.wrap(NS2, "boom", "boom")
try:
    NS2.boom()
except ValueError:
    pass
check("a raising function still pops its frame", not pt._FRAMES)
check("and is still counted", pt.STATS["boom"][0] == 1)

# --- double-wrapping must be refused ---------------------------------------
# Re-running wrap on the same function would nest a timer inside a timer, so
# every call is counted twice and the exclusive column stops summing.
reset()
NS3 = types.SimpleNamespace(f=lambda: time.sleep(0.01))
pt.wrap(NS3, "f", "f")
first = NS3.f
pt.wrap(NS3, "f", "f")
check("wrapping twice is a no-op, not a nested timer", NS3.f is first)
NS3.f()
check("so a call is counted once, not twice", pt.STATS["f"][0] == 1)

# --- the route is the one section 8(a) reports -----------------------------
# A profile of a different route gets quoted as if it were this one; that
# already happened with the two-leg profile and the 85.6s figure.
check("ROUTE is the 8(a) route, not the old two-leg walk",
      pt.ROUTE == ["portrait_room", "bar_pool_room", "bar_jukebox"])

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
