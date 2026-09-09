"""The hand is read from the POST-DEAL frame, where no card is lifted.

WHY. The game raises and BRIGHTENS whichever card the cursor rests on. A lifted card's ink
passes above DARK = 110 so its disc is never found, and the lift OCCLUDES its neighbour,
costing a second card. The lift is also ANIMATED, so the same card reads in one frame and
not the next. Across 57 hands reviewed by the user against the live corpus, every one of
the 16 abstentions was a lifted or occluded card -- and there were ZERO wrong reads. So the
abstentions were the whole remaining gap, and this removes their cause.

The user's own words: "if you use the screenshot after cards are dealt it guarantees that
you can see all the cards since none of them are selected... do not go chasing dragons."

The checks below pin the two properties that make it safe, not the mechanism:
the post-deal frame is PREFERRED when present, and it is CLEARED ON USE so a hand from an
earlier turn can never be read as this turn's.
"""
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


# ---- 1. THE STASH CLEARS ON USE. A hand left from an earlier turn that still looks fresh
# is this project's signature failure and would be completely invisible here.
orchestrator._POST_DEAL_HAND = None
check("nothing stashed means nothing returned",
      orchestrator.take_post_deal_hand() is None)

marker = Image.new("L", (979, 307), 123)
orchestrator._POST_DEAL_HAND = marker
got = orchestrator.take_post_deal_hand()
check("the stashed frame is returned", got is marker)
check("and the stash is EMPTY afterwards, so it cannot be reused",
      orchestrator.take_post_deal_hand() is None)

# ---- 2. THE POLL FILLS IT, and it is filled through a SETTER.
# `_POST_DEAL_HAND = ...` inside run() would bind a LOCAL, the stash would stay empty
# forever, and the reader would silently use the later vision crop with nothing anywhere
# saying so -- this project's signature failure. Caught before it ever ran; pinned here so
# it cannot come back.
import ast                                                              # noqa: E402
import inspect                                                          # noqa: E402

src_all = inspect.getsource(orchestrator)
tree = ast.parse(src_all)
run_fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
check("orchestrator.run exists to check", run_fn is not None)
if run_fn is not None:
    local_binds = [n for n in ast.walk(run_fn) if isinstance(n, ast.Assign)
                   for t in n.targets
                   if isinstance(t, ast.Name) and t.id == "_POST_DEAL_HAND"]
    check("run() never BINDS _POST_DEAL_HAND directly -- that would be a silent no-op",
          not local_binds, f"{len(local_binds)} direct assignment(s)")
    calls = [n for n in ast.walk(run_fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "stash_post_deal_hand"]
    check("run() fills the stash through the setter", len(calls) == 1, f"{len(calls)} call(s)")

poll_src = inspect.getsource(orchestrator.poll_for_readable_hand)
check("the poll scores frames by slots actually READ, not slots found",
      "r[\"digit\"] is not None" in poll_src and "read > best_read" in poll_src)
check("and it stops early on a complete read rather than burning the whole window",
      "break" in poll_src and "MAX_HAND_SIZE" in poll_src)

# ---- 3. THE READER PREFERS IT. Pinned on the call, not on a comment.
src2 = inspect.getsource(orchestrator.log_local_read_comparison)
check("the local read prefers the post-deal frame",
      "take_post_deal_hand()" in src2)
check("and falls back to the vision crop when there is none",
      'or crops["hand"]' in src2)
check("the source of each recorded hand is written down, so the effect is measurable",
      "hand_src" in src2)

# ---- 4. THE CROP GEOMETRY MATCHES, or the reader's slot anchors land in the wrong place.
# The deal gate crops through _settle_region_box; the vision path through
# GAMEPLAY_REGIONS_FRAC. They must be the same box.
check("the deal gate and the vision crop use the SAME hand region",
      orchestrator._settle_region_box("hand") ==
      orchestrator.GAMEPLAY_REGIONS_FRAC["hand"],
      f"{orchestrator._settle_region_box('hand')} vs "
      f"{orchestrator.GAMEPLAY_REGIONS_FRAC['hand']}")

# ---- 5. A GRAYSCALE CROP IS READABLE. The deal gate returns "L"; the vision path "RGB".
import local_hand                                                       # noqa: E402
FIX = os.path.join(_ROOT, "test_fixtures", "hand_digits", "hand025.png")
rgb = Image.open(FIX).convert("RGB")
gray = Image.open(FIX).convert("L")
a = [r["digit"] for r in local_hand.read_hand(rgb)]
b = [r["digit"] for r in local_hand.read_hand(gray)]
check("a grayscale hand reads the same as an RGB one", a == b, f"{a} vs {b}")

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
