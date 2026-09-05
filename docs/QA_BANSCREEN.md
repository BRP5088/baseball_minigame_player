# QA — the ban screen, end to end

Adversarial audit of the whole ban path, 2026-08-26. Every number here was
measured against the real frame log; nothing is asserted from reading the code
alone.

**Measured against** `orchestrator.py` md5 `a97085aa…`, `input_controller.py`
md5 `d1b84ce2…`, `decision_engine.py` md5 `bb463f34…`. Other agents were editing
the tree throughout, so line numbers are from those md5s and will have drifted;
symbol names are given alongside. Three changes landed mid-audit — the immediate
`save_progress` after bans (00:46), the `MASK_CONTRAST_THRESHOLD` /
`BAN_LOCKED_CONTRAST_THRESHOLD` split (01:12), and a `.tmp` cleanup in
`_atomic_write_json` (01:35). **None of them touched the ban vision path**
(verified by diff), so every measurement below still applies; the first two are
discussed in B9 and B5 respectively.

**Evidence base.** All 1,937 frames in `screenshot_log/` were classified by
normalised cross-correlation on the ban-screen header band (`x 0.25–0.75,
y 0.19–0.32`): **411 ban-screen frames**, with a clean score gap between 0.30
and 0.70 and no ambiguous cases. 386 of the 411 (94%) also OCR a
`BANNED CARDS n/3` counter, which confirms the classification. Every frame was
given an independent **scroll position** by reading the scrollbar thumb
(`x 1660–1700`), giving 361 settled frames and 50 mid-animation ones, and a
ground-truth `(absolute_row, col)` for all 3,610 settled cells.

Ground truth for this save, recovered from the frames and cross-checked against
`KNOWN_BAN_ROSTER`. **Both logged sessions are the same save** — the lock
pattern is identical across 2026-08-24 and 2026-08-25 at every scroll level —
so "locked" below is a property of this collection, not of the game. The
contrast *levels* are a property of the rendering and carry over to any save;
which cells sit at which level does not.

```
locked / not owned : (0,2) (1,0) (1,1) (2,0) (3,2) (4,2) (5,2) (6,2)
owned              : the other 25 catalogued positions
(6,3) and (6,4)    : POWER SWING tactics cards, not player cards at all
rows 7 and 8       : the tactics section
```

**What is actually live.** With `TRUST_ROSTER_ONLY = True`, exactly four things
run on the ban path: `detect_ban_grid_locked` (+ `_local_contrast`), the
`KNOWN_BAN_ROSTER` lookup, `choose_bans`, and `select_bans_and_start_full`.
`mask_low_contrast_regions`, `read_ban_row_cards`, `_read_ban_rows_separately`,
`get_ban_grid_card_crop`, `ocr_ban_card_name` and `match_roster_name` are all
**unreachable** — verified by making `read_ban_row_cards` raise and running the
scan against real frames (0 calls, 0 tesseract calls). So the audit weight sits
on the lock detector, the scroll arithmetic, and the keystroke sender.

**The happy path is correct, and that is verified, not assumed.** Replaying
`read_full_ban_collection()` against real frames at the five scroll positions
the scan actually visits produces exactly the 25 owned positions, no extras, no
card attached to the wrong position, 8 `move_down` / 8 `move_up`, zero vision
calls; `choose_bans` then picks Joshua Diaz (1,3), Johnny "Blaze" Sweets (2,1),
William Brown (3,3), and `select_bans_and_start_full` emits 18 keystrokes. The
live frame `screenshot_log/20260825_170141_505.jpg` shows the ban X on **Joshua
Diaz at exactly (1,3)** — the pipeline's prediction and the physical outcome
agree. Everything below is about what happens when something goes wrong, and
about the fact that nothing on this path can tell whether something did.

---

## B1 — CRITICAL: three of five real ban sequences placed only 2 of 3 bans, and the match started anyway

**Evidence.** OCR of the `BANNED CARDS n/3` header across all 411 ban frames,
clustered into visits by a 30-second gap. Ten visits; five reached the toggle
stage. Final counter value per visit:

| ban screen | final counter |
|---|---|
| `20260824_200720` – `200750` | **2/3** |
| `20260824_201338` – `201405` | 3/3 |
| `20260824_202016` – `202043` | **2/3** |
| `20260824_203753` – `203827` | **2/3** |
| `20260825_165858` – `170141` | 3/3 |

386 successful counter reads, **zero non-monotone** (the counter never goes
backwards within a visit), so these are not OCR artefacts.

Take the first one frame by frame. `20260824_200746_277.jpg` is the last
increment (1 → 2). The next four frames, 1 s apart, are the cursor unwinding
from scroll level 2 back to level 0, counter still 2.
`20260824_200750_297.jpg` reads `BANNED CARDS 2/3` with no X anywhere in the
two visible rows. `20260824_200751_303.jpg` is no longer a ban screen at all
(header correlation 0.202 vs 0.947), and `20260824_200752_308.jpg` is the
**match in progress** — scoreboard up, ROUND 1, 0–0. There was never a third
toggle: after the second ban the cursor moves straight up and never goes below
level 2 again.

The same holds for the other two. OCRing the scoreboard region on the first
non-ban frame after each 2/3 screen:

```
20260824_200752_308   JACK PEPPER 0 0 0 | OPPONENT 0 0 0 | ROUND . | DISCARDS
20260824_202046_743   JACK PEPPER 0 0 0 | OPPONENT 0 0 0 | ROUND . | DISCARDS
20260824_203830_101   JACK PEPPER 0 0 0 | OPPONENT 0 0 0 | ROUND . | DISCARDS
```

Three matches, each paid for, each started with a ban set the engine did not
choose.

**Two documented beliefs are contradicted by this.**

1. `orchestrator.py:3262` — *"Fewer than 3 bans leaves the game on 'BANNED
   CARDS n/3' and it refuses to start"*. Measured: the game starts at 2/3. The
   `len(bans) != 3` guard at :3264 is therefore not backed by the failure it
   claims to prevent; a short ban set is silent, not self-announcing.
