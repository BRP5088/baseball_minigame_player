# Quarantined tests

**Empty.** Nothing is quarantined right now, and the directory holds no test
files — check with `ls` before believing this line, because it has been wrong
before.

## What this directory is for

A test that cannot run — a genuine hang, a missing dependency, a fixture that no
longer exists — is moved here rather than deleted, so the reason survives. A
quarantined test is a test that is NOT protecting anything, so each one is debt
with a name.

## test_early_result_double_debit.py — released 2026-09-05

Quarantined on 2026-09-05 and released the same day. It was never broken: it
passes against shipped code, and the README claim that it "fails against shipped
code" was wrong.

Worse than wrong — it guards the `match_in_progress` double-debit path, where a
stale flag makes orchestrator press `start_match` believing the $50 was already
paid: the money leaves the in-game wallet, `balance` is never debited, and
`max_spend` cannot stop it. A **money guard, sitting outside the suite, described
as failing.** It now lives at `tests/minigame/test_early_result_double_debit.py`
and runs on every `./run_tests.sh`.

## test_ban_ocr_confusion.py — released 2026-09-04, and what it actually was

Quarantined 2026-09-03 as a HANG: "zero output and does not finish", verified at
180s buffered and 100s under `python -u`, and diagnosed from that silence as
"stuck at import or in module-level setup".

**It never hung, and it was never stuck at import.** Measured 2026-09-04: it
takes 49.6s, and its first `print` sits after all 110 cells. A slow step and a
hung step had identical output, which is CLAUDE.md's catalogue exactly.

## The rule this directory keeps breaking

Do not describe what is in here from memory. Twice now this README has claimed
the directory was empty while it held a test, and once it claimed a passing test
failed. `ls tests_quarantine/` is the authority.
