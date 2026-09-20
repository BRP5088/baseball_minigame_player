"""I-01: three rows in deal_timing.jsonl are artefacts of the `_hand_signature`
shadowing bug (evening of 2026-09-20 until commit de5a79b), not measurements of deal
duration -- the deal gate saw the card move (edge_seen: true) but the shadowed helper
raised on every readable-hand poll, so it could only ever time out. A row from that
window carries no `reason` field at all (the field shipped with I-09, the fix's
sibling); a genuine post-I-09 "edge seen, never stable" row always carries
`reason: "edge_no_stable"`. `load()` must exclude exactly the pre-I-09,
edge_seen+timeout shape, count it, and leave a real timeout (with `reason`) and a
stable row alone.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
os.environ["BASEBALL_TEST_RUN"] = "1"

import deal_timing as dt

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


ARTEFACT = {"ts": "2026-09-20T17:55:04", "outcome": "timeout", "predicted_bases": 0,
            "waited": 20.15, "settled_at": None, "floor": 3.0, "threshold": 15.0,
            "biggest": 55.7, "edge_seen": True, "bases_lo": 0, "bases_hi": 4,
            "play_seq": 1, "at_the_play": "runners none batter_speed None "
            "fielding 0 bases 0..4"}
GENUINE_TIMEOUT = {"ts": "2026-09-21T09:00:00", "outcome": "timeout", "reason": "no_edge",
                    "predicted_bases": 2, "waited": 20.0, "settled_at": None,
                    "floor": 3.0, "threshold": 15.0, "biggest": 4.0, "edge_seen": False,
                    "bases_lo": 1, "bases_hi": 3, "play_seq": 2, "at_the_play": "x"}
STABLE = {"ts": "2026-09-21T09:01:00", "outcome": "stable", "reason": "stable",
          "predicted_bases": 3, "waited": 6.3, "settled_at": 0.9, "floor": 3.0,
          "threshold": 15.0, "biggest": 20.0, "edge_seen": True, "bases_lo": 2,
          "bases_hi": 4, "play_seq": 3, "at_the_play": "y"}

check(dt.is_shadow_artefact(ARTEFACT), "the artefact row was not recognised")
check(not dt.is_shadow_artefact(GENUINE_TIMEOUT),
      "a genuine post-I-09 timeout (has `reason`) was wrongly flagged as an artefact")
check(not dt.is_shadow_artefact(STABLE),
      "a stable row was wrongly flagged as an artefact")
# edge_seen alone, or timeout alone, must not be enough -- it is the COMBINATION
# with a missing `reason` that identifies the artefact.
check(not dt.is_shadow_artefact({"outcome": "stable", "edge_seen": True}),
      "a stable row with edge_seen true was wrongly flagged")
check(not dt.is_shadow_artefact({"outcome": "timeout", "edge_seen": False}),
      "a timeout with edge_seen false was wrongly flagged")

fd, p = tempfile.mkstemp(suffix=".jsonl")
with os.fdopen(fd, "w") as fh:
    for r in (ARTEFACT, GENUINE_TIMEOUT, STABLE):
        fh.write(json.dumps(r) + "\n")
rows, synthetic, malformed, artefacts = dt.load(p)
os.unlink(p)

check(artefacts == 1, f"expected exactly 1 artefact excluded, got {artefacts}")
check(len(rows) == 2, f"expected 2 live rows (genuine timeout + stable), got {len(rows)}")
check(rows[0] is GENUINE_TIMEOUT or rows[0] == GENUINE_TIMEOUT,
      "the genuine timeout row was dropped along with the artefact")
check(any(r.get("outcome") == "stable" for r in rows),
      "the stable row was dropped along with the artefact")
check(not any(r is ARTEFACT or r == ARTEFACT for r in rows),
      "the artefact row survived into the fittable set")

# report() must SAY why, not silently shrink the count (CLAUDE.md 10.22).
import io
import contextlib
buf = io.StringIO()
fd, p = tempfile.mkstemp(suffix=".jsonl")
with os.fdopen(fd, "w") as fh:
    for r in (ARTEFACT, GENUINE_TIMEOUT, STABLE):
        fh.write(json.dumps(r) + "\n")
with contextlib.redirect_stdout(buf):
    dt.report(p)
os.unlink(p)
out = buf.getvalue()
check("1 I-01 shadow-artefact" in out,
      f"report() did not announce the excluded count: {out!r}")
check("edge_seen true" in out and "reason" in out,
      f"report() did not explain WHY the row was excluded: {out!r}")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)
