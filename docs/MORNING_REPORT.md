# Overnight, 28 Aug — what moved, what did not

**Bottom line: I did not get the six consecutive runs, so I did not start any
minigame work. BOX was never pressed. No money was spent.** The character can
now be driven with no controller connected, the route is reproducible for
roughly its first half, and I know precisely why the second half is not.

---

## The thing that was actually broken

Injection stopped working when you unplugged the DualSense, and my first
explanation was wrong. The real cause:

`StreamSession::SendFeedbackState()` is the only function in chiaki-ng that
transmits controller state, and **every caller is a real input event** — a
controller's `StateChanged` signal, or a keyboard/mouse/touch handler.
`UpdateGamepads()` fires on plug/unplug, not on a timer. There is no periodic
send at all.

So injected state was being computed correctly and then never sent. A connected
controller hid this completely, because its state events pumped the send path
continuously. Unplug it and everything goes quiet.

Fixed with a timer in the StreamSession constructor that calls
`SendFeedbackState()` while injection is active. **Injection now works with no
controller connected** — verified by driving the pause menu.

Two traps worth knowing, both of which cost me time:

- `SendFeedbackState` has a near-identical twin, `DpadSendFeedbackState`. I
  patched the twin first. It compiles, links, runs, and does nothing.
- You were right about the build. Copying over a running binary invalidates its
  code signature and macOS kills it with `SIGKILL (Code Signature Invalid)` —
  and every *later* launch dies the same way, with an empty log and a crash
  dialog blocking input. `restart_chiaki.sh` now quits first, copies, re-signs,
  then launches. chiaki also ignores SIGTERM while streaming, so it needs
  `kill -9`, and `pkill -f` did not reach it.

There is now a **watchdog**: if nothing is injected for 5 seconds the sticks are
released. Without it, the new timer would keep transmitting a jammed stick
forever if a driving script died — which it did, twice, during the night.

---

## What is reliable now

- **Reset is deterministic.** Three consecutive resets spawned at 86.86, 86.86,
  86.91 degrees, facing the typewriter. It also now retries a dropped OPTIONS
  press, and waits for the heading to *settle* before returning — it used to
  return on the first compass reading, which once reported a spawn of 241
  degrees mid-fade and doomed the run that followed.
- **Turning is accurate.** Every turn in a 25-step route landed within about 2
  degrees of its target.
- **The route reaches the bar.** Out of the office, down the staircase, out of
  the building, across the street, inside. One run ended standing next to Wanda
  Fuller, which is on the route you described.

## What is not reliable, and why

**0/3 attempts reached the table. 0/3 reached even the Wanda checkpoint.**

Every failed run reports a STUCK step — but a *different* one each time (steps
24/25, then 17/18, then 20). That is the signature: the first half of the route
is repeatable, and the second half runs through a crowded bar where the
character collides with furniture and NPCs at varying points. Once blocked, the
step budget runs out somewhere short of the table.

This is not something more tuning of the open-loop distances will fix. It needs
per-step obstruction recovery: detect the stall (already implemented and
working), then side-step and retry that step rather than continuing as though it
had succeeded.

---

## How the route works now, and why it changed shape

The recording is no longer replayed as stick inputs. It is converted into a
**world-space path**: direction of travel is the camera bearing combined with
the left stick's own angle, which separates where the character *goes* from
where the camera *looks*. That gives 25 short steps, each performed as "turn to
an absolute bearing, then walk forward" — never both at once.

That shape exists because walking while turning is where the error came from. A
30-degree heading lag at the top of the staircase became metres of position
error, and everything afterwards tracked heading beautifully while being in the
wrong room.

Things I tried that made it *worse*, recorded so they are not retried:

- Replaying your recorded right stick as feed-forward. The loop runs slower than
  the 50 Hz recording, so each camera sample is held too long and integrates
  into far more rotation than you made. Every tracking score dropped.
- Segmenting the run into turn/walk legs with a bearing per leg. Sampling a
  heading in the middle of a continuous sweep gives a target that was never a
  place the player stopped and faced.

`dur_scale` (default 1.35) is a calibration knob, not a constant: stopping to
turn covers no ground, but you never stopped, so replaying turn-then-walk
travels systematically short.

---

## A detector that was lying, and now is not

`final_approach.prompt_score` measures *that a prompt is on screen*, not which
one. Standing in front of Wanda produces "Wanda Fuller [] Talk" in the same
screen region and scores **0.375 against a 0.10 threshold** — so a run that
stopped at the wrong NPC was being counted as a success. The six-run criterion
would have been meaningless.

`table_prompt.py` now correlates the prompt's *text* against reference crops of
the real "Baseball Cards [] Play ($50)" prompt, and requires three things
together: the patch must contain actual contrast, a prompt must be present, and
the text must match. All three are needed — correlation alone scored 0.555 on
dark scenery with no prompt at all, by normalising noise.