2. `input_controller.py:321` (M11) — *"this path ran successfully through every
   ban screen of the 2026-08-24 live session"*. That session's own frames show
   **3 of its 4 completed ban placements ended at 2/3.** The claim was made
   from "the match started", which is exactly the observation that cannot
   distinguish 2/3 from 3/3.

**Why it is invisible.** Nothing in the pipeline reads the counter. The ban
branch's only success criterion is that `select_bans_and_start_full` returned
without raising, and that function returns after sending keystrokes into a
stream it never looks at again.

**Note on attribution.** Three of the five visits predate the N1 position-based
selection fix, so the specific 2026-08-24 mechanism may already be gone. But
the 3/3 at 20:13 sits *between* two 2/3s on the same day and the same code, so
whatever it was, it was intermittent — and nothing added since would detect a
recurrence.

### Fix B1 — read the counter before confirming

The counter is free and reliable. Measured over all 411 real ban frames:

```
read rate                94% (386/411)
non-monotone reads       0
misreads (a read that contradicts the sequence)   0
cost                     108 ms per attempt
```

The 25 unreadable frames are all *during the counter's own increment
animation* (they OCR to `"3"` or `"73"` — the numerator digit missing), so a
single retry after the screen settles closes the gap.

In `select_bans_and_start_full`, between the last `select_card`
(`input_controller.py:315`) and the two `confirm_play` presses (:328–329):

```python
n = read_ban_counter()          # retry up to 3x, 0.3 s apart
if n != len(banned_positions):
    raise BanCountMismatch(
        f"{n} of {len(banned_positions)} bans registered — refusing to confirm")
```

Two properties that matter:

* **Fail closed.** An unreadable counter must *not* count as 3. Require an
  explicit successful read of the expected number.
* **Raise before the confirms, never after.** Toggles are reversible until
  `confirm_play`; a match is not. But see **B4** — the orchestrator's current
  retry-on-exception path makes raising here *unsafe* until B4 is fixed. Ship
  them together.

Validated on all 411 frames:

```python
BAN_COUNTER_BOX_FRAC = (0.595, 0.220, 0.690, 0.295)


def read_ban_counter(img):
    """How many cards the ban screen says are banned, or None if unreadable.
    Never guesses: an unreadable counter is None, which callers must treat as
    'not verified', never as 'the number I expected'."""
    w, h = img.size
    x0, y0, x1, y1 = BAN_COUNTER_BOX_FRAC
    c = img.crop((int(w*x0), int(h*y0), int(w*x1), int(h*y1))).convert("L")
    c = c.resize((c.width * 4, c.height * 4), Image.LANCZOS)
    for thr in (110, 130, 150):
        b = c.point(lambda p, t=thr: 0 if p < t else 255)
        text = pytesseract.image_to_string(
            b, config="--psm 7 -c tessedit_char_whitelist=0123456789/").strip()
        m = re.search(r"([0-3])\s*/\s*3", text)
        if m:
            return int(m.group(1))
    return None
```

The same read also answers B9 on *entry*: `read_ban_counter(img) != 0` at the
top of the ban branch means bans are already placed on this screen, whatever
`bans_done_this_match` says.

---

## B2 — CRITICAL: one dropped `move_down` bans a card the player does not own, and nothing can see it

`orchestrator.py:2354`

```python
top_row = max(0, presses_so_far - 1)
```

The viewport's position is *inferred from the press count and nothing else*.
With `TRUST_ROSTER_ONLY = True` (`orchestrator.py:2297`) the card at a position
is `KNOWN_BAN_ROSTER[(top_row + rel_row, col)]` — no name OCR, no vision, no
cross-check. `detect_ban_grid_locked` is the only live vision component left,
and it reports lock state, not identity. **There is no independent confirmation
that the viewport is where the code thinks it is.**

**Measured consequence.** Replaying the scan against real frames with the
viewport one row behind what the code believes (one dropped `move_down`):

```
correct scan   : 25 cards, bans Joshua Diaz (1,3), Blaze Sweets (2,1), William Brown (3,3)
one-row desync : 26 cards, bans Joshua Diaz (1,3), WILLIAM LEE-GAINS (1,1), William Brown (3,3)
                 -> (1,1) is LOCKED. The player does not own that card.
```

`select_bans_and_start_full` then navigates to (1,1) and toggles it. That is
the cardinal sin, reachable from a single lost keystroke.

**The arithmetic itself is right — it is the *unverified* part that is the
problem.** Reading the scrollbar through the 2026-08-25 live scan gives the
settled capture positions directly:

```
16:58:58 - 16:59:23   level 0     <- presses 0,  top_row 0
16:59:23 - 16:59:41   level 1     <- presses 2,  top_row 1
16:59:42 - 16:59:59   level 3     <- presses 4,  top_row 3
17:00:00 - 17:00:40   level 5     <- presses 6,  top_row 5
17:00:42 - ...        level 7     <- presses 8,  top_row 7
```

Exactly `max(0, presses_so_far - 1)`, including the docstring's claim that the
first `move_down` moves the cursor without scrolling (two presses, one scroll
step, 0 → 1) and every later one scrolls by exactly 1.

It also shows **the bottom clamp is real and was hit on that run**: the last
step moves the thumb 1008 → 1058, 50 px where every other step is 82–84. The
code cannot tell a clamped press from a registered one. Today `top_row = 7`
happens to still be correct there; if the roster ever gains a row it will not
be, and nothing would notice.

Direction matters and is asymmetric:

* a dropped **`move_down`** during the scan → the collection is misattributed
  as above;
* a dropped **`move_up`** during the unwind (`orchestrator.py:2538`) → the
  cursor is left below row 0 and *every* ban lands one row low;
* an *extra* press in either direction, or the game clamping at the bottom of
  the list, is self-correcting only in the up direction (the cursor clamps at
  row 0). Over-scrolling down is not.

`test_ban_scan.py`'s unwind check asserts `move_down count == move_up count`.
Both counts come from the same `presses_so_far`, so it can only fail if the
loop structure changes — it cannot catch a keystroke that was sent and did not
land, which is the actual risk.

