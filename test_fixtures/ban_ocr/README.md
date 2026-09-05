Ban-grid name-banner OCR fixture for tests/test_ban_ocr_confusion.py.

One frame, copied here 2026-09-03 from
`screenshot_log/run_20260828_140236/20260828_140320_608.jpg` so the test does
not depend on a log directory the screenshot pruner deletes oldest-first — the
same reason test_fixtures/ban_scan/ exists (see its README).

Why this frame and not another: it is the only cached capture showing the grid
with a card ALREADY BANNED — "BANNED CARDS 1/3", with the ban X drawn across
Donny Mekesz at (0,4). That overlay clips the first letters of the banner, and
its read ("NNY MEKESZ") is the corpus's clearest example of the leading-letter
loss in the measured confusion table. It is a window capture at 1920x1080.

The rest of the OCR corpus is the ban frames already at test_fixtures/ root
(20260824_2005*), test_fixtures/ban_scan/ and test_fixtures/ban_counter/.
