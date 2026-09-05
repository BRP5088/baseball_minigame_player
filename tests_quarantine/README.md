# Quarantined tests

Empty. Nothing is quarantined right now.

## test_ban_ocr_confusion.py — released 2026-09-04, and what it actually was

Quarantined 2026-09-03 as a HANG: "zero output and does not finish", verified
at 180s buffered and 100s under `python -u`, and diagnosed from that silence as
"stuck at import or in module-level setup".

**It never hung, and it was never stuck at import.** Measured 2026-09-04:

    import orchestrator                       1.6 - 2.0 s
    the 110-cell corpus loop                 18.6 s serial, 169 ms/cell
    every pure-function / stubbed section     0.06 s combined
    the whole file, serial                   20 s idle / 49.6 s at load avg 28

`ocr_ban_card_name` calls `pytesseract.image_to_string`, which shells out — one
process spawn and one eng.traineddata load per cell, 130 cells. Process spawn is
also the part that degrades under machine load (`ocr_glyphs.py` records 5380ms
vs 1160ms for the same 40 crops on this machine), and the file was first run
beside the overnight run.

**The "zero output" carried no information about where it was.** The file's
FIRST `print` sat after all 110 corpus cells, so a kill at any point before the
end printed nothing — demonstrated 2026-09-04 by killing it at 25s in both
buffered and unbuffered mode: no output either way, identical to an import
hang. That is the CLAUDE.md pattern again — a slow step and a hung step with
the same output — and the diagnosis followed the silence instead of the clock.

The released version fixes both halves:

  * every phase prints as it completes, flushed and timestamped, so a kill
    names the phase it was in;
  * the corpus OCRs through one 8-worker thread pool (pytesseract is a
    subprocess, so the GIL is released across the spawn) — 14.97s -> 2.65s for
    the 110 cells, results checked card-by-card as identical to serial;
  * `MAX_OCR_CELLS = 130` is asserted, not merely intended, so the corpus
    cannot silently grow back into a multi-minute stall.

Runtime is now 3.7 - 4.1s at load average 20 and 14.6 - 16.2s at load average
28, against the serial file's 20s and 49.6s at the same two loads. It passes
inside `./run_tests.sh`. (No file count here on purpose: CLAUDE.md's own rule
is not to quote one, because it goes stale — this line said 87 within hours of
being written — and the script prints the real number.)
Mutation-tested: 12 mutants, 10 caught. The two that were not are equivalent
mutants (both orderings of the two matcher passes), documented in the file's
section 5 — no input distinguishes them, so no test can.

## test_early_result_double_debit.py (quarantined 2026-09-05)

Guards a fix that was ATTEMPTED AND REVERTED, so it fails against the shipped
code. It is kept because the bug it reproduces is REAL and still open.

The bug: `orchestrator.run()`'s early-result confirm gate carries
`and _scores_all_zero`. Mid-match the scoreboard is normally not 0-0, so the
clause turns the guard off for exactly the window it was built to cover. One
non-zero "result" misread then clears `match_in_progress`, and the next overlay
misread as `match_start_prompt` passes C5 and debits a SECOND $50 — $100 for one
match, a fabricated win in the record, and two `\` keystrokes into a live match
(`start_match` shares its key with `confirm_discard`).

Why the fix was reverted: dropping the clause makes the confirm gate fire on far
more polls than intended and desynchronises the run loop — 23 checks in
tests/minigame/test_run_state_machine.py went red (motion gate, last_phase
carry-over, clean-stop diagnostics). The state machine is timing-coupled in ways
the guard's author did not anticipate, so this is not a two-word deletion.

What a real repair probably looks like: gate the DEBIT on evidence that a match
genuinely ended, rather than re-reading after every result-shaped screen. Note
the tradeoff — `at_table()` answers False when it fails, so requiring it before a
debit would stall a legitimate one instead of misfiring.

Run it directly to reproduce:
    BASEBALL_TEST_RUN=1 .venv/bin/python tests_quarantine/test_early_result_double_debit.py
