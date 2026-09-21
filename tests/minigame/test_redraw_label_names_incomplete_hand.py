"""The [redraw] log line must name the INCOMPLETE-hand guard when that is why the
hand was kept, never "hand is strong enough" (seen live 2026-09-21 at best 5 < 6)."""
import os, sys, ast
os.environ["BASEBALL_TEST_RUN"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

src = open(os.path.join(ROOT, "orchestrator.py")).read()
i = src.index('_why = "hand is strong enough"')
block = src[i - 1200:i]
# the incomplete branch sits BEFORE the strong-enough default, in the same chain
j = block.rfind('hand_incomplete')
check("an elif on hand_incomplete precedes the 'strong enough' default", j != -1)
check("that branch names INCOMPLETE in its label",
      j != -1 and "INCOMPLETE" in block[j:])
check("the incomplete label is not the strong-enough label",
      j != -1 and "strong enough" not in block[j:].split("_why =", 1)[-1].split("\n", 1)[0])
# the chain still keeps the no-discards and stall reasons ahead of it
check("no-discards reason still comes first",
      block.find("NO DISCARDS LEFT") < j)
print("fails:", fails)
sys.exit(1 if fails else 0)
