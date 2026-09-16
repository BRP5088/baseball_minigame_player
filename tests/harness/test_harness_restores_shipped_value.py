"""A harness may not hardcode what a graph_walk flag's default "is".

WHAT THIS GUARDS. Every A/B harness flips a graph_walk flag and restores it in
a `finally`. All of them restored a LITERAL -- what the default was on the day
that script was written -- so the restore rotted silently into a WRONG value the
moment the real default changed:

    ab_leg_speed  restored LEG_SPEED_BY_LEG = {}    after leg 1 shipped 3.0
    ab_stall      restored STALL_CHANGE     = 2.5   after it became 6.0

A cleanup that reinstates a stale default is worse than no cleanup. It looks
like tidiness and installs an arm, and nothing fails when it is wrong -- the
duplicate-constant trap, which on this project already produced a block of
turning constants sitting under the most authoritative comment in the file and
read by nothing.

TWO RULES, and the second is the one with teeth:

1. A literal assignment to `gw.<FLAG>` must equal what graph_walk ships. An ARM
   is set from a variable, never a literal, so this constrains only what a
   harness may CLAIM the default is, not what it may test.

2. A harness that installs an arm IN ITS OWN PROCESS must restore that same
   flag from a CAPTURED value. Rule 1 alone is satisfiable by deleting the
   restore entirely, which would leave the arm installed -- a worse bug than the
   one being fixed.

   A harness that runs trials through `_harness.run_trial` is EXEMPT, and the
   exemption is the interesting part: it sets the arm inside the `--one-trial`
   child, which then exits. Process death is the restore, it cannot be forgotten
   or written wrong, and the parent never holds the flag at all. That is a
   second reason to prefer the subprocess pattern beyond the timeout being real
   -- so the exemption is granted by a positive fact about the file, not by a
   list of names, which is the kind of guard that rots (CLAUDE.md's keep_awake).

WHY THE CONTROL IS SYNTHETIC. Rule 1 passes today by there being no literals
left at all, so counting them proves nothing. The scanner is instead run over a
source with a known-bad line, and is required to flag it. A checker that cannot
fail is the thing this whole file is about.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import graph_walk as gw

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


def scan(source, path):
    """(stale_literals, armed_flags, captured_flags) for one module source."""
    stale, armed, captured = [], set(), set()
    tree = ast.parse(source, path)
    for node in ast.walk(tree):
        # `_SHIPPED = {"FLAG": ...}` -- the capture
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "_SHIPPED" \
                and isinstance(node.value, ast.Dict):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    captured.add(k.value)
            continue
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                and t.value.id == "gw" and t.attr.isupper()):
            continue
        try:
            want = ast.literal_eval(node.value)
        except Exception:
            armed.add(t.attr)          # set from a variable: an ARM
            continue
        live = getattr(gw, t.attr, "<<graph_walk does not define this>>")
        if want != live:
            stale.append((node.lineno, t.attr, want, live))
    return stale, armed, captured


# --- the real harnesses ------------------------------------------------------
over = os.path.join(_ROOT, "overnight")
files = sorted(f for f in os.listdir(over) if f.endswith(".py"))
check("there are harnesses to scan", len(files) >= 5)

all_stale, arming = [], {}
for fn in files:
    src = open(os.path.join(over, fn)).read()
    try:
        stale, armed, captured = scan(src, fn)
    except SyntaxError as e:
        check(f"{fn} parses", False)
        print(f"     {e}")
        continue
    for lineno, flag, want, live in stale:
        all_stale.append(
            f"{fn}:{lineno} sets gw.{flag} = {want!r} as a literal, but "
            f"graph_walk ships {live!r}. If this is a RESTORE, capture the "
            f"flag at import time instead of naming a value. If it is an ARM, "
            f"set it from a variable so this check can tell them apart.")
    if armed:
        # Subprocess harnesses set the arm in the child, which then exits.
        # Nothing to restore, and nothing that CAN be restored wrongly.
        arming[fn] = (armed, captured, "_harness.run_trial" in src)

for msg in all_stale:
    print("FAIL " + msg)
    ok = False
check("no harness hardcodes a graph_walk default", not all_stale)

# --- rule 2: an installed arm must be restored from a capture ---------------
check("at least one harness installs an arm, so rule 2 is not vacuous",
      len(arming) >= 3)

in_process = 0
for fn, (armed, captured, subproc) in sorted(arming.items()):
    if subproc:
        print(f"PASS {fn} arms {sorted(armed)} inside a run_trial child, which "
              f"exits -- no restore needed, and none can be written wrong")
        continue
    in_process += 1
    unrestored = sorted(armed - captured)
    check(f"{fn} captures the flags it arms "
          + (f"(arms {sorted(armed)})" if not unrestored
             else f"-- MISSING a capture for {unrestored}, so the arm is left "
                  f"installed when the run ends"),
          not unrestored)

# ANTI-VACUITY for rule 2: if every harness became a subprocess harness, the
# loop above would exempt them all and prove nothing. Say so rather than
# passing quietly -- and if that day comes, this rule is genuinely obsolete and
# should be deleted deliberately, not left looking green.
check(f"rule 2 actually examined {in_process} in-process harness(es)",
      in_process >= 1)

# --- the positive control ----------------------------------------------------
# THE PLANTS ARE DERIVED FROM WHAT SHIPS, NEVER WRITTEN AS LITERALS.
#
# This control used to plant `gw.LEG_SPEED_BY_LEG = {}`, which was a genuinely
# stale default while an override shipped. On 2026-09-06 that override was
# reverted on measured evidence (overnight/ab_leg1.py: 2/10 against 10/10,
# p = 0.000714) -- and `{}` instantly stopped being stale. The control then
# found 1 of 2 planted and the scanner's own proof of life had degraded, with
# nothing failing to say so. A positive control written as a literal decays the
# moment the thing it describes is corrected, which is precisely when the
# scanner matters most.
#
# Derived plants cannot rot: each is asserted different from the shipped value
# at runtime, so this control is correct whatever graph_walk ships tomorrow.
_PLANT = {"STALL_CHANGE": 2.5 if gw.STALL_CHANGE != 2.5 else 9.75,
          "MERGE_STEPS": not gw.MERGE_STEPS}
for _f, _v in _PLANT.items():
    assert _v != getattr(gw, _f), (
        f"the positive control planted {_f}={_v!r}, which is what graph_walk "
        f"actually ships — the plant is not stale and proves nothing")
BAD = ("import graph_walk as gw\n"
       + "".join(f"gw.{f} = {v!r}\n" for f, v in _PLANT.items()))
stale, _, _ = scan(BAD, "<synthetic>")
check("the scanner CAN detect a stale hardcoded default "
      f"(found {len(stale)} of {len(_PLANT)} planted)", len(stale) == len(_PLANT))
check("and it names both the written value and the shipped one",
      any(w == _PLANT["STALL_CHANGE"] and l == gw.STALL_CHANGE
          for _, f, w, l in stale if f == "STALL_CHANGE"))

GOOD = ('import graph_walk as gw\n'
        '_SHIPPED = {"STALL_CHANGE": gw.STALL_CHANGE}\n'
        'gw.STALL_CHANGE = arm\n'
        'gw.STALL_CHANGE = _SHIPPED["STALL_CHANGE"]\n')
stale, armed, captured = scan(GOOD, "<synthetic>")
check("and it does NOT flag a correct capture-and-restore",
      not stale and armed == {"STALL_CHANGE"} and captured == {"STALL_CHANGE"})

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
