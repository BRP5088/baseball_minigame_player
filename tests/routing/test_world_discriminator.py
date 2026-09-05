r"""'Am I in the world?' must not be answered by the HUD readers.

WHY THIS EXISTS
---------------
orchestrator retries a dropped start_match press only when it can prove no
match is running. The obvious proof — "is the world HUD on screen?" — was
written first as compass.find_bar()/read_bearing() and is WRONG:

    measured 2026-09-01, on real logged frames
      find_bar      returned non-None on EVERY frame tried, including three
                    gameplay turns and a ban screen
      read_bearing  returned 177.4 on a GAMEPLAY TURN

Either would report "in the world" during a live match, and the retry would
fire start_match (the `\` key, same as confirm_discard) into it — real
in-game spend that max_spend never sees. That is the QA1-F1 harm the guard
exists to prevent.

at_table() is sound because it demands contrast AND prompt ink AND stroke-shape
correlation together, and the dealer's prompt text is never drawn over a match.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

from PIL import Image

import places
import table_prompt as tp

MATCH = ["test_fixtures/prompt_detector/20260828_140652_622.jpg",
         "test_fixtures/prompt_detector/20260828_140623_689.jpg",
         "test_fixtures/prompt_detector/20260828_140708_034.jpg",
         "test_fixtures/ban_scan/20260828_140309_081.jpg"]
WORLD = ["places/dealer_table/000.jpg", "places/dealer_table/001.jpg"]

fails = []


def check(c, m):
    if not c:
        fails.append(m)


for rel in MATCH:
    p = os.path.join(_ROOT, rel)
    if not os.path.exists(p):
        fails.append(f"missing fixture {rel} — this test must not silently skip")
        continue
    im = Image.open(p)
    check(tp.at_table(im) is False,
          f"{os.path.basename(rel)}: at_table() said True on a MATCH screen. "
          f"orchestrator treats that as proof no match is running and retries "
          f"start_match into the live match — real untracked in-game spend.")
    room, score, _ = places.identify(im)
    check(room is None,
          f"{os.path.basename(rel)}: places.identify() named {room!r} "
          f"(score {score:.2f}) on a MATCH screen; it must abstain")

for rel in WORLD:
    p = os.path.join(_ROOT, rel)
    if not os.path.exists(p):
        fails.append(f"missing fixture {rel} — this test must not silently skip")
        continue
    im = Image.open(p)
    check(tp.at_table(im) is True,
          f"{os.path.basename(rel)}: at_table() said False at the real dealer "
          f"table; the retry would never fire and a dropped press stalls the "
          f"whole match")

# And the negative result that motivated all of this: the HUD readers are NOT
# usable here. If either ever becomes discriminating, this test should be
# revisited deliberately rather than by accident.
import compass
_hud_fooled = sum(1 for rel in MATCH
                  if compass.find_bar(Image.open(os.path.join(_ROOT, rel))) is not None)
check(_hud_fooled == len(MATCH),
      f"compass.find_bar() now rejects some match screens ({_hud_fooled}/"
      f"{len(MATCH)} still fooled). It used to accept ALL of them, which is why "
      f"the guard uses at_table() instead. Re-check that reasoning before "
      f"relying on find_bar for anything that means 'in the world'.")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  world discriminator: at_table() rejects {len(MATCH)} match screens and "
      f"accepts {len(WORLD)} dealer frames; the HUD readers cannot do this job")