Nothing else covers the mapping either. Mutating the scan so every collected
row is shifted by +1 (**M22**) or every collected column is reported as 0
(**M23**) — i.e. directly corrupting `(row, col) → card` — leaves the whole
suite green. A cheap regression test, independent of the fixes below, is to run
the scan against the real frames used in this audit and assert the collection
equals the 25 known owned positions exactly:

```python
got = {(r, c) for r, c, _ in read_full_ban_collection(use_cache=False)}
assert got == OWNED_POSITIONS          # kills M22 and M23
assert all(card is KNOWN_BAN_ROSTER[(r, c)] for r, c, card in grid)
```

### Fix B2a — the scrollbar is an independent, near-free viewport oracle (recommended)

The ban screen draws a scrollbar at `x ≈ 1660–1700`. Its thumb's top edge is a
clean function of the scroll level — measured over all 361 settled ban frames,
**max residual 3 px**:

```
level   0    1    2    3    4    5    6    7 (bottom clamp)
thumb  497  593  677  760  843  925  1008  1058
step        96   84   83   83   82   83     50   <- the 50 is the clamp
```

Written as a drop-in and re-validated on every frame:

```python
BAN_SCROLLBAR_BOX_FRAC = (0.830, 0.294, 0.850, 0.944)
BAN_SCROLLBAR_DARK = 90
# Thumb-top pixel for each scroll level, measured over 361 settled ban frames
# (max residual 3 px). Level 7 is the list's bottom clamp — note the 50 px step
# from level 6, where every other step is 82-84.
BAN_SCROLL_LEVEL_Y = [497, 593, 677, 760, 843, 925, 1008, 1058]
BAN_SCROLL_TOLERANCE = 8


def read_ban_scroll_level(img):
    """(level, thumb_top) for the ban grid's viewport, or (None, thumb_top)
    when the thumb sits between levels — i.e. the grid is still animating."""
    w, h = img.size
    x0, y0, x1, y1 = BAN_SCROLLBAR_BOX_FRAC
    band = np.asarray(img.convert("L").crop(
        (int(w*x0), int(h*y0), int(w*x1), int(h*y1))), dtype=np.float32)
    dark = np.nonzero(band.mean(axis=1) < BAN_SCROLLBAR_DARK)[0]
    if not len(dark):
        return None, None
    top = int(h*y0) + int(dark[0])
    for lvl, want in enumerate(BAN_SCROLL_LEVEL_Y):
        if abs(top - want) <= BAN_SCROLL_TOLERANCE:
            return lvl, top
    return None, top
```

Run over every ban frame in `screenshot_log/`:

```
settled frames : 361 correct, 0 wrong, 0 unreadable
moving frames  : 50/50 correctly refused (returns None)
cost           : 6.3 ms per frame including JPEG decode; ~1.7 ms on an
                 already-decoded image, ~0.04 ms if the L-convert is shared
                 with detect_ban_grid_locked
```

In `read_full_ban_collection`, immediately after the capture:

```python
lvl, thumb = read_ban_scroll_level(img)
if lvl != top_row:
    raise BanViewportDesync(
        f"believed top_row={top_row} but the scrollbar reads "
        f"{'mid-animation' if lvl is None else lvl} (thumb {thumb}px)")
```

Against the one-row desync above it fires on **every** batch
(`believed level 1 → thumb 496, expected 593`), and produces **zero** false
alarms on the correct scan. It also detects the bottom clamp and any
mid-animation capture for free.

This subsumes B8 as well: a frame captured mid-scroll returns `None` and is
refused, so the scan can no longer read a moving grid even if the settle gate
times out.

Two notes on the constants. `BAN_SCROLL_LEVEL_Y` is in **pixels at
`SCREENSHOT_MAX_WIDTH = 2000`**; to match this file's own convention it should
be stored as fractions of *width* (497/2000 = 0.2485 … 1058/2000 = 0.529) for
the same reason `BAN_GRID_ROW_Y_FRAC` is. And a table-free variant exists if
hardcoding eight numbers is unwelcome: assert the thumb *moved by one step per
`move_down`*, which catches drops and the clamp without any absolute
positions — at the cost of not detecting a desync that predates the scan.

### Fix B2b — one name OCR per batch (redundant second check)

`ocr_ban_card_name` is already written, already strict, and currently dormant.
Measured over 372 crops on real frames at every scroll level:

```
catalogued + owned positions : 237 correct, 0 WRONG, 35 abstain (None)
locked positions             : 88/88 -> None
tactics / uncatalogued       : 100/100 -> None
cost                         : 141 ms per crop
```

**Zero false positives in 372 reads.** So: for one catalogued position per
batch, if the OCR resolves at all and disagrees with
`KNOWN_BAN_ROSTER[(top_row + rel_row, col)]`, the viewport is not where the
code thinks it is — abort rather than ban. Against the one-row desync this
fires on the first batch (`OCR 'Johnny Drawers' vs roster 'Claude Ewer'`) and
never fires on the correct scan. Whole-scan cost ≈ 0.7 s for one position per
batch.

Two checks with independent failure modes (pixel geometry vs. text), for about
0.7 s and 10 ms on a screen that already costs ~25 s. They are not
interchangeable, and B2a is the one to ship first:

* **B2a fails closed.** The thumb was found on **411/411** frames, including
  every mid-animation one. A missing thumb is itself an abort condition.
* **B2b fails open.** 12.9% of owned positions abstain (`None`), and an
  abstention means no check ran. It never produces a *wrong* answer, which is
  why it is a good second opinion, but on its own a batch where every crop
  abstains is silently unchecked.

---

## B3 — CRITICAL: `select_bans_and_start_full` has no test coverage at all

`input_controller.py:271–329` is the only code in the project that sends the
physical ban keystrokes, and it is the last thing that runs before $50 is
committed. Mutation testing against the full offline suite (baseline: 15/15
green):

