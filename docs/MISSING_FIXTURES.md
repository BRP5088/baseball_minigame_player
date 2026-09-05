# Fixtures I deleted, and what it costs

While clearing 1.3 GB of stale frame dumps from `screenshot_log/` I also deleted
frames that two tests used as fixtures. That was my mistake. This records the
damage honestly and what is needed to undo it.

## Why it happened

`test_ban_scan.py` and `test_gameplay_regions.py` read their reference frames
out of `screenshot_log/` — a directory the orchestrator prunes during normal
operation. Both tests even carry comments anticipating this ("orchestrator
prunes screenshot_log/, so a green suite..."), and both correctly refuse to skip
silently when the frames vanish. They were right; the arrangement was wrong.

Both now read from `test_fixtures/`, which nothing prunes.

## Recovered

Nothing. I tried, and the attempt is worth recording because it was wrong.

I substituted frames of the TABLE prompt ("Baseball Cards [] Play ($50)") taken
from the walk recording, plus two live office frames. Both tests then failed
differently and I looked at what they actually assert:

`test_gameplay_regions.py` is not about the table prompt at all. Its
`_PROMPT_VISIBLE` frames are the IN-MATCH play prompt, and its `_PROMPT_ABSENT`
frames are BAN SCREENS — which contain the same "PLAY" text riding a moving
cursor. The whole point is that the fixed gameplay box must fire on one and not
the other. Office frames cannot fail that check, so they would have made the
test pass while proving nothing — the exact vacuous-fixture failure this repo
already documented in QA_VACUOUS.md. The substituted frames were deleted again.

## Still missing

Both sets can only be captured from INSIDE a match, which requires pressing BOX
at the table and spending $50 of in-game money. They are therefore blocked on a
match being played for some other reason — not on the route work.

* **`test_fixtures/prompt_detector/`** — three frames showing the in-match PLAY
  prompt (`20260824_200915_662.jpg`, `_200917_668.jpg`, `_200918_673.jpg`) and
  two BAN SCREEN frames that must not trigger it (`20260824_200458_664.jpg`,
  `_200504_992.jpg`).

* **`test_fixtures/ban_scan/`** — ban-screen frames (was
  `screenshot_log/20260825_1659*`).

Until then both tests fail loudly rather than skipping, which is correct. Do not
"fix" them with any frame that happens to be handy — a detector test that passes
on the wrong fixtures is worse than one that fails.

Both tests fail rather than skip until the frames exist. Do not "fix" them by
loosening that check — a detector test that reports success on zero frames is
how this went unnoticed the first time.
