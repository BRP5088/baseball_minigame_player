Ban-grid reference frames for tests/test_ban_scan.py (FRAMES[0] becomes `_REAL`).

Recaptured 2026-09-01 from screenshot_log/run_20260828_140236 after the original
2026-08-24 fixtures were pruned along with their run directory, which left this
file raising SystemExit and the ban-scan coverage entirely disabled.

Chosen by LOOKING at them: both read "BANNED CARDS 0/3" with card names legible
(JOHNNY DRAWERS, MAMA JODY GAIN, JOSHUA DIAZ ...) and greyed locked slots
present, which is what the grid reader has to cope with. They are window
captures at 1920x1080 — NOT the older full-display frames in ban_counter/, which
include the Mac menu bar and Dock and so put every region fraction in the wrong
place.