| mutation | result |
|---|---|
| M1 `BAN_LOCKED_CONTRAST_THRESHOLD` 124 → 100 (the pre-fix value) | caught — `test_ban_grid_locked` |
| M2 `BAN_LOCKED_CONTRAST_THRESHOLD` 124 → 160 | caught — `test_ban_grid_locked` |
| M4 unwind one `move_up` short | caught — `test_ban_scan` |
| M6 lock detector inverted | caught — `test_ban_grid_locked`, `test_ban_scan` |
| M7 `_local_contrast` approximated (kernel 21 not 41) | caught — `test_ban_grid_locked`, `test_ban_scan` |
| M8 lock-detector crop margin → 0 | caught — `test_ban_grid_locked` |
| M10 cache short scans again (undo QA1-F6) | caught — `test_ban_scan`, `test_known_ban_roster` |
| M17 `choose_bans` picks the *strongest* cards | caught — `test_decisions` |
| M20 `bans_done_this_match` never set True | caught — `test_run_state_machine` |
| M21 the new immediate `save_progress` after bans removed | caught — `test_run_state_machine` |
| **M3 scroll off-by-one (`top_row = presses_so_far`)** | **SURVIVES** |
| **M11 drop the last `select_card` (→ 2/3 bans)** | **SURVIVES** |
| **M12 targets sorted descending by row** | **SURVIVES** |
| **M13 no `move_up` back to the top before confirming** | **SURVIVES** |
| **M14 one `confirm_play` instead of two** | **SURVIVES** |
| **M15 select by power instead of position (the N1 regression)** | **SURVIVES** |
| **M18 column navigation direction flipped** | **SURVIVES** |
| **M16 roster-exhausted stop removed (the LESSONS §7 fix)** | **SURVIVES** |
| **M22 every collected row shifted +1 (all bans one row low)** | **SURVIVES** |
| **M23 every collected column reported as 0** | **SURVIVES** |

Ten caught, ten survive. Note what the survivors have in common: **M3, M22 and
M23 corrupt the `(row, col)` → card mapping, and M11–M18 corrupt the keystrokes
sent to act on it.** Those are the only two ways a wrong physical card gets
banned, and neither is covered. Everything the suite does cover is the *image
processing* — thresholds, kernels, crop margins — which is the part that has
never been observed to fail.

The pattern is not "a few gaps": **every one of the six mutations confined to
`select_bans_and_start_full` survives**, including the exact failure B1 observed
live (drop one `select_card` → 2/3) and the exact regression N1 was written to
prevent (select by something other than position). The function is called once
per paid match and nothing asserts anything about what it emits.

### Fix B3 — a keystroke-sequence test

The function is pure with respect to `press`; recording it is enough. Assert on
the *sequence*, not just counts, so a reordering fails:

```python
grid = [(r, c, PlayerCard(f"{r}{c}", 5, 1)) for r in range(5) for c in range(5)]
seq = record(lambda: select_bans_and_start_full(grid, {(1, 3), (2, 1), (3, 3)}))
assert seq == ["move_down", "move_right", "move_right", "move_right", "select_card",
               "move_down", "move_left", "move_left", "select_card",
               "move_down", "move_right", "move_right", "select_card",
               "move_up", "move_up", "move_up",
               "confirm_play", "confirm_play"]
```

That exact sequence is what the real code emits today (verified against the
real frame set). Two-sided assertions to add alongside it:

* exactly `len(banned_positions)` `select_card` presses — kills M11;
* net vertical displacement is zero at the `confirm_play` (`move_down` count ==
  `move_up` count) — kills M13;
* the cursor never moves up *before* the last `select_card` — kills M12;
* exactly two `confirm_play` — kills M14;
* a grid where two positions hold cards with equal power/name still yields
  exactly `len(banned_positions)` `select_card` presses — kills M15 and pins
  the N1 fix;
* a target to the *left* of the cursor produces `move_left`, one to the right
  produces `move_right` — kills M18 (the full-sequence assertion above already
  does, but state it separately so it survives a rewrite of the fixture).

---

## B4 — HIGH: an exception after the first `select_card` is retried from a wrong origin, up to 15 times

`orchestrator.py:3299–3311`

```python
select_bans_and_start_full(grid, banned_positions)
bans_done_this_match = True
...
except Exception as e:
    stuck_count += 1
    print(f"Couldn't complete the ban screen ({e}), retrying... ")
```

If anything raises *after* the first `select_card` — `pyautogui` failing, the
counter check proposed in B1, a `KeyboardInterrupt` variant — the toggles
already applied stay applied, `bans_done_this_match` is never set, and the loop
`continue`s. On the next iteration `read_full_ban_collection()` returns the
process cache instantly, and `select_bans_and_start_full` runs again from its
documented assumption that the cursor is at `(0, 0)`. `MAX_STUCK_ATTEMPTS = 15`
(`orchestrator.py:70`), so up to 15 passes × 3 toggles = 45 blind toggles from
an unknown origin.

The `N11` note in the neighbouring C3 guard already reasons correctly about
this ("a blind retry would un-ban what was just banned") — but that reasoning
was applied to the *screen-repeat* guard and not to the *exception* path
immediately below it.

**Fix.** Treat a failure that occurs after any `select_card` as a hard stop,
not a retry. Cheapest version: have `select_bans_and_start_full` raise a
distinct `BanToggleStateUnknown` once it has pressed `select_card` at least
once, and have the ban branch `break` with `stop_reason = "ban_toggles_dirty"`
on that type rather than counting it toward `stuck_count`. This is also the
precondition for B1's fail-closed counter check.

---

## B5 — HIGH (evidence, not value): the "empty gap [106.5, 142.5]" is not empty

`orchestrator.py:461` and `test_ban_grid_locked.py:73–84`.

The comment and the test both rest on: *"Re-measured over ALL 95 cached ban
frames (950 cells). The distribution is cleanly bimodal … locked cluster …
106.5 / empty, 35.9 wide / unlocked cluster 142.5 …"*

**Independently re-measured over 411 ban frames (4,110 cells):**

```
cells inside [106.5, 142.5]      142 / 4110  (3.5%)
frames containing >= 1 such cell  96 / 411
largest gap anywhere in the distribution      2.2   (at the very top, 190.3 -> 192.4)
largest gap in the 85-145 region              2.0
```

There is no empty gap. The distribution has a sparse *valley*, not a void.

**The value 124.0 is nevertheless correct — and now has a defensible bound.**
Restricted to genuine *player-card* cells on *settled* frames:

