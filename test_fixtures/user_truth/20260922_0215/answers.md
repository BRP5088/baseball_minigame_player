# User truth: five refused-select frames, 2026-09-22 02:15 sheet

Ground truth answered by the user (Brett Patterson), watching the real PS5 screen,
against the `diagnostics/questions/20260921_2307/` contact-sheet questions. Slots
are 0-4 left to right. This directory is the tracked archive of that answer session;
`agent_progress/issues/user-answers-20260922/progress.md` (untracked, gitignored)
carries the working notes and scratch scripts behind the numbers below.

## The user's answers, verbatim

    Q2  refused_select_1790026023456048000  user: slot 3 has the cursor, NOT selected (no glow); PITCHER, power 9, fielding 2
    Q3  refused_select_1790029233140573000  user: slot 1 lifted, cursor looks like it is on slot 1; BATTER, power 5, movement (speed) 3
    Q6  refused_select_1790029942849538000  user: slot 4 lifted AND selected; BATTER, power 8, movement 1
    Q17 refused_select_1790041074877095000  user: slot 0 has the cursor; PITCHER, power 7   (the question had asked about slot 1)
    Q19 refused_select_1790042607981357000  user: slot 0 selected; BATTER, power 7, movement 1   (the question had asked about slot 3)

Also from the user: hand-card NAMES are cropped by the PS5 display itself, not by
the engine's crop (so a missing/partial name on any card is a game-rendering fact,
not a reader defect).

## Mapping Q-numbers to frames (why this table exists)

The task's "Q" numbers do not match the `Q` column in the current on-disk
`diagnostics/questions/20260921_2307/questions.json` (that file numbers ALL rows,
refused-select and dropped-slot interleaved, 1-93). Re-deriving the user's
numbering: filtering to refused-select rows only and numbering them 1..18 in
file order reproduces the task's Q-numbers with a constant **+2** offset for
every frame that exists in the current file:

    file's refused-only index 1  (frame ...140573000, abs Q2)  -> task Q3
    file's refused-only index 4  (frame ...849538000, abs Q14) -> task Q6
    file's refused-only index 14 (frame ...764460000, abs Q68) -> task Q16 (Fable's addendum)
    file's refused-only index 15 (frame ...877095000, abs Q70) -> task Q17
    file's refused-only index 16 (frame ...558827000, abs Q72) -> task Q18 (Fable's addendum)
    file's refused-only index 17 (frame ...981357000, abs Q74) -> task Q19

Task's Q2 (frame `refused_select_1790026023456048000`, directory mtime 17:27) is
**not present anywhere in the current 93-row sheet** -- established by grepping
`questions.json` for the ns and finding no match. Its offset (+2, i.e. it would
be "refused-only index 0", before the sequence starts) and its earlier directory
timestamp (17:27, before the current sheet's earliest refused-select row at
18:20:33) are consistent with one story: it is an older refused-select frame
from before whatever `--since` cutoff produced the current 23:07 regeneration,
already pruned from that file. ESTABLISHED: absence from the current sheet, and
the timestamp ordering. ASSUMED: the "why it was pruned" story (plausible, not
directly verified against `questions_sheet.py`'s `--since`/dedupe behaviour with
a live run).

## Per-field comparison: engine-at-refusal (why.json) vs local readers (now, offline) vs user

Readers run offline against `hand.png` with `BASEBALL_TEST_RUN=1`:
`local_hand.cursor_glow(img)` for cursor + rows, `local_hand.selected_cards(rows, scale)`
for selection. `scale = img.width / local_hand.ANCHOR_W`; all five images are
979x307, so `scale = 1.0` throughout.

### Q2 -- refused_select_1790026023456048000 (why.json: target=3, kind=player, already_selected=[])

| field | engine-at-refusal | reader (now) | user | verdict |
|---|---|---|---|---|
| cursor slot | (not recorded in why.json for this shape) | 3 (glow=26.9) | slot 3 | RIGHT |
| slot 3 selected? | not selected (target, no already_selected) | `selected_cards`=[] | NOT selected | RIGHT |
| slot 3 power (digit) | -- | '9' (score 0.940) | 9 | RIGHT |
| slot 3 secondary | -- | 2 (score 0.889) | fielding 2 | RIGHT |

All RIGHT. (`kind` from the reader is generic "player"/"tactics", not
batter/pitcher; secondary=2 is in the pitcher-only 0/1/2 range per CLAUDE.md's
role-split census, consistent with the user's PITCHER call but not an
independent field to score.)

### Q3 -- refused_select_1790029233140573000 (why.json: target=1, kind=player, already_selected=[1])

| field | engine-at-refusal | reader (now) | user | verdict |
|---|---|---|---|---|
| cursor slot | target=1 (engine was trying to select 1) | 1 (glow=25.4) | slot 1 | RIGHT |
| slot 1 selected? | already_selected=[1] | `selected_cards`=[1] | lifted | RIGHT |
| slot 1 power | -- | '5' (score 0.979) | 5 | RIGHT |
| slot 1 secondary | -- | 3 (score 0.891) | movement/speed 3 | RIGHT |

