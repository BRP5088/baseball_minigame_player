# Two ban-screen frames showing the TACTICS section

Copied out of `screenshot_log/run_20260828_135528/` on 2026-09-17.

WHY THEY HAD TO MOVE. `screenshot_log/` is GITIGNORED and the orchestrator prunes
it oldest-first, so these frames do not exist for anyone who clones this repo and
will eventually not exist here either. The test that reads them guarded itself with
`if TACTICS_FRAMES:` -- so when they vanished the whole section simply did not run
and the file still exited GREEN. Measured by hiding screenshot_log/ and re-running:
test_ban_ocr_confusion.py PASSED with no corpus at all.

That is the shape CLAUDE.md calls this project's signature: a success path and a
no-op path with identical output. And it was guarding the BAN path, which spends
$50 a match.

WHAT THEY PROVE: the ban scan's early stop ("no player names readable AND past the
known roster") rests on tactics cards OCR'ing to nothing. That claim is asserted
over these real frames rather than over strings, because the crop geometry is half
of it.
