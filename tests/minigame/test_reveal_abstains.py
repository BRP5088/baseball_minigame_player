"""The reveal readers must refuse where they cannot know, not return a number.

Three QA round 4 findings, all the same family: an abstention scored as a value.

  _side picked the LOWEST disc as the played card, and a second player card DOES
  appear in a zone -- measured on home_run.jpg, where ZONE_HOME holds a runner's
  card (5) alongside the played card (7) and the tactics badge (2).

  margin_from concluded "no tactics seen" when BOTH tactics readers abstained and
  returned a bare power that feeds a margin. Two readers failing is not evidence of
  absence -- and one of them is known weak (_discs "does not reliably find a tactics
  badge at all"). The same function correctly abstains on the STRONGER evidence
  combination, so it answered on the emptier one.

  orchestrator.effective_power dropped a KNOWN non-zero bonus when the kind did not
  read, pricing it at zero and returning a number. A margin of exactly 3 is an
  automatic HOME RUN, so dropping a +2 turns one into a hit in the record.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import orchestrator as o
import reveal_cards as rc

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


FR = os.path.join(_ROOT, "test_fixtures/reveal_banner")


def frame(n):
    return Image.open(os.path.join(FR, f"{n}.jpg")).convert("RGB")


# --- 1. two card powers in a zone -> refuse ---------------------------------
# home_run.jpg: ZONE_HOME holds a runner's card (5) and the played card (7).
hr = rc.read_reveal(frame("home_run"), "batting")
check(hr["ours"]["discs"] == 3 and hr["ours"]["power"] is None,
      f"a zone holding a second CARD POWER refuses: discs={hr['ours']['discs']}, "
      f"power={hr['ours']['power']} (it used to answer 7 at score 0.983)")
check(hr["ours"].get("ambiguous") == 2,
      f"...and says how many it saw: ambiguous={hr['ours'].get('ambiguous')}")

# --- 2. THE CONTROL: a played card PLUS a tactics card still reads ----------
# This is the case that must NOT be refused, and it is the common one: a tactics
# BADGE reads 1-2, outside the 4-9 card range, so it is not a second card power.
# Without this the check above passes on a _side that refuses whenever it sees two
# discs at all -- which would silently disable the reader on every tactics play.
rcz = rc.read_reveal(frame("reveal_cards"), "batting")
check(rcz["ours"]["discs"] == 2 and rcz["ours"]["power"] == 7
      and rcz["ours"]["bonus"] == 2,
      f"CONTROL: card + tactics badge still reads fully: "
      f"discs={rcz['ours']['discs']} power={rcz['ours']['power']} "
      f"bonus={rcz['ours']['bonus']}")

m, _why = rc.margin_from(rcz, "batting")
check(m == 3, f"CONTROL: and its margin still resolves to 3 (HOME RUN), got {m}")

# --- 3. one disc IS positive evidence of no tactics card --------------------
rp = rc.read_reveal(frame("reveal_pitching"), "pitching")
m2, why2 = rc.margin_from(rp, "pitching")
check(m2 == 1 and "one disc" in why2,
      f"a single-disc zone answers, and says why: margin={m2}, {why2[:70]}")

# --- 4. ...but two discs with no kind read must NOT ------------------------
# Synthetic, because the fixtures do not contain this combination: a zone with a
# second disc where neither the badge digit nor the banner named a kind.
fake = {"ours": {"power": 7, "bonus": None, "kind": None, "discs": 2,
                 "kind_detail": "no template cleared the gate"},
        "theirs": {"power": 5, "bonus": None, "kind": None, "discs": 1,
                   "kind_detail": None}}
m3, why3 = rc.margin_from(fake, "batting")
check(m3 is None,
      f"two discs and NEITHER reader named a kind -> abstain, got {m3}")
check("not evidence" in why3,
      f"...and the reason names the mechanism: {why3[:90]}")

# --- 5. effective_power: a known bonus of unknown kind is unknown -----------
check(o.effective_power(5, 2, None) is None,
      f"a +2 whose KIND did not read abstains, got {o.effective_power(5, 2, None)} "
      "(it used to silently price it at zero and return 5)")
check(o.effective_power(5, 2, "swing_boost") == 7,
      "CONTROL: a +2 that IS a swing boost still adds power")
check(o.effective_power(5, 1, "speed_boost") == 5,
      "CONTROL: a speed boost still adds none")
check(o.effective_power(5, None, None) == 5,
      "CONTROL: no bonus at all is not an abstention — a bare power still answers")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