All RIGHT.

### Q6 -- refused_select_1790029942849538000 (why.json: target=4, kind=player+tactics, already_selected=[0,4])

| field | engine-at-refusal | reader (now) | user | verdict |
|---|---|---|---|---|
| slot 4 selected? | already_selected includes 4 | `selected_cards`=[0,4] | lifted AND selected | RIGHT |
| slot 4 power | -- | '8' (score 0.968) | 8 | RIGHT |
| slot 4 secondary | -- | 1 (score 0.890) | movement 1 | RIGHT |
| cursor slot | target=4 | 0 (glow=22.1) | not asked | n/a (reader says cursor is on slot 0, not slot 4 -- consistent with "already_selected=[0,4], target=4": the cursor had moved on to slot 0 by the time of refusal; not something the user was asked to confirm) |

All checkable fields RIGHT.

### Q17 -- refused_select_1790041074877095000 (why.json: target=0, kind=player, already_selected=[], attempt=2)

| field | engine-at-refusal | reader (now) | user | verdict |
|---|---|---|---|---|
| cursor slot | target=0 | **None** (glow[0]=28.2, well above CURSOR_GLOW_MIN=10.0, but excluded from the argmax pool -- see below) | slot 0 | **WRONG/ABSTAINED** |
| slot 0 power | -- | **None** (score 0.743, digit unread) | 7 | **WRONG/ABSTAINED** |
| slot 0 secondary | -- | 0 (score 0.340) | not stated | n/a |

**This is a genuine reader disagreement, not a sheet/label issue.** Raw glow for
slot 0 is 28.2%, comfortably inside `cursor_slot`'s own documented true-cursor
band (20.7-36.1) and above `CURSOR_GLOW_MIN` (10.0). But `cursor_glow`'s
eligibility mask (`local_hand.py:1460-1464`) zeroes any row where
`y_from == "disc"` and `digit is None` -- row 0 here is exactly that
(`y_from='disc'`, `digit=None`, `score=0.743`) -- so the highest raw glow on the
frame is discarded before the argmax runs, and `cursor_slot` returns `None`
instead of 0.

The digit itself is a near-miss: `read_digit`'s score for slot 0 is 0.743
against `MIN_SCORE` 0.80 (score cited in `local_hand.py`'s raised-card
commentary), so it never clears the gate. The neighbouring attempts on the
**same hand**, 3s before and 4s after, both read it cleanly:
`refused_select_1790041071764460000` (attempt 1, 21:37:51): digit='7',
score=0.954. `refused_select_1790041078558827000` (attempt 3, 21:37:58):
digit='7', score=0.988. So this is a transient miss on one frame in the middle
of a 3-attempt retry sequence (likely a card still settling mid-animation),
not a stable misread -- but it did leave the engine's OWN `probe_attempts`
history at this exact frame showing a stale `selected: [4]` from attempt 1
(see why.json), i.e. the engine's cursor tracking was also confused on this
attempt, independently of the offline re-read here.

**Q17/Q19 finding (task step 2):** the task states the original question this
frame was shown under had asked about "slot 1". `why.json`'s own `target` for
this exact frame is **0**, and the user's independent answer, reading the
picture, is **slot 0**. The engine's belief (target=0) and the user's
observation (slot 0) **AGREE**; it is the number the ORIGINAL question label
carried (1) that was wrong, not the engine's slot selection. The current
on-disk `diagnostics/questions/20260921_2307/questions.json` already shows
`"slot": 0` for this frame (row Q70), so whatever produced the wrong "slot 1"
label the user actually answered against is not reproducible from what is on
disk now -- either it was already fixed by the time this sheet was
regenerated, or the user was shown a different rendering. Not guessed at
further than that.

### Q19 -- refused_select_1790042607981357000 (why.json: target=0, kind=player+tactics, already_selected=[0])

| field | engine-at-refusal | reader (now) | user | verdict |
|---|---|---|---|---|
| slot 0 selected? | already_selected=[0] | `selected_cards`=[0] | selected | RIGHT |
| slot 0 power | -- | '7' (score 0.993) | 7 | RIGHT |
| slot 0 secondary | -- | 1 (score 0.900) | movement 1 | RIGHT |
| cursor slot | target=0 | 3 (glow=23.9) | not asked | n/a (reader says the cursor itself is on slot 3, a tactics speed_boost card, while the SELECTED card is slot 0 -- not contradictory, just not what the user was asked) |

All checkable fields RIGHT.

