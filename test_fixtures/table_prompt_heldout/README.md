# Held-out table-prompt frames, from BOTH recordings

Copied 2026-09-17 from demos/ (gitignored, so absent on a fresh clone). The time
windows and the [::40] stride the test used to apply are ALREADY APPLIED here.

BOTH recordings on purpose: using one traversal taught the detector a single viewing
angle, and it then rejected genuine table frames from the other recording --
including one where the prompt is plainly legible. They are the guard against
at_table() recognising only the exact frames it was built from.
