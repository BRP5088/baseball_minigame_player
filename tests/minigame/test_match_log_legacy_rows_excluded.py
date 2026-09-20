"""I-18a: outcome statistics must exclude rows with no `outcome_basis` by default.

369 of 373 real rows in match_log.jsonl predate `classify_outcome` and carry no
`outcome_basis` at all -- their `outcome` field is the withdrawn "score went up"
classifier's opinion (CLAUDE.md section 4: "26 such rows ... all came from the
old ... classifier"). analyze_match_log.py and tactics_effect.py both report
win rates / outcome tallies off `outcome`, so both must drop those rows by
default and accept `--include-legacy` to put them back.

WHAT MUST NOT BE EXCLUDED. `effective_power` (and therefore the margin/
secondary permutation test) reads `*_power`/`*_tactics_bonus`/`*_tactics_kind`,
never `outcome` -- the same local reader in every era (CLAUDE.md section 3) --
so a legacy row with usable power fields must still count toward THAT analysis.
Excluding it too would throw away 369 rows of a question they can still answer.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import analyze_match_log as aml
import tactics_effect as te

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


# Two rows from before classify_outcome existed (no outcome_basis key at all,
# matching the real file exactly -- not `"outcome_basis": null`) and two from
# after it landed, one on each basis classify_outcome can produce.
LEGACY_1 = {"phase": "batting", "our_power": 7, "opp_power": 5,
           "our_tactics_bonus": 0, "opp_tactics_bonus": 0,
           "our_tactics_kind": "fielding_boost", "opp_tactics_kind": None,
           "our_secondary": 2, "outcome": "home_run"}
LEGACY_2 = {"phase": "pitching", "our_power": 6, "opp_power": 6,
           "our_tactics_bonus": 0, "opp_tactics_bonus": 0,
           "our_tactics_kind": None, "opp_tactics_kind": None,
           "our_secondary": 1, "outcome": "out"}
MODERN_1 = {"phase": "batting", "our_power": 8, "opp_power": 5,
           "our_tactics_bonus": 0, "opp_tactics_bonus": 0,
           "our_tactics_kind": None, "opp_tactics_kind": None,
           "our_secondary": 3, "outcome": "hit", "outcome_basis": "margin"}
MODERN_2 = {"phase": "pitching", "our_power": 5, "opp_power": 5,
           "our_tactics_bonus": 0, "opp_tactics_bonus": 0,
           "our_tactics_kind": None, "opp_tactics_kind": None,
           "our_secondary": 0, "outcome": "tie_win", "outcome_basis": "tie"}

ROWS = [LEGACY_1, LEGACY_2, MODERN_1, MODERN_2]


def _write_log(rows):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for r in rows:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


path = _write_log(ROWS)
try:
    print("1. has_outcome_basis: legacy rows are missing the key, not None")
    check(aml.has_outcome_basis(LEGACY_1) is False, "LEGACY_1 has no outcome_basis")
    check(aml.has_outcome_basis(MODERN_1) is True, "MODERN_1 has outcome_basis 'margin'")
    check(aml.has_outcome_basis(MODERN_2) is True, "MODERN_2 has outcome_basis 'tie'")

    print("\n2. analyze_match_log.load() itself does NOT filter -- all 4 come back")
    rows, synthetic, bad = aml.load(path)
    check(len(rows) == 4 and synthetic == 0 and bad == 0,
          f"load() returns all 4 genuine rows (got {len(rows)})")

    print("\n3. main(include_legacy=False): outcome stats see only the 2 modern rows")
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        aml.main(path=path, include_legacy=False)
    out = buf.getvalue()
    check("2 legacy rows" in out, f"names the count excluded (got: {out!r:.200}")
    check("outcome-eligible rows: {'hit': 1, 'tie_win': 1}" in out,
          "the outcomes tally is ONLY the 2 modern rows, not home_run/out too")
    check("home_run" not in out.split("outcomes")[1].split("\n")[0],
          "the legacy home_run never reaches the printed outcome tally")
    check("BASELINE (outcome-eligible rows only) — always predict" in out,
          "the baseline line says it is scoped to outcome-eligible rows")

    print("\n4. main(include_legacy=True): all 4 rows count toward outcomes")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        aml.main(path=path, include_legacy=True)
    out2 = buf2.getvalue()
    check("INCLUDED (--include-legacy)" in out2, "says legacy rows were put back")
    check("'home_run': 1" in out2 and "'out': 1" in out2 and "'hit': 1" in out2
          and "'tie_win': 1" in out2,
          f"all four outcomes appear once each (got: {out2!r:.300}")

    print("\n5. legacy rows STILL count toward the powers-only margin/secondary "
          "analysis, in BOTH modes -- that half never reads `outcome`")
    check("usable for analysis (margin/secondary, powers-only, legacy "
          "included): 4/4" in out,
          "all 4 rows (2 legacy + 2 modern) are usable for margin/secondary "
          "with --include-legacy OFF")
    check("usable for analysis (margin/secondary, powers-only, legacy "
          "included): 4/4" in out2,
          "and the same 4/4 with --include-legacy ON -- this analysis does "
          "not move with the flag at all")

    print("\n6. tactics_effect.py's win_rate() is entirely outcome-based, so it "
          "must drop the legacy rows too by default")
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        te.main(path=path, include_legacy=False)
    out3 = buf3.getvalue()
    check("2 legacy rows" in out3 and "EXCLUDED" in out3,
          "tactics_effect names the exclusion in its own printed line")
    # NOT VACUOUS (CLAUDE.md's check() lesson): the line above is printed by a
    # branch that could fire even if the filter it describes never ran, so
    # assert on the ACTUAL effect too -- LEGACY_1 is the only row carrying
    # our_tactics_kind="fielding_boost", and it must disappear from the
    # COVERAGE listing (built only from the rows that survived the filter)
    # once legacy rows are dropped. The win-rate table below it always prints
    # a "fielding_boost" ROW LABEL for all four known kinds regardless of
    # data, so checking the whole output for the string would pass vacuously.
    _coverage = out3.split("our_tactics_kind coverage:")[1].split("\n\n")[0]
    check("fielding_boost" not in _coverage,
          f"the legacy-only tactics kind (fielding_boost, from LEGACY_1) is "
          f"gone from the coverage LISTING, not just claimed gone in prose "
          f"(coverage section: {_coverage!r})")
    check("2 of 2 rows have NO tactics_kind" in out3,
          "the coverage table's own row count reflects 2 rows, not 4 "
          f"(got: {out3.splitlines()[4] if len(out3.splitlines()) > 4 else out3!r})")

    buf4 = io.StringIO()
    with contextlib.redirect_stdout(buf4):
        te.main(path=path, include_legacy=True)
    out4 = buf4.getvalue()
    _coverage4 = out4.split("our_tactics_kind coverage:")[1].split("\n\n")[0]
    check("fielding_boost" in _coverage4,
          "--include-legacy puts LEGACY_1's fielding_boost back in the "
          f"coverage listing (got: {_coverage4!r})")
finally:
    os.unlink(path)

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