**Q17/Q19 finding, second half:** the task states this frame's original question
asked about "slot 3". `why.json`'s `target` is **0**, and the user's answer is
**slot 0 selected**. Same conclusion as Q17: the engine's belief (target=0,
already_selected=[0]) **AGREES** with the user's observation; the original
question's slot label (3) was wrong. Note slot 3 in this same frame IS a real
card (a tactics `speed_boost`, per the reader) and also happens to be where the
reader currently places the cursor -- a plausible source for how a "slot 3"
label got attached to this frame by whatever generated the original question
text, though that is not established, only plausible.

## Summary

18 of 20 checkable fields across the five frames: RIGHT. 2 of 20 (Q17's cursor
slot and Q17's power digit): WRONG/ABSTAINED by the reader, both explained by
one mechanism (the digit-unread exclusion in `cursor_glow`'s eligibility mask
combined with a `read_digit` score of 0.743 falling just under `MIN_SCORE`
0.80) on a single transient frame bracketed by two clean reads of the same
card. No case was found where the reader confidently reported something WRONG
that the user contradicts -- every disagreement is the reader abstaining
(`None`) where the user could see the answer, which is the safe-direction
failure this project's local readers are built to prefer.

Both Q17 and Q19 confirm the engine's own `target` belief in why.json was
CORRECT and matched the user's independent observation; the mismatch was in
the slot number named by the original question text the user was shown, not
in the engine's slot-selection logic.

## Addendum: slot-box cropping on Q16-Q19 (frames with 21:37 hand + Q19)

Follow-up from the coordinator: on Q16, Q17, Q18 and Q19 the user reported the
drawn slot bounding box in the contact sheet "kinda crops the 7 off" (power
disc digit 7 near/outside the box). Frames: Q16=`refused_select_1790041071764460000`,
Q17=`refused_select_1790041074877095000` (as above), Q18=`refused_select_1790041078558827000`
(same 21:37 hand as Q16/Q17, attempt 3), Q19=`refused_select_1790042607981357000`
(as above). All four have `why.json` target/slot = **0**.

Measured (BASEBALL_TEST_RUN=1, offline, `tools.questions_sheet.slot_box` imported
unmodified, `local_hand.read_hand`/`circle_finder.find_circles` for the disc's
true (x,y,r)):

    frame  digit  score  disc(x,y,r)      slot_box(0)   margin_left  margin_right
    Q16    7      0.954  (206,158,r=18)   (48,278)      140px        54px
    Q17    None   0.743  (~207,201, no    (48,278)      159px        71px
                          circle matched
                          within 6px of
                          any DARK_/RAISED
                          threshold; point
                          only, no radius)
    Q18    7      0.988  (206,201,r=18)   (48,278)      140px        54px
    Q19    7      0.993  (211,160,r=18)   (48,278)      145px        49px

(margins are `disc_left_edge - box_left` and `box_right - disc_right_edge`,
in native 979x307 px; all four frames are 979x307 so scale=1.0 throughout.)

**Neither the sheet's drawn box nor the reader's own slot-assignment window
clips the disc on any of these four frames**, measured:

- `tools.questions_sheet.slot_box(979, 307, 0)` = `(48, 0, 278, 307)` for all
  four (same hand geometry). The disc (r=18, so a 36px-wide circle) sits with
  49-71px of clearance from the box's right edge and 140-159px from its left
  edge -- comfortably inside, on both sides, in every frame. A tight zoom crop
  of Q17's frame around the disc and the box's right edge (kept only as a
  scratch PNG, not archived here) confirms this visually: there is clear dark
  background between the "7" circle's right edge and the red line, before the
  neighbouring `FIELDING PLAY` card's own shield badge starts.
- The reader's own slot-assignment window (`local_hand._slot`'s cost against
  `SLOT_TOL`, the closest analogue to a "search window" -- it decides which
  slot a found candidate belongs to, not a pixel crop) is even less exposed:
  cost is 13.0-27.7 against `SLOT_TOL * s` = 34.0 for all four, so the disc is
  never near being assigned to the wrong slot or dropped as out-of-window
  either.

**What IS true, and is probably what read as "cropped" to the eye:** the box's
margins are asymmetric -- roughly 49-71px on the right against 140-159px on
the left, i.e. the disc sits well right-of-centre within its own slot box (the
box is built from the MIDPOINT between this slot's anchor and its neighbours,
not from the card's own art), and the box's right edge does show a sliver of
the neighbouring card's badge/text bleeding in (visible in the rendered
200x260 production tile). That is proximity, not clipping -- the digit itself
always has clearance -- but a right margin of 49-71px against a left margin of
140-159px is a real asymmetry, worth a note to whoever next touches
`tools/questions_sheet.py`'s `slot_box` (not edited here, per instruction):
biasing the box's centre slightly further right for slot 0 specifically (or
recentring on the found disc `x` rather than the SLOT_PLAYER/SLOT_TACTICS
midpoint) would put more daylight around the digit without changing what it
contains. This is an observation for the I-59 tool, not a defect fixed here.