Both frames that fooled earlier versions are kept as negative fixtures, and the
test uses leave-one-out plus held-out frames. Its first version "passed" with a
perfect 1.000 because every reference was scoring against itself.

---

## Housekeeping you asked for

- **Tests** moved to `tests/` (37 files), **docs** to `docs/` (27 files).
  `run_tests.sh` updated; fixture paths repointed off the pruned log directory.
- **1.3 GB reclaimed** (2.6 GB down to 1.3 GB) by deleting stale frame dumps.

**One thing I got wrong here, and it cost you something.** Two tests read their
fixtures out of `screenshot_log/`, and I deleted five frames they depend on.
They now read from `test_fixtures/`, which nothing prunes, but the frames are
gone. `test_ban_scan` and `test_gameplay_regions` fail until they are
recaptured, and both need frames from *inside a match* — the in-match PLAY
prompt and ban screens. I could not recreate them without spending $50, so I did
not. Details in `docs/MISSING_FIXTURES.md`.

I also tried substituting frames I did have. That was worse: those tests exist
to prove the detector fires on the in-match prompt and *not* on a ban screen,
and office frames cannot fail that check. It would have made the test pass while
proving nothing. I deleted the substitutes.

Everything else is green: 34 of 37 tests pass. The third failure is
`test_no_side_effects`, which fails only because it cannot exercise the two that
will not run — it is a consequence of the missing fixtures, not a separate fault.

---

## Two things needing your decision

1. **A macOS dialog is sitting over the game** — "Claude is requesting to bypass
   the system private window picker and directly access your screen and audio."
   I did not click Allow. You said security settings on your work machine are
   not something to loosen, and this is exactly that kind of decision. Captures
   still work, so it is cosmetic, but it obscures the middle of the screen.
   Pressing Escape does not dismiss it — Escape is mapped to the PS button in
   chiaki and opens the PS5 overlay instead.

2. **The two failing tests** need a match to be played for another reason before
   their fixtures can be recaptured.

## Obstruction recovery — built, and it works

I built the recovery I was about to recommend. On a stalled step, the character
now crabs sideways while still pushing forward and retries, then re-aims. It
works: a run that stalled at step 19 freed itself and moved 43.2 where the
threshold is 2.5, and two of three runs afterwards reported no hazards at all.

It did not fix the arrivals. Still 0/3. Removing the collisions revealed that
the runs were already ending in varying places for a second reason.

## The real blocker, stated plainly

**There is no position feedback anywhere in this system.** The compass gives
yaw, so heading is servoed exactly — every turn lands within about 2 degrees.
How far the character has travelled is pure open loop, so error accumulates with
nothing to correct it. That is why the identical route ends next to Wanda one
time and outside on the street at a "LOST TURTLE" poster the next.

Everything that worked tonight improved *aiming*. Nothing measured *position*,
and no amount of further tuning to durations or speeds will, because those are
the very quantities that drift.

## The idea I tried for position, and why it is dead

The compass strip carries small markers. If they marked fixed world positions,
the bearings to two of them would be a position sensor available on nearly every
frame — and not a scene-matching one, which matters because scene matching was
already shown unable to separate same-place from different-place in a building
of repeated doorframes.

I built it, got it reading on 88% of frames, and then **tested it properly and
it failed.** Pinning the heading and walking in a straight line, with the view
changing by 39.6 (a blocked character reads near zero, so it definitely moved),
both markers' offsets from heading stayed constant to within 0.0 and 0.5
degrees. They ride the camera. They are HUD icons at fixed screen positions and
they carry no position information at all.

An earlier test had me convinced of the opposite — rotating in place, the
computed world bearings held to 1.6 degrees, which is exactly what a world-fixed
object does. That was an artifact of which blobs the detector happened to find
at which headings. I nearly wrote it up as a working position sensor on the
strength of it.

**I deleted the module.** A dead end that reads plausibly is worse than no code,
and the one number that mattered — does the bearing change when you walk — took
two minutes to measure once I asked it directly.

## After you went back to sleep

**Visual anchors.** I scanned the whole route asking, for each moment, whether
the worst match at that place still beats the best match anywhere else on the
route. Only 10 of 32 sampled moments are separable, and where they fall is the
useful part:

    t = 9.1 - 13.2    seven anchors, gaps up to +0.44   office, stairs, landing
    t = 14.7 - 20.8   NONE                              corridor and street
    t = 22.3 - 23.9   three anchors, gaps +0.07..+0.10  inside the bar

The unanchorable middle is exactly the stretch that loses the route. An
instrumented run matched most early anchors, missed badly at t=22.33 (0.202
against a 0.541 threshold), then matched at 23.34 and 23.85.