```
max contrast on a LOCKED (not-owned) card   106.5   <- and see B5b
min contrast on an UNLOCKED (owned) card    141.4   <- (6,0) Jake Saucepan Black
=> true safe window (106.5, 141.4), width 34.9; 124.0 sits 17.5 / 17.4 from the edges
```

The fix that moved 100.0 → 124.0 was right, and **worth more than the comment
claims**. Counting settled cells on genuine player-card positions across all
411 frames:

```
threshold 100.0 : 18 cells read a LOCKED (not-owned) card as unlocked
                  7 of them on (0,2), all BANNING PHASE banner frames
                 11 of them on (2,0) Zachary Lee, cursor-lifted (100.1 - 105.5)
                  0 cells read an owned card as locked
threshold 124.0 :  0 in either direction, on all 361 settled frames
```

Not 6 cells — 18, across two distinct physical cards and two distinct causes.
What is wrong is the *reason recorded for it*, and that matters because this
file's own practice is to re-derive constants from the recorded measurement.

On **mid-animation** frames neither value helps: 42 cells false-unlock and 26
false-lock at *any* threshold in this range, because the sample box straddles
two different cards. That is B8's problem, not the threshold's.

**What actually lives inside the claimed gap** (and is what the original
measurement must have excluded):

```
(6,3)  POWER SWING (a TACTICS card)  120.8 - 141.3, median 128.9, 63 settled frames
(7,1)  tactics                       121.5 - 170.3
(7,4)  tactics                       126.0 - 170.3
plus every mid-scroll-animation frame (see B5c)
```

### B5b — the 106.5 upper bound is set by the BANNING PHASE banner, not the cursor

The comment attributes 106.5 to *"the ban cursor's highlight … +20-26"*.
Measured per locked position, with and without the banner frames:

| locked cell | median | max without banner | max with banner |
|---|---|---|---|
| (0,2) | 53.1 | 83.9 | **106.5** |
| (2,0) | 79.7 | 105.5 | 105.5 |
| (1,1) | 63.1 | 92.2 | 92.2 |
| (5,2) | 53.8 | 94.5 | 94.5 |
| (3,2) | 74.7 | 94.3 | 94.3 |
| (6,2) | 79.1 | 82.9 | 82.9 |
| (1,0) | 50.2 | 80.0 | 80.0 |
| (4,2) | 73.2 | 78.2 | 78.2 |

So: **the cursor is worth up to +26 (max 105.5); the BANNING PHASE banner is
worth +33 to +53** on (0,2), taking it from a median of 53.1 to 86.3–106.5.
The banner is the binding constraint and is not mentioned anywhere in the code.

### B5c — the answer to "does the BANNING PHASE overlay perturb the detector"

Seven frames in the log carry it (`20260824_201338_852`, `201339_855`,
`202016_619`, `203324_509`, `203325_056`, `20260825_165858_914`, `165859_442`).
It is a large white word-mark spanning `x ≈ 0.27–0.71, y ≈ 0.49–0.55`, i.e.
squarely inside row 0's contrast boxes (`y 0.195w–0.385w` = 390–770 px) for
columns 1, 2 and 3. Measured lift per column at scroll level 0, banner frame
vs. the same position without it:

```
col      0      1      2      3      4
base   169.2  171.2   54.6  169.0  162.2
banner 165.5  183.4  105.0  178.8  158.9
delta   -3.7  +12.2  +50.4   +9.8   -3.3
```

The lift is largest on (0,2) precisely because that card is locked — the white
word-mark supplies the local contrast the faded art does not.

**Measured: `detect_ban_grid_locked` returns the correct 2×5 grid on 7/7
banner frames.** The end-to-end replay in the header of this document even uses
a banner frame (`20260825_165858_914`) as the scan's first capture and still
produces the right 25 cards. Margin on the worst cell is 17.5 (106.5 vs 124.0).

At the *old* threshold of 100.0, five of the seven banner frames would have read
(0,2) — Harold "Fisto" Blunt, not owned — as unlocked. So the banner, not the
cursor, is the strongest single justification for the threshold move.

The banner only ever appears at scroll level 0 (all 7 frames), so only (0,2) is
exposed. Worth recording, because banner + cursor on the same cell has never
been observed and would be ~53 + ~26 above a ~53 baseline — i.e. it would cross
124.0. It cannot happen today only because the banner shows while the cursor is
still at its default position.

### Fix B5

Replace the comment at `orchestrator.py:453–478` and the `_GAP_LO/_GAP_HI`
literals in `test_ban_grid_locked.py:73` with the bound that is actually true:

```python
# Measured 2026-08-26 over all 411 ban-screen frames in screenshot_log/
# (3,610 settled cells, scroll position established independently from the
# scrollbar thumb). The distribution is NOT bimodal with an empty gap — tactics
# cells at (6,3), (7,1), (7,4) sit in the middle of it, and 3.5% of all cells
# land in [106.5, 142.5]. What IS true, and is what this threshold needs:
#
#   max contrast on a LOCKED player card   106.5  (BANNING PHASE banner on (0,2);
#                                                  105.5 without it, cursor-lifted)
#   min contrast on an UNLOCKED player card 141.4  ((6,0) Jake Saucepan Black)
#
# 124.0 sits 17.5 above the first and 17.4 below the second.
BAN_LOCKED_CONTRAST_THRESHOLD = 124.0
_LOCKED_MAX, _UNLOCKED_MIN = 106.5, 141.4   # test asserts against THESE
```

and make the test's assertion `_LOCKED_MAX + 10 <= T <= _UNLOCKED_MIN - 10`
with both literals hardcoded in the test (as they correctly already are — the
existing test does *not* read its bound from the constant it is checking, which
is the right shape; only the numbers behind it are wrong).

---

## B6 — MEDIUM: (6,3) and (6,4) are not uncatalogued player cards, they are POWER SWING tactics cards

`orchestrator.py:1974` ff. The roster comment explains the two gaps as *"row 6,
cols 3-4, never captured in any scan this session — cut off by either a
transient mismatch or the tactics-section boundary before a clean read landed
on them"*, and `TRUST_ROSTER_ONLY`'s note calls them *"the two catalogue gaps"*
that are *"simply skipped as ban candidates"*.

