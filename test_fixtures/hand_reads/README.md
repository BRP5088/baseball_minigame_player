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