**But I do not trust the late anchors, and the reason matters.** Searching from
that arrival point, I found Wanda Fuller — who appears in the recording at
t=17.95, not t=24. She is an NPC and she moves. Anchors whose frames contain a
person are measuring where that person happens to be standing, and the three
late anchors have the thinnest margins of the ten. `anchors.py` is built and
works, but only the early ones should be believed.

**The detector was fooled twice more, by Wanda again.** With her prompt text
partly hidden behind the character's hand, the distorted patch scored **0.657**
— higher than most genuine table frames — and a run was recorded as reaching the
table when it was standing next to her. An absolute threshold cannot survive
that, because occlusion moves the score wherever it likes.

It now compares against BOTH sets and requires the table to beat the known
impostor by a margin. Whatever distortion does to the table score it does to the
Wanda score too, so the comparison survives what a cut-off does not. It accepts
12 genuine table frames and rejects all three impostors: clean Wanda, occluded
Wanda, and dark scenery with no prompt at all.

**Distance scaling is exhausted as an approach.** dur_scale 1.35, 1.7 and 2.0
all finish with zero stuck steps, a final heading within a degree or two of
target, and no table. The route is not failing because it walks too little.

## Where I would go next

Position feedback has to come from somewhere. The compass strip is ruled out,
distance scaling is ruled out, and visual anchors only exist on the half of the
route that already works. The remaining candidate is **checkpointing on
interaction prompts**. It is
the one position signal in this game that has proven both readable and
unambiguous: `table_prompt` already distinguishes the Baseball Cards prompt from
Wanda's from noise, and Wanda stands on the route.

The shape would be: walk a short leg, sweep for a known prompt, and only
continue once the expected one is seen — turning a 25-step open-loop route into
a few segments each anchored at a place the character can positively identify.
The cost is that a prompt only fixes position when you are standing next to the
thing, so the anchors are sparse. The benefit is that error stops accumulating
across the whole route, which is what actually defeats it today.

The pieces already exist: prompt recognition that now survives occlusion,
obstruction recovery, exact turning, and a deterministic reset. What is missing
is the segmentation and the sweep-until-recognised loop.

**The honest caveat on that plan:** Wanda moves, so she cannot anchor position
either. A prompt checkpoint is only trustworthy if it belongs to something
fixed — a piece of furniture, a door, the table itself. Worth checking which
interactables on the route are static before building on them.

**And the thing I would actually ask you for:** a second recording of the same
walk. Not because the first is bad, but because everything here is inferred
from a single traversal, so I cannot separate "the route is like this" from
"that is what happened once". Two recordings would show which parts are stable
and which were incidental — the crowded second half especially, where NPCs stand
in different places each run.


---

# Addendum — after you woke up (28 Aug, morning)

## The success criterion was broken, and now is not

This matters more than any route change, because every "0/3" I reported was
measured with an instrument that was wrong.

`table_prompt.at_table` failed **four** times, each time differently:

1. Brightness only — "is any prompt visible". Wanda's prompt scores 0.375
   against a 0.10 threshold, so stopping at the wrong NPC counted as success.
2. Correlation with a 0.55 threshold — dark scenery with NO prompt scored 0.555
   by normalising noise.
3. Correlation plus a "must beat Wanda by a margin" rule — overlapped, because a
   negative with a very low Wanda score produces a huge margin.
4. Correlation with references from one, then two, traversals — **rejected the
   real thing**. Your third recording plainly shows "Baseball Cards [] Play
   ($50)" and it scored 0.566 against a 0.79 threshold.

The brightness gate turned out to be actively harmful: measured across all
recordings it rejects 24 of 67 genuine table frames while negatives reach 0.375.

It now uses correlation alone, with references drawn from all three traversals
and a contrast guard. Held-out table frames score at least 0.851, everything
else tops out at 0.666, and the threshold sits in that 0.18 gap. It finds the
table in all three recordings (380, 221 and 343 frames) and rejects all three
frames that fooled earlier versions.

**Every earlier success rate in this report was measured with a broken
instrument and should not be trusted.**

## Your third recording is the best data by far

