# hand_reads fixtures

## i22_pitch_boost_slot3_turn1.png / i22_pitch_boost_slot3_turn4.png (I-22)

Source: `overnight/run_live_20260920d.log`, the live run's pitching half. After
"discarding the weakest (power 5)" at slot 3, the redeal into slot 3 read as
`3: UNKNOWN` for four consecutive turns before finally reading `pitch_boost +1`.
Frames pulled from the (gitignored) `diagnostics/deal_frames/` dump `local_hand_cards`
writes when a slot is dropped:

    turn1  diagnostics/deal_frames/dropped_1789948008009552000/hand.png
    turn4  diagnostics/deal_frames/dropped_1789948058815785000/hand.png

Both are the SAME physical card (pairwise banner correlation 0.996-0.997 across all
four captured turns -- one real-world example, sampled repeatedly, per CLAUDE.md
10.22), sitting unplayed in slot 3 while other slots were played around it. The
card is plainly legible to a human eye ("PITCH FOCUS", bonus digit "1" in the top
corner) and `read_bonus` already read it correctly (bonus=1, score 0.92-0.94) on
every one of the four turns -- only `read_tactics_type`'s TYPE score fell short
(0.755-0.764 against `MIN_TYPE_SCORE` 0.85), so `local_hand_cards` dropped the
whole card as unreadable.

Root cause: this card's disc lands at x=642 in the 979-wide crop, well left of the
~661-664 cluster the shipped `tactics_templates.npz` bank's pitch_boost examples
were cut from (measured: `overnight/local_hand/*.png`'s slot-3 pitch_boost cards
score 0.97 mean against the bank; this card's own crop correlates only 0.28
against one of those). Not an occlusion (10.28/10.34 do not apply -- nothing
covers the card) and not a timing/settle issue (the score is identical, to three
decimal places, across four polls spanning tens of seconds) -- a genuine
bank-coverage gap, the same shape commit 83a4a73 fixed for FIELDING PLAY at slot 3
("the bank had never seen it there").

Both frames must read: slot 3, kind=tactics, type=pitch_boost, bonus=1,
type_score >= 0.85.

`turn1` is also a DONOR in `tools/build_hand_tactics_templates.py`'s `DONORS`
list. `turn4`, captured ~50s later after further turns, is kept OUT of the donor
list so `test_i22_pitch_boost_slot3.py` has one independent frame the fix was
never trained on.

## i38_occluded_target_1.png / i38_occluded_target_2.png / i38_occluded_target_3.jpg (I-38)

Found by an archive search (`agent_progress/census/archive_search/`, 2026-09-21):
a local pre-filter over `screenshot_log/`, `overnight/`, `diagnostics/` flagged
1,041 frames where `read_hand` returned a 5-row fan with exactly one `kind ==
"player"` row reading `digit is None`; 60 were sampled and shipped to Snoopy's
Qwen3-VL-8B (`unsloth/Qwen3-VL-8B-Instruct-GGUF` via llama-server) asking which
position's disc looked covered. **The VLM agreed with `read_hand`'s flagged slot
on only 9/60 (15%)** -- consistent with Snoopy_testing.md's own finding that this
model gets "which card is raised" wrong. Ten candidates were then opened and read
by eye; only 2 of 7 non-animation candidates checked showed genuine physical
occlusion (a neighbour's edge covering the disc) -- the other 5 were RAISED/
SELECTED cards whose disc was plainly visible on screen but still read `digit:
None` (the brightened-disc-defeats-DARK_THRESHOLDS gap CLAUDE.md 10.23 already
covers, not occlusion). These three are the genuine occlusion frames:

    1: source diagnostics/20260920_212312_9400/after_stall_0.png
    2: source overnight/crawl/20260910_140253/001.png
    3: source screenshot_log/run_20260921_080311/20260921_081329_809.jpg

**#1 and #2** are the same shape from two different matches (2026-09-20 and
2026-09-10): a tight five-BATTER-card fan where slot 1 (leftmost) is tucked
almost entirely under slot 2's left edge -- only a sliver of "BATTER" text and
art survives, the disc itself off-frame under the neighbour. `read_hand` on both:
slot 0 `kind=player digit=None y_from=disc` (a circle WAS found, but weak/wrong --
score 0.149-0.315), slots 1-4 all read cleanly. Readable powers: #1 is
`[None, 4, 4, 4, 5]` (best readable play: slot 5, power 5); #2 is
`[None, 4, 4, 4, 8]` (best readable play: slot 5, power 8). In neither case can
the occluded slot's true power be ruled IN or OUT as the actual best card --
that is exactly I-38's shape, decision_engine was never run against these
(no runner/phase state available from a static frame); only the readable powers
are reported here.

**#3** is a different mechanism: a mid-DEAL-animation frame, one card
("William Brown", BATTER 4/3, still semi-transparent) caught flying in directly
on top of slot 3, covering the card underneath. `read_hand`: slot 0 reads
5/3(secondary), slot 1 is itself unresolved (`kind=tactics type=None
y_measured=False` -- also mid-animation), slot 2 `kind=player digit=None
y_from=fallback` (the occluded one), slots 3-4 read 5/3. This is a transient
state the settle gate (CLAUDE.md's "wait for quiet, twice running", section 3's
"THE CAPTURE MOMENT" entry) should poll past rather than a steady stuck hand, so
it is a different -- and probably self-resolving -- case from #1/#2; kept as the
third fixture because it is a real, distinct occlusion mechanism (a dealt card
over its target, not a neighbour's steady-state overlap), not because it is
equally hard to recover from.