`test_fixtures/20260824_200604_139.jpg` shows row 6 directly: Jake Saucepan
Black, Mickey Brown, Thomas Thomas (locked), then **POWER SWING**, **POWER
SWING**. They are the first two cells of the tactics section, which begins
mid-row. There is nothing to catalogue.

Two consequences:

1. **`(6,3)` flickers across the threshold.** Measured 120.8–141.3 (median
   128.9) over 63 settled frames, i.e. it reads "unlocked" on roughly half of
   captures. Harmless today — it is skipped by the roster lookup, and the scan
   prints `1 position(s) not in the roster [(6, 4)]` or `[(6,3), (6,4)]`
   depending on the frame.
2. **It is the trigger for the 149-second pathology, and the documented
   rollback re-arms it.** `TRUST_ROSTER_ONLY = False` is offered as the way to
   "restore vision-backed discovery". With it off, (6,3)/(6,4) fall through to
   `ocr_ban_card_name` (measured: `None`, 100/100 on tactics cells), then to
   `read_ban_row_cards`, which correctly filters tactics out — producing the
   count mismatch → per-row retry → two vision calls per wasted step that
   `LESSONS.md §7` describes. The early-stop added for §7 is weaker than it
   looks: the condition at `orchestrator.py:2411` is
   `top_row > _max_roster_row() + 1`, i.e. `top_row > 7`, and the scan's
   `top_row` sequence is `0, 1, 3, 5, 7`. **7 is not > 7, so on the live
   (`trust_roster`) path that branch never fires at all** — what actually stops
   the scan today is the `if not roster_hits: break` at :2428, which exists
   only on the `trust_roster` path. On the rollback path the early stop does
   fire, but one batch late (at `top_row = 9`), which is the "one batch of
   slack" the comment intends — so the rollback still pays the mismatch-plus-
   retry cost for the whole of rows 7–8 before stopping.

**Fix.** Record (6,3)/(6,4) as *known tactics positions* rather than gaps —
a `KNOWN_TACTICS_POSITIONS = {(6, 3), (6, 4)}` set consulted before the roster
lookup, so the scan stops describing them as missing catalogue entries. Change
the early stop to `top_row >= _max_roster_row()` (or drop it and document that
`not roster_hits` is the real stop) so the §7 fix is live on both paths. And
add a test that fails when the stop is removed: mutation **M16** — deleting the
`if not roster_hits: break`, i.e. deleting the only thing that actually ends the
scan today — leaves the entire suite green.

---

## B7 — MEDIUM: `_cached_ban_collection` turns one bad scan into a whole bad session

`orchestrator.py:2271`, guarded at :2550.

*Is the "two saves in one process" case reachable?* **No, today.**
`run_tonight.py` and `run_testing.py` each call `orchestrator.run()` exactly
once per process, and `run_testing.py` deliberately uses a *copy* of the same
save, so even a shared cache would be correct. Nothing else calls `run()`.

*The reachable problem is different and worse.* The `>= 3` guard added by
QA1-F6 checks **count**, not correctness. The 26-card desynced collection from
B2 passes it, is cached, and is then served to every subsequent ban screen in
the session with no re-validation and no expiry. One dropped keystroke in the
first match's scan bans the wrong physical card in *every* match that night.

**Fix.** Validate before caching, not just count: cache only if every
`(row, col)` in the collection is in `KNOWN_BAN_ROSTER`, the positions are
distinct, and — if B2a is adopted — every batch's scrollbar check passed. A
collection that failed a viewport check should be returned for this match (or
better, not returned at all) but never cached.

---

## B8 — MEDIUM: the scan's settle gate does not watch the ban grid; it works by accident

`orchestrator.py:2533` calls `wait_for_screen_to_settle(max_wait=6.0)` with the
default region set, which is `("legacy_roi", "hand")` (`orchestrator.py:1283`).
`legacy_roi` is `y 0.15–0.65`, `hand` is `y 0.716–1.0`; the ban grid's contrast
boxes span `y 0.302–0.906` of the frame. This is structurally the same shape as
the bug the comment at `orchestrator.py:1178` calls a "ROOT-CAUSE FIX" — a
settle detector that does not observe the region about to be read.

**Measured: it is adequate anyway, by overlap.** Shifting the scrolling grid
band of a real frame vertically and computing the same mean-absolute-delta the
gate uses:

```
shift   legacy_roi (thr 6.0)   hand (thr 8.0)   verdict
  5 px        11.06                11.74        moving  (caught)
 10 px        15.40                16.48        moving
 40 px        26.42                25.01        moving
120 px        39.66                20.71        moving
366 px (one full row)  47.72        0.00        moving
```

A **5-pixel** grid shift is already caught. Independently, across all 74 real
scroll transitions in the log, **0 would have been called stable**.

**So mid-animation capture is not a live risk** — which is important, because
mid-animation frames are genuinely dangerous. Of the 50 mid-animation frames in
the log, several read a locked card as unlocked at the current threshold, e.g.

```
20260824_203804_754  thumb 632 (between levels 1 and 2)  cell (rel 0, col 1) = 131.7
20260824_203825_708  thumb 632                            cell (rel 0, col 1) = 133.9
20260825_170125_433  thumb 632                            cell (rel 0, col 1) = 129.6
```

— all of which, at a believed `top_row = 1`, make (1,1) William Lee-Gains (not
owned) a ban candidate. No threshold value can fix this; only not reading a
moving frame can.

**Fix.** Add `"ban_grid"` to `SETTLE_REGION_SETS` (the grid bbox is already
derivable from `BAN_GRID_COL_X_FRAC` / `BAN_CARD_ROW_TOP_FRAC`) and pass
`regions="ban_grid"` at :2533, so the protection is by design rather than by
coincidence. Cheaper alternative that costs nothing: after the settle, take the
scrollbar reading from B2a and require it to be within 5 px of a level — that
detects a moving frame directly and is the same check that catches desync.

Note the residual hole either way: `max_wait=6.0` returns and reads anyway on
timeout (`orchestrator.py:1397`). A ban-grid-aware settle plus a scrollbar
sanity check makes that outcome detectable instead of silent.

---