Starts at the spawn (86.8 against the reset's 86.9), reaches the table, **98% of
headings decode** against 60% for the first, and eight pauses that land exactly
on the decision points. It yields a 40-step route whose structure is legible:
west out of the typewriter room, the "move left" at the banister, north down the
stairs and along the corridor, west at the turn, north around the corner past
the jukebox, then east into the table.

That route now executes cleanly — every turn within about 3 degrees, and runs
with zero stuck steps.

## What actually blocks the route

**Wanda Fuller is standing in the path, and she does not move.**

The route reliably reaches her — that has been consistent across many runs, and
it is why I kept finding her. But it arrives pressed face-first INTO her, with
her filling the entire frame, and the last four seconds to the table cannot be
walked. In your recordings you pass beside her, which is why the final bearings
zigzag (90, 88, 82, 72, 86, 98, 87, 76) rather than holding east.

I was wrong earlier when I inferred she moves. You said she does not, and the
evidence fits your version: the route simply stops where she stands.

Strafing either way past her does not bring the table into view, so she is not
adjacent to it — the table is about four seconds of walking further on.

## Also ruled out this morning

* **Jukebox as an anchor.** Real but too thin: 0.70 where it is, 0.51-0.62
  elsewhere, and a live anchoring attempt measured 0.603 — inside the ambiguous
  band. Not reliable enough to split the route on.
* **The dealer table as a distance gradient.** Excellent as a detector (0.70 at
  the table against 0.33 anywhere else) but it only rises once the table is
  genuinely in view, so hill-climbing on it from elsewhere just wanders.

## Where this leaves it

The remaining problem is now a single, well-defined one, which it was not
yesterday: **get past Wanda.** Everything before her is repeatable, the route
executes accurately, and arriving at her is consistent rather than random.

The approach I would take next is to treat her as the anchor she evidently is —
detect her prompt, which is reliable at close range, then use it to trigger a
deliberate go-around: back off, strafe well clear, re-acquire the recorded
bearing, and only then run the final leg. My attempt at that today strafed too
little and from too close.


---

# Addendum 2 — the macro experiment (28 Aug, midday)

## Your macro idea was right, and it produced the most important measurement yet

I did not need to patch chiaki to test it. The injection already accepts exact
analog values at any rate, so a "macro" is just replaying the recorded stick
samples at their original 50Hz timing — which is what `macro_replay.py` does,
scheduling every sample against one absolute start time rather than sleeping
between them.

**It replays essentially perfectly: 3192 samples, 1 arrived late (0%).**

An agent went through the chiaki-ng source to answer whether a NATIVE macro
would be better. Findings worth keeping:

* No macro, record, or replay facility exists anywhere in chiaki-ng.
* The transport does not quantise. Every distinct stick value produces one
  immediate UDP datagram (`feedbacksender.c` wakes on a condvar and sends;
  `FEEDBACK_STATE_TIMEOUT_MIN_MS` is defined but never applied — there is a
  literal TODO where a minimum interval would go). 50Hz fidelity reaches the
  console intact.
* The only remaining quantisation is my own 8ms pump timer, and the game samples
  input at its frame rate (16.7ms at 60fps), so that mostly moves things around
  WITHIN one game frame.

The agent's own criterion for whether to build it was: does the Python driver
drift? It does not — absolute deadlines, 0% late. So **a native macro is not
worth the patch**, and I did not write one.

It did find a real defect in my injection patch, which I fixed: `left_x` and
`left_y` were separate atomics with no atomicity across the pair, so the pump
could sample a half-updated stick vector. Both components are now read and
written under one mutex.

## The measurement that changes the picture

Three replays of the same macro from the same reset:

    run 1: heading 90.0   table-view 0.424
    run 2: heading 90.0   table-view 0.431
    run 3: heading 91.0   table-view 0.360

**Heading spread: 1.0 degree.** The macro is REPRODUCIBLE. This is the opposite
of what I assumed all night — I had concluded the game was too nondeterministic
for open-loop replay, and that was wrong. It lands in the same place every time.

That place simply is not the table. So the problem is not drift or randomness,
it is a **fixed offset** — which is a far more tractable thing to fix than the
accumulating error I spent the night chasing.

## What is actually in the way

From the macro endpoint, turning to **bearing 76** puts the table in view at
0.423, nearly centred (x=0.54), with the prompt correlation at +0.487.

Walking in from there, the character moves only 3-4 units per step for ten
consecutive steps while the view stays put. A real stride registers 10-30. It is
**physically blocked** a couple of steps short of the table, with the table
visible the whole time. My stuck detector never fired because its threshold
(2.5) is below a partial block.

Crabbing left and right did not get around it, though by then my searching had
already carried the character off the reproducible spot — which is its own
lesson: once the macro has put it on that spot, exploratory searching destroys
the one thing that was reliable.

## Where I would pick this up

1. Run the macro. It reproducibly reaches the spot.
2. Turn to bearing 76 without walking. The table is in view there.
3. Solve the last two steps ONLY — the blockage is a small, fixed, local
   problem, and it is the entire remaining gap. Raise the stuck threshold above
   4 so a partial block is detected, and try a step-up/step-round rather than a
   crab, since crabbing keeps the character pressed against whatever it is.

Do not resume the searching and hill-climbing. Those were attempts to find a
place I could not otherwise locate; that problem is now solved by the macro, and
searching only loses the position it establishes.
