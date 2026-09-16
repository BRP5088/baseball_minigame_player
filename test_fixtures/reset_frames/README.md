# Pause-menu and reset frames — the NEGATIVE half of the in_gameplay gate

Copied out of `screenshot_log/` 2026-09-17, which is GITIGNORED *and* pruned
oldest-first by the orchestrator: these were going to disappear twice over.

All eight that exist: reset_pause x2, reset_down x1, reset_confirm x1,
reset_facing_ x4. `test_turn_control` asserts in_gameplay() is FALSE on the first
four -- a pause frame read as gameplay means the reset ladder presses into a menu.

The reset_facing_ four are 2000x1292 WHOLE-DISPLAY grabs from a capture path that no
longer exists; the file's own comment explains why they are kept separate and not
used for the reticle constant.
