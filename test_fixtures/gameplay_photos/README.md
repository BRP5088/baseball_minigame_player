# gameplay_photos

Fifteen full gameplay screenshots from 2026-08-23, read by three tests:
`test_gameplay_regions`, `test_ocr_scoreboard`, `test_ocr_runner`.

They lived in `Photos to train on/` at the project root until 2026-09-05 — a
name from an era before there were any captured frames to work from.
`docs/TEST_SUITE_AUDIT.md` had already flagged the arrangement: three tests
depending on a directory that was not a fixture directory, so a copy of the
project without it silently lost their coverage.

They are versioned deliberately, despite being 84M. A test whose data is not
committed is a test that cannot be run from a fresh clone, and this suite's
whole value is that it runs offline anywhere.