## B9 — MEDIUM: a banned card is indistinguishable from an unbanned one to every part of the pipeline

The game marks a banned card with a large X (`screenshot_log/20260825_170141_505.jpg`,
Joshua Diaz at (1,3)). Measured contrast on that cell **with the X**: 156.8.
The unbanned distribution for the same cell across the log: 150.2 – 185.3,
median 163.3. The X is invisible to `detect_ban_grid_locked`, and
`TRUST_ROSTER_ONLY` means nothing else looks at the card at all.

So a ban screen re-entered after bans are placed reads as "0 banned", and
`choose_bans` picks the same three — toggling them **off**. Today this is
prevented by `bans_done_this_match`, which is now persisted immediately in the
ban branch — a fix that landed at 00:46 during this audit. I verified it in
both directions: driving `["match_start_prompt", "ban_screen"]` through the
state machine now leaves `progress.json` as
`{"match_in_progress": true, "bans_done_this_match": true}`, and against the
pre-fix code the same run left the key absent entirely. Mutations **M20** and
**M21** are both caught, so it is now regression-tested too.

The point stands that the guard is *state*, not *observation*: it survives a
crash only because it is written to disk, and it cannot help if
`progress_file` is the wrong one or is reset. The counter read from B1 is the
observation that closes it — `n/3 != 0` on entry means bans are already placed,
regardless of what any flag says.

---

## B10 — LOW: `detect_ban_grid_locked` reads row boundaries as fractions of WIDTH and then clamps to height

`orchestrator.py:571–624`. `row_y` is computed as `int(w * y)`, and the crop is
`gy1 = min(h, max(row_y) + margin)`. That needs `h >= 0.585·w + 22` = **1192 px
at w = 2000**; the actual frames are 1292 (7.7% headroom). Below that, the
bottom row's cell slice is silently truncated by numpy *and* the last 20 rows
of `_local_contrast`'s output are padding-contaminated (255-minus-0 → maximum
contrast), biasing toward "unlocked" — the dangerous direction.

Measured by truncating a real frame's letterbox: at h = 1125 (16:9), row 1's
cells move by up to +6 and **no cell is misclassified**. So this is latent, not
live. All 1,937 logged frames are 2000×1292.

**Fix (cheap).** Assert the precondition where it can be seen:

```python
assert gy1 == max(y for _, y in row_y) + margin, (
    f"frame is {w}x{h}; the ban grid's bottom margin is clamped, so the last "
    f"row's contrast is read from padding and locked cards can read unlocked")
```

---

## B11 — SPEED: the ban screen now costs ~25–30 s, not 149 s; the remaining fat is the capture, not the vision

Measured trace of the current code against real frames:

```
scan iterations                    5   (top_row 0, 1, 3, 5, 7)  [measured here]
detect_ban_grid_locked              22 ms each                  [measured here]
  (PIL Max/MinFilter equivalent    7216 ms                      [measured here])
keystrokes                          34  (8 down + 8 up scan, 18 ban)
                                                                [measured here]
capture_screenshot_image           ~760 ms each                 [from this file's
  = 376 screenshot + 78 resize + 154 osascript + 150 sleep       own recorded
                                                                 measurements]
per keystroke                      ~0.45 s with focus cached    [same]
settles                             4 + 1
```

≈ 15 s of keystrokes, ≈ 4 s of captures, ≈ 4–8 s of settling. The 149 s in
`LESSONS.md §7` is gone: with `TRUST_ROSTER_ONLY` the scan makes **zero** vision
calls and **zero** tesseract calls, verified by making both raise.

Two remaining levers, and one trap:

* **The captures.** `capture_screenshot_image` uses `pyautogui.screenshot()`
  (~376 ms) where `_fast_grab()` does the same job in ~32 ms and is already used
  by the settle loop. That is ~3.5 s of the ban screen.
  **Trap — measure before adopting.** `_fast_grab` normalises mss's *logical*
  1728×1117 grab *up* to 2000 px; `capture_screenshot_image` downscales
  pyautogui's *physical* 3456×2234 grab *down* to 2000 px. They are different
  images at the same nominal size, and `MASK_KERNEL = 41` is explicitly
  calibrated to the latter (the file already records that 1400 px broke 4 of 12
  frames). Re-measure the 3,610-cell distribution on `_fast_grab` frames before
  swapping, or the speed win silently changes which cards get banned.
* **The unwind.** 8 of the 34 keystrokes exist only to return the cursor to
  (0,0) so `select_bans_and_start_full` can assume its origin. If B2a is
  adopted, the scrollbar tells you where the cursor actually is, and the unwind
  could be replaced by "press `move_up` until the thumb reads level 0" — which
  is both faster in the common case and *correct* in the case the current code
  cannot detect.
* Not a lever: the collection is a per-save constant, so the process cache
  already makes match 2+ free. Only the first ban screen of a session pays.

---

## B12 — verified claims (no defect; recorded so they are not re-litigated)

* **`_local_contrast` is exact.** Independently checked against PIL's
  `MaxFilter`/`MinFilter` on the *full* grid crop (824×1384) of 6 real ban
  frames, borders included, not just the interior and not just synthetic
  patterns: **max |difference| = 0** on every frame. 21.2 ms vs 7216 ms (340×).
  The existing test compares the interior of 3 synthetic arrays, which is
  weaker but sufficient; the real-frame check is worth adding because it also
  pins the border convention the docstring claims.
* **The crop is exact.** `margin = MASK_KERNEL // 2 + 2 = 22 > 20 = radius`, and
  the sampled cells begin at index 22 and end 22 from the far edge, so no
  sampled pixel sees padding — verified by the zero-difference result above.
  Mutation **M8** (margin → 0) is caught.
* **The scan is fully local.** Verified by making `read_ban_row_cards` raise:
  0 calls, 0 OCR calls, 25 cards.
* **The cursor does not break the card crops.** 372 `ocr_ban_card_name` reads
  across every scroll level: 237 correct, **0 wrong**, 88/88 locked → `None`,
  100/100 tactics → `None`. The scan leaves the cursor in **column 0**
  throughout, and column-0 crops read correctly 12/12 at (3,0), (4,0), (5,0)
  and 10/10 at (6,0). The `cutoff=0.85, allow_surname_fallback=False` setting
  is doing exactly what its N1 comment claims.
