"""A tool that drives a live match must spend, refuse and unpack like production.

QA round 4 found three shapes in tools/ that production had already fixed:

  BYPASSING spend_and_play. Calling select_and_play/select_and_discard directly
  skips forget_hand_slot, so _hand_memory keeps the card that was just played and
  local_hand_cards serves it back for that slot on the next turn -- which is exactly
  the slot the memory is consulted for, so nothing audits it.

  DEFAULTING AN UNREAD PHASE. `ls.read_phase(hand)[0] or "batting"` turns an
  abstention into a value, and that value is a whole STRATEGY: while pitching it
  runs best_batting_play and proposes the wrong kind of card.
  orchestrator.local_game_state refuses for exactly this reason.

  USING A TUPLE AS A BOOL. spend_and_play and spend_and_discard return (ok, why).
  A non-empty tuple is ALWAYS truthy, so `if o.spend_and_play(s)` makes the refusal
  branch unreachable -- 10.1's family, introduced by the fix for the first shape
  until this scan caught it.

Scanned rather than hand-listed, because a hand-kept list of names rots silently:
nothing fails when a new tool is missing from it (CLAUDE.md, keep_awake's lesson).
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


TOOLS = os.path.join(_ROOT, "tools")
RAW_SPENDS = {"select_and_play", "select_and_discard"}
WRAPPED = {"spend_and_play", "spend_and_discard"}

raw_calls, bare_bools, phase_defaults, scanned = [], [], [], 0

for fn in sorted(os.listdir(TOOLS)):
    if not fn.endswith(".py"):
        continue
    path = os.path.join(TOOLS, fn)
    try:
        tree = ast.parse(open(path).read())
    except SyntaxError:
        continue
    scanned += 1
    for n in ast.walk(tree):
        # a call to the RAW spend functions, by bare name or attribute
        if isinstance(n, ast.Call):
            name = (n.func.attr if isinstance(n.func, ast.Attribute)
                    else n.func.id if isinstance(n.func, ast.Name) else None)
            if name in RAW_SPENDS:
                raw_calls.append(f"{fn}:{n.lineno} {name}")
        # a wrapped spend used directly where a BOOL is wanted
        if isinstance(n, (ast.If, ast.IfExp)):
            t = n.test
            if isinstance(t, ast.Call):
                nm = (t.func.attr if isinstance(t.func, ast.Attribute)
                      else t.func.id if isinstance(t.func, ast.Name) else None)
                if nm in WRAPPED:
                    bare_bools.append(f"{fn}:{t.lineno} {nm}")
        # `read_phase(...)[...] or "batting"` -- an abstention given a value
        if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
            srcseg = ast.dump(n)
            if "read_phase" in srcseg and "batting" in srcseg:
                phase_defaults.append(f"{fn}:{n.lineno}")

check(scanned >= 10, f"the scan actually read {scanned} tool files — an empty scan "
                     "must not pass")

check(not raw_calls,
      f"no tool calls select_and_play/select_and_discard directly; they must use "
      f"spend_and_play/spend_and_discard so forget_hand_slot runs: {raw_calls}")

check(not bare_bools,
      f"no tool uses a spend_and_* call as a bare boolean — it returns (ok, why) "
      f"and a non-empty tuple is always truthy: {bare_bools}")

check(not phase_defaults,
      f"no tool defaults an unread phase to 'batting' — refuse instead, the way "
      f"local_game_state does: {phase_defaults}")

# POSITIVE CONTROL: the scan must be able to SEE these shapes, or "found nothing"
# means nothing. Parse a snippet containing all three and confirm each is caught.
_ctl = ast.parse(
    'o.select_and_play(1, look=x)\n'
    'if o.spend_and_play(1):\n    pass\n'
    'phase = ls.read_phase(h)[0] or "batting"\n')
_r = _b = _p = 0
for n in ast.walk(_ctl):
    if isinstance(n, ast.Call):
        nm = (n.func.attr if isinstance(n.func, ast.Attribute)
              else n.func.id if isinstance(n.func, ast.Name) else None)
        if nm in RAW_SPENDS:
            _r += 1
    if isinstance(n, (ast.If, ast.IfExp)) and isinstance(n.test, ast.Call):
        nm = (n.test.func.attr if isinstance(n.test.func, ast.Attribute)
              else n.test.func.id if isinstance(n.test.func, ast.Name) else None)
        if nm in WRAPPED:
            _b += 1
    if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
        d = ast.dump(n)
        if "read_phase" in d and "batting" in d:
            _p += 1
check(_r == 1 and _b == 1 and _p == 1,
      f"CONTROL: the scan detects all three shapes when they are present "
      f"(raw={_r}, bare_bool={_b}, phase_default={_p}) — without this, three empty "
      "lists would read as a clean tree")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
