# live/ — reveal frames kept as the rig plays, labelled by what the engine chose

**The recorder writes to `../auto/` now, not here (2026-09-20).** The frames in this
directory are hand-adjudicated: `tests/minigame/test_reveal_kind_live_fixtures.py`
names all five, two of them supplied templates, and the census carries an exclusion
list for those two — so an unattended run appending to this directory would bury a
curated set in frames nobody has looked at. `orchestrator.record_reveal_kind` writes
one frame per turn where WE played a tactics card, named `<kind>_<ns>.jpg`, into
`../auto/`, and stamps that path into the match_log row as `reveal_frame`. Everything
below is why it exists and how to score it, and applies to both directories.

WHY IT EXISTS (OPEN-24). `reveal_cards.TACTICS_KIND_MIN` (0.75) gates the
tactics-KIND reader and stands on the 48 frames in `../reveal6/` and `../reveal/`
— two matches. `match_log.jsonl` already holds 148 rows of ground truth, because
`our_tactics_kind` is `decision.tactics_card.kind`, the card this code chose and
played. None of those 148 has a surviving frame: `SCREENSHOT_KEEP_RUNS` is 3, so
the append-only row outlives the picture. The log remembered what we played and
the disk forgot what it looked like.

THE LABEL IS NOT CIRCULAR (CLAUDE.md 10.22). The opponent's kind is READ by the
same reader this corpus scores — and carries the bonus-of-3 values RULES.md says
cannot exist — so only OUR side is written here.

RATE, measured over 369 logged turns: we play a tactics card on 40% of them, ~4 a
match, 273 KB a frame — about 1 MB per match. The distribution is lopsided and
the rare classes are the ones this will NOT fix quickly: swing_boost 82,
pitch_boost 52, fielding_boost 8, speed_boost 6. `../reveal6/` and `../reveal/`
still cover fielding and speed best (25 and 23 frames).

SCORING. `tools/banner_kind_census.py` holds the exclusion list for the five
frames that supplied templates — a template matches its own source at 1.000
(10.30). Add any frame from here to a scoring run only as HELD-OUT data.
