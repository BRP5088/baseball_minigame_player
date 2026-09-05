"""Trial records must be queryable, and must never break a run.

WHY THIS EXISTS. Every analysis on this project has meant grepping prose logs
written for humans — counting "abandoning the rest of this leg", parsing
"arrived=False (located None, 4 step(s) walked, ABANDONED, 2 stall event(s))".
That works once. Comparing two runs means a new regex; comparing against last
week means hoping the wording did not drift.

Two properties matter more than the format:

 1. An INVALID trial (arrived=None) must never be counted as a failure. CLAUDE.md
    rule 6 — CANNOT SEE is not DID NOT ARRIVE — and conflating the two already
    invalidated a whole A/B here.
 2. Recording must never raise. A harness that dies while writing a result is
    worse than one that records nothing: it destroys the trial it was measuring.
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
sys.path.insert(0, os.path.join(_ROOT, "overnight"))
os.environ["BASEBALL_TEST_RUN"] = "1"

import _harness as h

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


TMP = tempfile.mkdtemp(prefix="trials_")
P = os.path.join(TMP, "trials.jsonl")

h.record_trial(P, "exp", "A", 1, arrived=True, stall_events=0, seconds=90.0)
h.record_trial(P, "exp", "A", 2, arrived=False, stall_events=2, seconds=88.0,
               abandoned=True)
h.record_trial(P, "exp", "A", 3, arrived=None, invalid_reason="stream dead")
h.record_trial(P, "exp", "B", 1, arrived=True, stall_events=0, seconds=100.0)

rows = h.load_trials(P)
check("every trial is recorded", len(rows) == 4)
check("each row carries a schema version", all(r.get("v") == 1 for r in rows))

s = h.summarise(rows, experiment="exp")

# --- the denominator must EXCLUDE invalid trials -------------------------
check("arm A counts 2 valid trials, not 3", s["A"]["valid"] == 2)
check("and reports the invalid one separately", s["A"]["invalid"] == 1)
check("an INVALID trial is not counted as an arrival", s["A"]["arrived"] == 1)
# The trap: 1/3 would read as a 33% arrival rate when it is 50% of what was
# measurable. Rates over the wrong denominator have misled this project before.
check("so the rate is over VALID trials", s["A"]["arrived"] / s["A"]["valid"] == 0.5)

check("abandonment is carried through", s["A"]["abandoned"] == 1)
check("stall events are summed", s["A"]["stall_events"] == 2)
check("arms are kept separate", s["B"]["valid"] == 1 and s["B"]["arrived"] == 1)

# --- recording must never raise ------------------------------------------
try:
    h.record_trial("/nonexistent\x00/bad/path.jsonl", "e", "a", 1, arrived=True)
    raised = False
except Exception:
    raised = True
check("an unwritable path does NOT raise into the trial", not raised)

# --- a corrupt row must not destroy the file -----------------------------
with open(P, "a") as fh:
    fh.write("{not json at all\n")
h.record_trial(P, "exp", "A", 4, arrived=True, seconds=91.0)
rows2 = h.load_trials(P)
check("a corrupt line is skipped, not fatal", len(rows2) == 5)
check("and rows after it still load",
      any(r.get("trial") == 4 for r in rows2))

# --- experiment filtering ------------------------------------------------
h.record_trial(P, "other", "A", 1, arrived=False)
check("summarise filters by experiment",
      h.summarise(h.load_trials(P), experiment="exp")["A"]["valid"] == 3)

import shutil
shutil.rmtree(TMP, ignore_errors=True)
print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