* **`read_ban_row_cards` and `_read_ban_rows_separately` are dormant**, not
  merely unlikely: unreachable while `TRUST_ROSTER_ONLY` is True.
* **`choose_bans` is deterministic but tie-broken by scan order.** Eight
  catalogued cards have `power == 4` and seven of them are owned, so the "three
  weakest" are a choice among seven equals. `sorted` is stable, so which three
  win depends on the order rows are appended — fixed today (rows 0,1 → 1,2 →
  3,4 → 5,6) and reproducible, but it means the tie-break is an artefact of the
  scan rather than a decision. Not a correctness bug; worth knowing before
  anyone "optimises" the scan order, and worth noting that the `secondary` stat
  the whole project is trying to measure is *never consulted* when picking bans.

---

## Unknowns that change the blast radius (not defects — gaps in what is known)

These are cheap to settle and each one changes how bad a dropped keystroke is.
None of them can be answered from the existing frames.

* **Does the ban grid's cursor wrap at the row edges?** `select_bans_and_start_full`
  computes `col_diff` exactly and never overshoots *by design*, so wrapping only
  matters when a press is dropped or duplicated. If `move_right` at column 4
  wraps to column 0 (or to the next row), one lost keystroke moves the cursor
  a whole row; if it clamps, it moves nothing. The log has no frame of the
  cursor at column 4 receiving a `move_right` — during the scan the cursor
  stays in column 0 throughout, and during placement it only ever reaches
  columns 1 and 3.
* **Does `select_card` on a locked card do anything?** If the game refuses it,
  the B2 desync degrades from "bans a card you don't own" to "silently places
  one fewer ban" — which is exactly the 2/3 signature in B1, and would make
  B2 the leading explanation for it. If it *does* toggle, B2 is the full
  cardinal sin. Currently unknown, and the two hypotheses are distinguished by
  a single observation: whether the counter increments.
* **What is the real keystroke drop rate?** `match_log.jsonl` has 39 rows and
  zero misfire records; `OVERNIGHT_AUDIT.md` reports "500 cards played, 0
  suspected misfire(s)" from a run later shown to be a frozen stream, i.e. no
  keystroke was ever observed to land. The ban path sends 34 keystrokes per
  match with no feedback of any kind, and the rate at which they land has never
  been measured. `input_controller.report_misfire()` exists but is fed only by
  the gameplay reveal auditor, never by the ban screen.

---

## Ranked summary

| # | Finding | Consequence | Where |
|---|---|---|---|
| B1 | 3 of 5 real ban sequences placed 2/3 bans; the game starts anyway | paid $50, wrong ban set, silent | `input_controller.py:271`, `orchestrator.py:3262` |
| B2 | viewport position inferred from press count with no confirmation | one dropped keystroke bans a card the player does not own | `orchestrator.py:2354` |
| B3 | the keystroke-sending function has zero test coverage | every mutation to it ships green | `input_controller.py:271-329` |
| B4 | exception after the first toggle is retried from a wrong origin ×15 | up to 45 blind toggles | `orchestrator.py:3299-3311` |
| B5 | the "empty gap" behind the threshold is not empty (value is still right) | future re-derivation misleads | `orchestrator.py:461`, `test_ban_grid_locked.py:73` |
| B6 | (6,3)/(6,4) are tactics cards, not catalogue gaps; §7 early stop is dead code | rollback switch re-arms the 149 s pathology | `orchestrator.py:1974`, `:2411` |
| B7 | cache validates count, not correctness | one bad scan poisons the whole session | `orchestrator.py:2550` |
| B8 | settle gate does not watch the ban grid (works by overlap) | mid-animation frames are dangerous and the protection is accidental | `orchestrator.py:2533`, `:1283` |
| B9 | a banned card looks identical to an unbanned one | guard is state, not observation | `orchestrator.py:571` |
| B10 | row boundaries are width fractions clamped to height | latent; needs h ≥ 1192 at w = 2000 | `orchestrator.py:607-620` |
| B11 | ~4 s of the ban screen is `pyautogui.screenshot()` | speed only, with a resolution trap | `orchestrator.py:775` |

**If only one thing is done: read the `BANNED CARDS n/3` counter before
confirming (B1), together with the hard-stop change in B4.** It costs 108 ms,
it is 94% reliable on frames the code has not even settled, and it is the only
proposed check that would have caught the failure that has already happened
three times.

### Suggested order

1. **B4** — make a post-toggle failure a hard stop instead of a 15× retry.
   Nothing else is safe to add until raising is safe.
2. **B1** — `read_ban_counter`, checked before the confirms and again on entry.
   Closes the observed failure and, on entry, subsumes B9.
3. **B2a** — `read_ban_scroll_level`, checked after every capture. Closes the
   unobserved-but-worse failure, and subsumes B8 and the mid-animation risk.
4. **B3** — the keystroke-sequence test. Ten surviving mutations, one fixture.
5. **B7, B6, B5** — cache validation, the tactics positions, and the corrected
   threshold comment. Cheap, none of them urgent.

Steps 1–3 add roughly 0.6 s per ban screen and one new failure mode: a run that
stops instead of banning the wrong card. Given the screen costs $50 to reach,
that is the correct trade.

**Do not touch anything else on this path first.** The lock detector, the
separable contrast filter, the crop margins and the threshold value were all
adversarially re-measured here and all hold. The failures are in the two places
nobody has instrumented: where the viewport is, and whether the keystrokes
landed.

---

### Reproduction

Everything above was produced offline from `screenshot_log/` in a sandbox
(`…/scratchpad/qa_ban`, `…/scratchpad/qa_meas`) — no game, no keystrokes, no
API calls, `BASEBALL_MATCH_LOG` and `BASEBALL_DIAGNOSTICS_DIR` redirected to
`/tmp`. The real tree was not modified: `screenshot_log/` still holds 1,937
frames with no file newer than the session that wrote them, and
`match_log.jsonl`, `progress*.json` and `known_ban_roster_learned.json` are
untouched (the last still does not exist).
