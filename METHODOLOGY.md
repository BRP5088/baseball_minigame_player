# Methodology learned the hard way (§10)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

---

## §10 Methodology learned the hard way

**32. AN UNPROVEN ASSERTION IS NOT A SHORTCUT. IT IS THE SAME WORK PLUS A
RETRACTION.** The user's rule, 2026-09-17: *"asserting claims without proof aren't
allowed. they are often wrong and waste time."* Stated first because it is the cheapest
rule in this file to follow and the most expensive to skip -- almost every other entry
here exists because someone, usually me, said a thing instead of checking it.

Five from ONE session, each stated confidently, each wrong, each caught by someone else
asking:

    "grep is wrapped by RTK"              named a plausible cause. `type grep` shows
                                          it is Claude Code's own ugrep. Asserted
                                          inside a paragraph ABOUT an instrument that
                                          silently under-reports (§10.16c)
    "typhoon: zero references"            grep searches CONTENTS; typhoon_results.json
                                          was 11.8K on disk
    "that grep returns only <one file>"   false at the commit that wrote it -- the SAME
                                          commit created the second file it misses
    "the places cluster is ~130 dead      load_places, descriptor and frame_heading are
     lines, safe to delete"               live; deleting on that list breaks the localiser
    "paddle_venv: nothing uses it"        five production runners shell out to it; a
                                          deletion was nearly carried out (§2)

**THE TEST, BEFORE THE SENTENCE LEAVES:** what did I actually run or read that shows
this? If the answer is "it stands to reason" or "that is how it usually works", then
either run it -- these checks cost seconds, `type grep` settled the first row -- or
write the claim as a guess and label it. This file already separates ESTABLISHED from
ASSUMED for sub-agent notes (§10.16); the same discipline applies to every sentence
said to the user, in a commit message, or written here.

**AND THE COST IS NOT THE WRONG SENTENCE, IT IS WHAT GETS BUILT ON IT.** The paddle_venv
line sat here for weeks doing nothing until someone acted on it. §10.2's whole subject is
a mechanism that made sense and measured backwards. A wrong claim is inert right up until
it is load-bearing, which is why it cannot be left to be corrected later.

**33. THE USER IS USUALLY RIGHT, AND THE RECORD SAYS SO. TEST THEIR IDEA BEFORE
ARGUING WITH IT.** Their own framing, 2026-09-17: *"I tend to be right about most
things. I'm not bragging, I've just spent a LOT of time debugging this and know it
pretty well."* That is not flattery to be humoured -- it is a calibration fact with
a mechanism (they have watched this game far longer than any session has) and it is
cheaper to act on than to relearn.

The cost of the opposite is already written all over this file. §8's closed loop
opens with *"the user had asked for this design earlier and an earlier session built
dead reckoning instead; that cost days."* §3 records the coin misread THREE times
against their correction, and the PS5 overlay taking X where this file insisted on
Square. §4's "+3 does not exist" was their call against 11 recorded values. §10.29's
wrong diagnosis was stopped by them. In one evening, 2026-09-17:

    "both players have separate decks, so they        refuted a census this project
     can have different cards than us"                 had treated as a game rule
    "capture the hand as the obstructing card          the ONLY way the occluded
     animates away"                                    card was ever identified
    "stop doing 'the card is on screen right now'      found a deadlock that would
     -- you aren't letting us tune the engine"         have killed every unattended run

**THE RULE:** when they propose something, the next move is a MEASUREMENT, not a
counter-argument. Say what would confirm or refute it and go and get that. Where
they are wrong the measurement says so quickly and cheaply -- and that has also
happened, which is why this is calibration rather than deference.

**34. AN OCCLUDED CARD CAN ONLY BE REVEALED BY REMOVING WHAT COVERS IT, SO
DISCARDING A JUNK OCCLUDER HAS INFORMATION VALUE THE ENGINE DOES NOT MODEL.**
Measured live 2026-09-17. Slot 1's power disc sat under slot 2's card; §10.28
already records that no amount of re-reading, cursor movement or selection uncovers
it. Slot 2 was discarded (on its own merits -- a 4 in a hand whose readable maximum
was 5), and slot 1 read **8/1 at 163 ms and in 20 of 20 deal frames, score
0.986-0.993**. Not a narrow window: the instant the occluder lifts, the card is
legible and stays legible.

**AND THE HAND WAS NEVER WEAK.** The hidden card was the BEST one, so the true
maximum was 8 against `REDRAW_POWER_THRESHOLD` 6 and `should_redraw` should not have
fired at all. It fired because it takes `max()` over the slots that SURVIVED and has
no idea its input is incomplete -- the same shape the discard branch's own comment
describes for a misread power ("a true hand [9,5,4,4,5] read as [1,5,4,4,5] ...
discards THE REAL 9").

**THE USER'S READING OF THAT IS THE RIGHT ONE, AND IT IS NOT "THE DISCARD WAS
WASTED":** *"I wouldn't be super worried about using the discard since it allowed us
to see a better card and the card was bad."* Both halves are true at once -- the
decision was taken on wrong information, and its outcome was positive (junk thrown,
an 8 revealed, a POWER SWING +2 drawn). What follows is not "stop discarding" but
that a discard which REMOVES AN OCCLUDER buys information, and nothing in
`should_redraw` prices that. Do NOT throw a card merely to read its neighbour; do
recognise that when the occluder is already the weakest card, the two reasons agree.

The unmodelled gap, stated so it can be measured rather than guessed: an occluded
card in a hand the engine does NOT want to discard stays unknown for the whole half,
and every decision that half is taken over an incomplete hand silently.

**35. WHEN A WINDOW'S DISCRIMINATION COMES FROM WHERE IT SITS, EVERY DEGREE OF
FREEDOM YOU GIVE IT DESTROYS THAT DISCRIMINATION -- AND EACH ATTEMPT LOOKS LIKE
AN IMPROVEMENT RIGHT UP TO THE CONTROL.** Four attempts in one night, 2026-09-17,
on the cursor-glow window. All four raised the TRUE reading. All four raised the
FALSE reading at least as much, and only the control showed it.

The window is 80x20 at a fixed offset from the power disc, and it works because it
is pinned to the narrow strip of dark backdrop JUST OUTSIDE the card, where a
hovered card's halo is the only bright thing. The cards are white cartoon art, so
**any box placed ON a card reads 60-88% bright whether or not the cursor is
there.** Every "improvement" below moves the box further onto the card:

    1D sweep, 0-120 px along the box's       slot 4 never exceeds 11.0 at ANY
    own axis                                 offset, while slots 0-3 read 26-28
                                             at the shipped position
    2D sweep, dx +-140 dy +-90, take the     TRUE reaches 87.6 -- and FALSE
    brightest placement found                controls reach 70-79. One population
                                             (10.4), no threshold exists
    a band FOLLOWING the card's fitted rim   fixes the weak slot (7.0/11.0 ->
    instead of an axis-aligned box           25.0/26.5, in line with the others)
                                             and FALSE rises to 38.3, because
                                             EVERY card has a bright edge
    the SAME box, ROTATED to the card's      5/12 against the shipped 8/12 -- and
    tilt (size and offset untouched)         the angle estimate RAILED at its own
                                             search bounds (+14, -4) on most
                                             slots, so it was never an angle

**THE FIRST THREE WOULD HAVE SHIPPED ON THE TRUE NUMBERS ALONE.** "The weak slot
went from 7.0 to 25.0, in line with every other slot" is a real sentence about a
real measurement, and it is worthless without the FALSE column beside it. This is
10.4 with a specific cause worth naming: optimising a window's placement optimises
it toward whatever is brightest, and whatever is brightest is usually the class you
are trying to reject.

**THE TELL, BEFORE SPENDING THE NIGHT:** ask what supplies the CONTRAST. If the
answer is "the background it happens to sit on" rather than "the object itself",
the placement is load-bearing and is not a free parameter. A reader that searches
for its asset (10.23) is the opposite case and the freedom is correct there --
what distinguishes them is whether the thing being measured has its own signature
or is only bright relative to its surroundings.

**AND THE ONE THAT DID NOT FAIL WAS NEVER TRIED, BECAUSE IT NEEDS LABELS THIS
PROJECT HAS NEVER HAD.** `local_hand.selected_cards` measures which card has RISEN
above its fan anchor -- pure geometry, no brightness. Selecting requires the cursor
to be on that card, so **the frame before a slot newly rises is a frame whose
cursor slot is known**, from a signal the glow reader cannot influence. Every
earlier census of `cursor_slot` used the reader's own answer (10.22) or a human
reading a contact sheet. It needs no live change and runs on frames already on
disk.

**37. BEFORE REPORTING THAT A FUNCTION IS BROKEN, CHECK THE ARGUMENT SHAPE IT
WANTS. FIVE TIMES IN ONE SESSION THE CODE WAS RIGHT AND THE CALL WAS WRONG.**
2026-09-20, all mine, each one looking exactly like a defect in working code:

    read_phase(full_frame)          wants the HAND STRIP; its own first docstring
                                    line says "for a hand strip". Returned
                                    (None, {'cards': 0}) -- reported as "the engine
                                    cannot tell which half it is in". Given the
                                    strip: ('pitching', votes {pitcher: 3})
    homeplate_runner_present(list)  wants the DICT. crop_gameplay_regions returns a
                                    LIST of (label, image); all three production
                                    sites wrap it in dict(). Raised AttributeError
                                    -- reported as "a real bug on the live path"
    read_hand(...)[i]["power"]      there is no "power" key; it is "digit". Every
                                    row read None, and a whole false diagnosis
                                    ("the reader cannot read a visible card") was
                                    built on it before the docstring was read
    GameState(runners=int)          declared List[PlayerCard]. best_pitching_play
                                    does len() and raised; best_batting_play never
                                    reads it and accepted the int SILENTLY
    ocr_scoreboard(full_frame)      the parameter is literally named
                                    scoreboard_img. Passing the whole screen gave
                                    None/None and two confident misreads; given
                                    crops["scoreboard"] it is 12/12 exact, live and
                                    saved. THIS ONE COST A TEN-AGENT INVESTIGATION
                                    INTO A NON-BUG.

**THE TELL IS THAT THE FAILURE LOOKS LIKE THE BUG YOU EXPECTED.** Four of the five
produced None or an abstention -- exactly what a broken reader produces -- so the
wrong call confirmed the hypothesis that prompted it. The check costs one command:
`inspect.signature`, the first docstring line, and one production call site.

**AND A DEFAULT-TOLERANT SIGNATURE HIDES IT.** `GameState.runners` is annotated
`List[PlayerCard]`; one consumer calls len() and raises, the other never reads it
and takes an int without complaint. A field that one path validates and another
silently tolerates will be passed wrong eventually, and only one of the two will
say so.

**38. AN AGENT'S CONFIDENT EMPIRICAL CLAIM IS STILL A CLAIM. RE-RUN IT.** The same
session, a refuter reported that ocr_scoreboard returned {'your': [2,0,2],
'opponent': [0,0,0]} on 6 of 6 reads of a named PNG, and built a detailed
correction on it ("the reader is not broken on this screen"). Run against that
exact file -- hashed, 12 reads, 3 separate processes -- it returns None/None every
time. The claim did not reproduce. It was directionally right by accident: the
reader IS fine, but only when handed the crop, which is not what that agent said
it did.

The same round also had a refuter call a census script non-existent because a
listing was CUT AT 200 ROWS by the tool and it read the truncation as the whole
answer -- 10.16c's shape in a new instrument. **Pipe a listing to `wc -l` before
believing it is complete**, and treat "I ran it and got X" from a sub-agent as a
hypothesis to reproduce, not as a measurement.

**36. "IS THIS DEAD" NEEDS THREE INSTRUMENTS, AND EACH ONE IS WRONG ALONE.**
2026-09-20, deleting 385 lines. All three failures below were caught by an
instrument DISAGREEING with a hand-checked fact, never by the instrument itself.

**(a) A ONE-PASS REFERENCE COUNT UNDER-REPORTS, because dead code reads dead
code.** A scan of `graph_walk.py` reported **0 orphans of 100 top-level names**
while seven names in it were dead. `GOAROUNDS` is loaded at `:1032` and `:1036`
-- both inside a block after an unconditional `return False`, which CPython
never emits (`dis.dis` shows no GOAROUNDS at all). The count cannot see that.
**Seed the regions that are unreachable for reasons a count cannot see, delete,
rescan, and iterate to a FIXPOINT.** Round 2 of that loop found seven more
names, including `hand_digit_reader._WORKER` at 79 lines -- exactly the ones a
single-pass manifest leaves stranded, which is `_something_moved` in reverse.

**(b) THE `find | xargs grep` RECIPE IN SECTION 2 IS NOW TOO WIDE.**
`agent_progress/` holds **2,100+ .py files including FOUR copies of
orchestrator.py** and one of `graph_walk.py`. So

    find . -name '*.py' -not -path './.venv/*' -print0 | xargs -0 grep -l HOME_ROUNDS

returns `./graph_walk.py` AND
`./agent_progress/verify-sim/scratch_33608/graph_walk.py` -- a "reference" found
inside a COPY OF THE FILE BEING EXAMINED, reported as a live reader. That recipe
fixed grep's too-NARROW problem and created a too-WIDE one, and BOTH give a
confident wrong answer. **Exclude `agent_progress`, `drafts`, `backups`,
`_obsolete` and `tests_quarantine` when the question is "is this dead"; count
them separately, because a reference in a landed patch script is history, not a
caller.**

**(c) A SYMBOL REACHED ONLY BY `getattr` HAS NO STATIC REFERENCES AT ALL.**
`ban_grid.SHIELD_BOX` looked dead to every count. It is live:

    tools/state_viewer.py:909   _EDIT_CONST = {... "shield": "SHIELD_BOX" ...}
    tools/state_viewer.py:919   {k: list(getattr(bg, _EDIT_CONST[k])) for k in ...}

Deleting it breaks the live box editor with an AttributeError. That is the
`identify_edges` precedent reproduced exactly, and the only thing that caught it
was flagging every candidate whose NAME appears in a string anywhere. **Before
deleting any name, grep for it as a STRING, not just as an identifier.**

**AND THE UNIT OF PROOF IS THE THING YOU ARE CLAIMING ABOUT.** The same day, an
exhaustive trace of `hand_digit_reader` -- AST over every module, every public
function, the commit that cut it -- became the sentence "paddle_venv is CHECKED,
NOT USED". False: `result_ocr.py` spawns that interpreter for the result banner
on the live path. One consumer was checked and the claim was made about the
DEPENDENCY. **An exhaustive trace of the wrong question is still the wrong
answer**, and it reads exactly like diligence. See section 2.

**1. The commonest bug here: the code did nothing, and doing nothing looked
exactly like working.** Every bug found on 2026-09-01 had this shape; each fix
was two or three lines and finding them took a day. Before theorising about a
failure, ask what would be in the log if this step had never run at all — and if
the answer is "the same thing", fix the silence first.

The catalogue, as a pattern to recognise:

- a logger passed as `lambda m: None` (a conclusion was then drawn from a log
  that could not have contained the evidence)
- an early `return` on a `None` that writes nothing (corrections never ran, all
  run, and logged nothing — indistinguishable from "nothing needed correcting")
- a measurement taken and discarded (`walk_forward` returns how far the view
  moved; both step loops threw it away, so walking into an NPC looked like
  walking)
- a loop bound that cannot be reached (a test spun forever and the suite
  reported pass counts that were meaningless)
- a cached handle nothing revalidates (`chiaki_pid` trusted a dead process;
  every press "succeeded" into nothing)
- a success path and a no-op path with identical output (`_inject_press`
  returned True because the WRITE succeeded — that silently disabled every
  button in the system)
- a slow step and a hung step with identical output (a test "hung" at import;
  it never hung, it took 49.6s and its first `print` sat after all 110 cells)
- **a fix that produces output which looks like evidence and is not** (the
  frame-capture fix: four jpegs, correctly written, of the wrong moment)
- **a measurement that returns the same number everywhere and reads as a
  verdict** (`len(places.keypoints(img))` is 2 — the function returns a
  (keypoints, descriptors) pair — so every point of three prompt-zone runs on
  2026-09-07 was "wedged" at 2 keypoints, the harness backed off every move,
  and rich 1500-keypoint frames were filed as geometry. A count that never
  varies is not a count.)

**2. ONLY AN INTERVENTIONAL A/B COUNTS.** An association does not, however
significant, and neither does a mechanism that makes sense. `STALL_CHANGE` is
the canonical case: observational evidence gave Fisher **p = 0.00039** (runs
whose office leg went clean reached the next node 14/15; runs where the stall
gate fired, 0/5). Intervened on, it measured **6/10 against 8/10, p = 0.63** —
and the point estimate favoured the ORIGINAL value. The low view-change was a
SYMPTOM of an already-bad run, not its cause.

**3. n=3 CANNOT DETECT THE EFFECTS BEING LOOKED FOR HERE.** Power to detect a
full 1.0-depth effect (simulated, sd 0.6):

    n=3   power 0.00      n=6   power 0.72
    n=10  power 0.94      n=16  power 0.99

Every 3-trial A/B on this project has been reading noise, which is why so many
reversed. A permutation test on the "first positive navigation result"
(`[2,1,2]` vs `[2,3,3]`, including 2 full routes against 0) gives **p = 0.298**.
**Minimum for a navigation A/B: 10 trials per arm, interleaved.** A finer metric
does NOT rescue a small n — a per-leg binary outcome was simulated and is WORSE
(power 0.26 at n=10 against 0.94 for depth).

**4. A THRESHOLD MUST SIT BETWEEN TWO MEASURED POPULATIONS, NEVER INSIDE ONE.**
Four bugs of this exact shape in two days: a confirm delta under the noise
floor; `WHITE_LEVEL` under the unselected text; pause-screen brightness (0.927
vs 0.944 — no separation exists); and `STALL_CHANGE` cutting through a unimodal
distribution (values 3.1 to 7.9, one population, so the gate fired on 5 of 20 as
false positives). **Plot the distribution first.**

**5. INTERLEAVE THE ARMS, AND NEVER COMPARE ACROSS SESSIONS.** Route performance
has a large session-to-session component that dwarfs the effects being measured
— the same node measured 3/3 one morning and 4/20 that afternoon with no code
change. Interleaving is what saves a measurement taken under varying load;
blocking the arms would confound the arm with the hour.

**6. WHEN BOTH ARMS DEGRADE TOGETHER, SUSPECT THE ENVIRONMENT.** A change that
affects only one arm cannot move both. A run where every arm got worse at once
turned out to be the console falling asleep — a capture straight afterwards
measured a frame delta of **0.00**. The harness treated CANNOT SEE as DID NOT
ARRIVE. Check the stream is alive before and after every trial and record
`None`, never a failure.

**7. CHANGE ONE THING, THEN MEASURE.** Two route changes in one restart cost the
attribution.

**8. STATE n ALONGSIDE ANY RATE.** A route rate quoted at "~40%" from 5 attempts
was 8% over 24.

**9. MUTATION-TEST ANYTHING LOAD-BEARING.** Break the fix, confirm the test
fails, restore. A phase-repair test passed with the guard removed until the
mutant exposed the hole; a wiring assertion once passed because it matched the
function's own `def` line.

**10. MUTATION TESTING LIES IF THE FILE SIZE DOES NOT CHANGE.** CPython
validates a cached `.pyc` on (mtime, size), so a same-size edit runs STALE
BYTECODE and the mutant never executes. Worse, the same cache then made a CLEAN
file report 8 failures — `-B` stops Python WRITING bytecode but not READING it.
Delete `__pycache__/<module>*.pyc` between mutants. Also: `str.replace(a, b, 1)`
on a pattern that appears twice mutates half the code — **count the occurrences
first**.

**10b. AND RE-COUNT AFTERWARDS, BECAUSE PROSE THAT QUOTES CODE CREATES NEW
MATCHES.** Counting first is necessary and not sufficient. A patch that removes
a constant and leaves a comment EXPLAINING the removal quotes the very names it
is deleting, and every quote is a fresh match for any later search. Three edits
to `compass.py` were corrupted this way in one sitting, 2026-09-13, each
differently:

    the comment quoted `    pitch = ...` as `#     pitch = ...`, and
    "#     pitch" CONTAINS "    pitch" -- so replace(dead_line, "") deleted the
    line out of the middle of the NEW COMMENT and left the real dead store
    untouched, with the count having been taken before the insertion

    a later `assert "PITCH_PX_PER_90 = 293.0" not in src` fired on CORRECT code,
    because the new prose says "PITCH_PX_PER_90 = 293.0 lived here"

    a second span's anchor went from 1 occurrence to 2 the moment the prose
    landed, so its excision refused to run

**THE RULE: do every CODE removal first, assert the code is gone, and insert the
prose LAST, in one operation.** Then assert on an ASSIGNMENT (`^NAME\s*=`) or on
the code half of each line (`line.split("#", 1)[0]`), never on a bare substring —
a substring test cannot tell a comment from a constant and will fail on correct
code, which is section 11's shape pointed at the patch script instead of the
test.

**10a. A MUTATION DRIVER'S RESTORE MUST OWN ITSELF, BECAUSE THE THING THAT
KILLS THE DRIVER DOES NOT CARE WHICH LINE IT WAS ON.** 2026-09-07: an inline
driver mutated `places.py:491` in the checkout, and the tool running it hit its
600 s ceiling and killed the child between mutate and restore. `places.py` sat
on disk with `if ratio < MIN_RATIO:  # MUTANT` and the wrong sha for eleven
minutes, discovered only because a process listing showed the driver gone.
Nothing was live to import it — an hour earlier OPEN-5 would have (10.17). The
first driver on Snoopy had the same shape and captured a MUTANT as its
baseline. So: the restore goes in a `finally`; any driver longer than a minute
runs in the background from the start with its output flushed to a file; and
after ANY kill, verify the sha of every file the driver touches before doing
anything else. `git status --porcelain` on a tracked file is the one-line
check.

**11. A TEST MUST NOT ASSERT AGAINST THE CONSTANT IT IS GUARDING.** Checking
`mag_for(x) <= USABLE_MAX` rises with `USABLE_MAX` and passes forever. Pin the
literal.

**12. BEWARE THE VACUOUS STATISTIC.** "68 of 68 turn steps had |want - got| <=
4.0, so 100% are no-ops" is CIRCULAR — `turn_to` only returns once the error is
inside tolerance, so that inequality holds BY CONSTRUCTION. It looked
devastating and measured the loop's exit condition. The real version compares
the spread of COMMANDED bearings against the spread of ACHIEVED headings.

**13a. THE "NEVER RUN OFFLINE WORK DURING A LIVE RUN" RULE WAS BROADER THAN ITS
EVIDENCE (measured 2026-09-06).** **And narrower than I then treated it (2026-09-07):**
the measurement below covers THE SUITE. It does not cover a 20-minute OCR or
ORB sweep over 4,000 frames, even under `taskpolicy -b`; the user watched the
stream go sluggish while two of those ran beside the goal-leg A/B and asked for
the run to be paused. Anything CPU-bound that is not the suite waits. The 242ms figure below is real and it is about
FOUR PARALLEL MUTATION SWEEPS at load 273-333. It was then applied to the
ordinary suite, which is a different workload at a thirtieth of the load, and
that cost real serialisation time.

Measured directly, sampling `sleep(0.005)` overrun continuously for the length
of a suite run -- the quantity that matters, because `slow_traverse` holds the
stick and SLEEPS OUT each push, so overrun IS leg distance error:

    idle control                 median 1.21ms   p99 1.35ms   max 2.46ms
    the suite, JOBS=4, normal    median 1.26ms   p99 2.69ms   max 9.73ms   203s
    the suite under taskpolicy -b median 1.26ms  p99 1.35ms   max 7.79ms   636s

30,787 samples during a real suite run at normal priority, and **not one sample
exceeded 50ms**. Against a 0.79s push, the worst overrun is 1.2%. **So the SUITE
may run during a live run.** Mutation sweeps at load 273-333 are NOT covered by
this and stay serialised -- that load was not reproduced here.

`BASEBALL_NICE=1 ./run_tests.sh` puts the suite on the Efficiency cores via
`taskpolicy -b` and makes p99 identical to idle. **It also costs 3.1x wall
clock, and run naively that is a trap**: the slowdown pushed `test_map_admit.py`
(58s normally) and `test_affected_tests.py` past the 300s ceiling, and both were
reported HUNG -- the ceiling censoring the work it had just slowed down, turning
a green suite into two failures. That is 10.14 in a new place. The flag
therefore raises `TEST_TIMEOUT` to 1200s itself, and an explicit
`TEST_TIMEOUT` still wins.

**13. MUTATION TESTING IS EXPENSIVE ON THIS MACHINE.** Four parallel sweeps drove
the load average to 273-333 and the suite to ~2 files per FOUR MINUTES. The
cause is likely I/O — this is a work machine with Sophos Anti-Virus, and
mutation testing writes a source file thousands of times. **Do not disable it**
(the user has said so). Consequences: **never take live timing measurements
while a sweep runs** — Python's `sleep` degrades from ~5ms to as much as 242ms
under saturation, which corrupts every walked leg. Run heavy offline sweeps and
live console work IN SERIES.

**14. A TIMEOUT MUST NOT CENSOR ONE ARM.** An `attempts` A/B used a 420s ceiling
and 3 of 6 deep-arm trials hit it — the ceiling censored precisely the arm whose
mechanism is "spend longer". Also: `signal.alarm` did NOT interrupt a 590s trial,
because the process was blocked inside a capture call. Enforce timeouts from
outside the process.

**15. KEEP A FRAME.** Cause A got a diagnosis within an hour because it had
numbers; Cause B stayed unexplained for days because nobody kept a picture. One
jpeg per failure settles arguments immediately — but **check what moment it
captures**, because a frame taken after recovery, or before the attempt,
describes something else entirely and looks exactly as authoritative.

**16. A SUBAGENT THAT IS KILLED LOSES EVERYTHING IT HAS NOT WRITTEN DOWN.**
On 2026-09-05 four parallel workflows hit a usage limit mid-flight and 18 agents
were killed. One had spent 179 tool calls and twelve minutes reading archived
frames; it returned nothing, and the transcript holds its tool calls but not its
conclusion. Re-running costs the same tokens again.

So any prompt that dispatches a subagent must tell it to write to
`agent_progress/<label>/progress.md` **as it goes** — every few tool calls, not
at the end. A file written on completion is lost in exactly the case it exists
for. **This is the DISPATCHER's job**: the agent has no way to know the
convention, so an instruction missing from the prompt means no notes get written
at all.

A DIRECTORY per agent, not a single file, because the script that produced a
number belongs next to the number — and CLAUDE.md forbids findings in `/tmp`,
which on this machine was once found as 825 empty directories with every file
gone. Scripts, extracted data and plots go in the same directory as the notes.

The file separates **Established** (verified, with the command or file that
verified it) from **Assumed** (working from, not checked). A half-finished
analysis restored later reads exactly as authoritative as a finished one, and
this project has lost days to output that looked like evidence and was not — so
anything under Assumed is re-verified before it is built on.

`agent_progress/` is gitignored and safe to delete wholesale; its README carries
the template.

**Model selection is the dispatcher's job too.** Any sub-agent dispatched for
routine scouting, log parsing, static reading or coverage checking runs on a
cheap, lightweight model (Haiku). Flagship models are reserved for complex
architectural reasoning, and only when a cheaper model demonstrably cannot do
the step. Measured 2026-09-07: four flagship agents drafting scripts burned
~850k tokens in five minutes, two of them on ideas the same day's A/B data had
already killed; the static QA audit on Haiku, ten agents, cost 1.16M for an
evening's findings. Token bleed is a failure of the DISPATCH, not of the agent.

**16c. THIS SHELL IS zsh WITH BSD/ALTERNATIVE TOOLS, AND FOUR COMMON GNU/bash
IDIOMS SILENTLY DO NOTHING HERE.** All four were hit in ONE evening, 2026-09-13,
while VERIFYING other work -- so each one is 10.1 inside the instrument: the
check did not run, and "found nothing" is indistinguishable from "nothing is
wrong".

    find -newermt '3 hours ago'   this machine's find is bfs: "Invalid
                                  timestamp" AND EXITS 0. Printed nothing, the
                                  `|| echo` fallback never fired, and it read as
                                  "no agent wrote a progress note" -- which was
                                  false; 17 had.  USE -mmin -180.
    awk '/\byes\b/'               POSIX awk has no \b. Matches NOTHING, always.
                                  Use grep -w, or a plain substring.
    for f in $list                zsh does NOT word-split unquoted parameters.
                                  The whole list becomes ONE argument ->
                                  "File name too long". Use
                                  `while IFS= read -r f; do ... done < file`
                                  or zsh's ${(f)list}.
    cmd | tail                    $? is TAIL's status, not cmd's. A script that
                                  died on a traceback reported EXIT=0. Capture
                                  the status before piping, or use
                                  ${PIPESTATUS[1]} / set -o pipefail.

There is no `timeout` either (GNU coreutils); use the harness timeout or
`perl -e 'alarm shift; exec @ARGV'`, which run_tests.sh already does.

**AND `grep` HERE OBEYS `.gitignore`, SO EVERY "NOTHING REFERENCES IT" SWEEP IS
BLIND TO WHOLE DIRECTORIES (2026-09-17).** `type grep` resolves to a function in
`~/.claude/shell-snapshots/`, and the function is **Claude Code's own, not RTK's** -- I
attributed it to RTK first and was wrong; the snapshot contains zero mentions of rtk. It
execs the `claude` binary under `ARGV0=ugrep`, i.e. Claude Code ships ugrep inside itself
and routes `grep` to it:

    ARGV0=ugrep "$_cc_bin" -G --ignore-files --hidden -I --exclude-dir=.git ...

**`--ignore-files` is the whole cause. Its default FILE is `.gitignore`**, and ugrep then
ignores matching files AND DIRECTORIES in that directory and every subdirectory -- so it
does not filter results, it never descends. On this repo that silently removes
`agent_progress/`, `models/`, `armor_venv/`, `demos/` and `screenshot_log/`, and reports
the truncated answer as a complete one. Measured on the same pattern and tree:

    grep -rl ArmorOCR --include='*.py' .                          2 files
    grep -rl --no-ignore-files ArmorOCR --include='*.py' .        8 files
    find . -name '*.py' -print0 | xargs -0 grep -l ArmorOCR     8 files

**THE FIX IS ONE FLAG, `--no-ignore-files`**, which reproduces `find | xargs` exactly.
Reach for it on any completeness claim; `git grep --no-index` or an `os.walk` with an
EXPLICIT skip list work too, but they are not needed for this.

Six files were missed and four are `agent_progress/bakeoff/`, which is where the ONLY
functional references to the deleted OCR models lived -- the two scripts that load the
weights. A sweep of mine reported "nothing references it" having never looked in the one
directory that did. An agent using `find | xargs` found them.

**It is the most dangerous instance of 16.16c's shape**, because "does anything use this"
is the question asked immediately before an irreversible delete. And a FILENAME is a
reference too: `grep --include="*.json" typhoon` found nothing while `typhoon_results.json`
sat on disk, because grep searches contents, not names.

**AND THE SAME TRAP LIVES IN A WAIT CONDITION, WHERE IT COSTS AN HOUR INSTEAD OF A
WRONG ANSWER (2026-09-17).** Two background waiters of mine spun until the user asked
"tasks are still running" -- long after the work they were waiting on had finished.
Neither condition could EVER have become true:

    until [ "$(ps aux | grep -c '[g]raphify')" -le 1 ]; do sleep 10; done
        echo "graphify done"                     <- and there is the bug

    the [g]raphify bracket keeps the PATTERN from matching itself. It does not
    protect the REST of the command line: `echo "graphify done"` sits in the same
    argv, `ps aux` prints it, and the count never drops below 2. The loop was
    watching for its own echo.

    until [ "$(grep -c '"type":"completed"' "$J")" -ge 4 ]; do sleep 10; done

    the journal writes `"type":"result"`. I waited on a key that does not exist,
    which is the `typhoon_results.json` mistake again -- grepping for the wrong
    thing and reading the silence as "not yet".

Both are 10.1's "a loop bound that cannot be reached", and both are SILENT by
construction: a wait that will never end is indistinguishable from work that is
taking a while, which is exactly why they ran for an hour.

**THE RULE, and it is one command:** before arming a wait, RUN ITS CONDITION ONCE BY
HAND and confirm the number is what you think. `ps aux | grep -c '[g]raphify'`
returning 2 with no graphify running answers it instantly. For a self-match, count a
field rather than the line -- `pgrep -c -x graphify`, which matches the executable
NAME and cannot see your own argv. And prefer a wait that is BOUNDED, so a wrong
condition costs one timeout instead of the session.

**THE RULE THIS EARNS:** a verification command gets the same suspicion as the
code it verifies. Before believing a check that came back CLEAN, make it fail
on purpose once -- the same discipline section 10.9 demands of a test. A check
that cannot fire is worse than no check, because it is reported as evidence.
**That applies to a WAIT as much as to a grep**: "still running" is a claim, and an
unbounded loop asserts it forever without ever checking.

**16b. IN A FAN-OUT, EVERY DEFAULT IS A COLLISION, AND OMITTING A SETTING IS
NOT NEUTRAL.** Written 2026-09-13 after breaking BOTH halves of the rule above
in one evening, having read it first.

Two workflows dispatched **57 agents**. The nine hunters were fine: each got its
own axis key, so each got its own directory, and each left a 85-221 line
`progress.md` with the scripts that produced its numbers sitting beside them --
which is what the rule asks for, and what survives a kill.

**The other 46 were refuters spawned from ONE prompt template, and the template
carried ONE literal path.** Every skeptic was told to write to
`agent_progress/qa4-refute/progress.md`. They overwrote each other all evening:
28 lines survived for ~24 agents, and the file's own header names a single lens,
so 23 agents' reasoning is simply gone. The same template also omitted
`opts.model`, and in a workflow script **omitting the model INHERITS THE
MAIN-LOOP MODEL** -- so 46 agents ran grep, `ast.parse` and caller-tracing on
the flagship at high effort, which is precisely what the paragraph above
measured and forbade.

    the shape: a per-agent setting written ONCE in a shared template
               produces N agents that are identical where they must differ

So the check before any fan-out is not "did I follow 10.16" -- I had -- it is
**"which fields in this template must VARY per agent, and does each actually
vary?"** Today that is exactly two:

    the scratch path   parameterise it:  <wf>-refute/<claim-slug>-<lens>/
                       a literal path in a loop body is N agents, one file
    the model          set it EXPLICITLY: haiku for grep / AST / caller-trace /
                       file census; flagship only for synthesis, and for
                       adversarial refutation of a finding on the money path

Both failures are SILENT. A clobbered note looks exactly like a note nobody
wrote, and a flagship agent grepping looks exactly like a cheap one grepping
until the bill arrives -- 10.1's family, one level up, in the dispatch itself.

**AND VERIFY THE NOTES EXIST RATHER THAN TRUSTING THE INSTRUCTION**, because
the instruction being in the prompt is not evidence it was followed. The check
that was run first here was
`find agent_progress -name progress.md -newermt '3 hours ago'` -- and this
machine's `find` is **bfs**, which rejects a relative timestamp with
`Invalid timestamp` AND EXITS 0. It printed nothing, the `|| echo` fallback
never fired, and the empty output read as "no agent wrote anything", which was
false. Use `-mmin -180`. A verification that cannot fire is worse than none,
and it is the same bug the fan-out itself had.

**16a. A SUB-AGENT'S SCRATCH TREE IS A COPY, NEVER A SYMLINK FARM, AND NEVER
INSIDE THE CHECKOUT.** 2026-09-07 22:47: a skeptic building a "scratch copy
with symlinks to the rest of the checkout" ran its `ln -s` loop with the
CHECKOUT as the destination, and 65 tracked test files under `tests/routing/`
became symlinks pointing at their own absolute path. Nothing failed for half
an hour: the one test file it copied was real, its runs were green, and the
damage surfaced only when the pre-commit hook hit "Too many levels of
symbolic links". `git status --porcelain | grep '^ T'` lists the casualties
and `git checkout --` restores tracked ones; an UNTRACKED file replaced this
way is gone. Every dispatch prompt says: build scratch trees with `cp`, under
the scratchpad, and never run `ln` with a path inside the checkout. After any
sub-agent finishes, `find . -type l` outside the venvs and `git status` for
`T` entries, before trusting anything.

**17. THE A/B RUNNER RE-IMPORTS `graph_walk.py` FROM DISK ON EVERY TRIAL, SO A
MUTANT ON DISK FOR ONE SECOND IS THE CODE A LIVE TRIAL RUNS.** `_harness.run_trial`
spawns `python <script> --one-trial <arm>` per trial — that is the design, so
process death is the restore and no cleanup can reinstate a stale default. The
cost of that design is the other direction: every child starts cold and loads
whatever `graph_walk.py`, `places.py` or `slow_traverse.py` is on disk at that
moment. Mutation-test a guard in the checkout while OPEN-5 is walking legs, and
the next trial walks with the guard removed, arrives or does not, and is scored
as an arm result. No error, no log line, nothing to distinguish it from the
arm.

Found on 2026-09-07 by reasoning, before it happened: a QA workflow was about
to mutate `graph_walk.py` in place while `overnight/ab_attempts.py` had the
console. Stopped. The first replacement used a git worktree, which is isolated
from the import but shares the disk, and §10.13's I/O hazard is the disk — so
that was stopped too. **The rule: while `console_lock` is held, the checkout is
read-only, and mutation testing goes to Snoopy (`Snoopy_testing.md`).**
Static analysis — reading, grepping, `ast.parse` on source text with
`python -B` — is fine; it writes nothing.
**18. A DEFAULT ARGUMENT IS BOUND ONCE, WHEN THE `def` RUNS, AND THAT BREAKS
A/B ISOLATION SILENTLY.** `leg_reliability` declared every public function as
`def rate(a, b, path=STORE)`. `STORE` is a string, captured at import — so
`leg_reliability.STORE = "arm_A.json"`, the natural way for an A/B harness or a
test to give one arm its own record, changed NOTHING: every call still read and
wrote the import-time file, and nothing said so. With `SPEED_FROM_RELIABILITY`
on, an interleaved A/B would have had both arms writing one store, trial N's
speed a function of trials 1..N-1 across both arms, and the harness reporting a
clean redirect. `press(post_delay=ACTION_DELAY)` is the same trap, which is why
that parameter takes `None` (§5). Fixed 2026-09-07: `path=None`, resolved at
call time through `_store()`, pinned by `tests/routing/test_leg_reliability.py`
with a check that fails on the bound default. **The rule: a module-level knob a
test or harness may redirect is read at CALL time, never captured in a
default.** Grep for `=STORE)`, `=PATH)`, `=DELAY)` shapes before trusting any
redirect.

**19. SAVE PATCH SCRIPTS BEFORE EXECUTING THEM, AND ASSERT EVERY ANCHOR BEFORE
WRITING ANY FILE.** 2026-09-07 22:00: a two-file patch script asserted and wrote
`overnight/chain_trials.py`, then failed an anchor assert on `tools/dashboard.py`
— with the harness file already on disk, mid-batch, and the next trial child
died on it (rule 21 broken by a script that was half right). One assert block
for all files, then all writes. **19. SAVE PATCH SCRIPTS BEFORE EXECUTING THEM.** When an agent writes a script
to parse, slice or patch a critical project file — this file, the map, a
harness — it saves the script to disk first (the scratchpad is fine) and gates
the atomic write behind strict assertions on every anchor it will touch. If an
assertion fires, the logic is preserved and the retry is a one-line fix, not a
300-line re-send; if the write is reached, every seam has already been checked.
2026-09-07: the eight-edit patch to this file was written inline, its GRAVEYARD
assert was off by one, and the whole script had to be re-sent to fix one
integer. Saved, the retry would have cost nothing. The assertion that fired
BEFORE the write is the pattern; the re-send is the cost of not saving.

**20. PRE-SLEEP HANDOFF INTEGRITY.** Before an agent enters an unattended
overnight or long-running background state, it updates and COMMITS the current
state and the execution plan to `HANDOFF_NOW.md` — what is running, where its
artefacts land, what happens next and in what order, and the rules in force. If
a process drops or hits a ceiling mid-night, the morning session must find the
exact active plan and state immediately, without relying on chat history. A
plan that lives only in the conversation is lost in precisely the case the
handoff exists for (the same shape as 10.16, one level up).

**21. SEQUENCING OVERRIDE FOR IN-FLIGHT RUNS.** Never refactor, edit or modify
a module on disk while an active process or live console test is importing it
fresh — a harness's trial children re-import `graph_walk.py`, `_harness.py` and
their neighbours on every trial (10.17 is the concrete instance). Background
refactoring, dependency audits and automated QA passes are strictly SERIALISED
behind the live run: held in queue until every live console trial has completed
AND its evidence is committed. Read-only work may proceed; anything that writes
into the import path waits. "It is a small edit" is not an exception — the
child does not know how small it was.

**22. A MATCHING COUNT IS NOT CORRESPONDENCE, AND SCORING ON IT MANUFACTURES A
CLEAN RESULT OUT OF TWO ERRORS.** 2026-09-09: the local hand reader's accuracy
was scored by lining its rows up with the paid model's cards BY POSITION on
every hand where the two counts matched. The reader can miss one card and
invent another in the same hand — the count still matches, and every column
after the first error is compared against the WRONG card. The table that came
out looked like a finding: 4 read at 90%, 5 at 88%, but 6 at 31%, 7 at 33% and
9 at 0%, tracking template counts so neatly that the diagnosis wrote itself.
It was an artefact. A contact sheet of the "missed 6s and 7s" showed FIELDING
PLAY cards.

Re-scored with correspondence PROVEN — the counts match AND the set of slots
each side calls tactics matches — only **10 of 57 hands could be compared at
all**. The real defect was never the templates; it was that the reader did not
agree with the model about POSITIONS on 47 of 57 hands.

It also corrupts what is built on it: 79 templates were cut using that
alignment, and six were wrong — three labelled one card off (a 6 labelled 7, a
5 labelled 6, a 4 labelled 7) and three that are not digits. Each matched its
own source crop at correlation 1.0000, so it read that crop wrong forever
after, confidently, at score 1.000.

And it hides itself in the metric: the old reader scored **41 of 41 = 100%** on
its 10 aligned hands, and two of those hands were two errors cancelling — a
mouse's nostril padded the count and read "5" where the missing card's power
was 5. **A pipeline whose own output defines the alignment cannot be scored on
that alignment.** Require an independent agreement — here, the kind pattern —
and report how many samples were excluded, never just the rate.


**23. A READER THAT CROPS AT A FIXED ANCHOR IS READING THE WRONG PIXELS THE MOMENT
THE THING MOVES -- AND IT REPORTS THAT AS "I AM NOT SURE".** 2026-09-09: two
readers, built months apart, were held at 0% and 40% by the same defect, and in
both cases the abstention rate read as "the recogniser is weak" when the
recogniser was never shown the object.

    reader          what it cropped at        coverage before -> after
    the shield      a fixed offset below      0%    -> 98.4%   cross-session
                    the power disc
    tactics type    the SLOT anchor, in a     40.5% -> 93.6%   cross-session
                    180px-wide box

The shield's offset varies because **the cursor lifts a card and the badge rides
with it**, so a window measured on unlifted cards found the badge on 8% of one
digit. The tactics banner's box was wide enough to reach past the card and take
in the NEIGHBOUR's banner, so the correlation was matching two cards at once and
collapsed whenever the neighbour differed.

**THE FIX IS THE SAME ONE THAT RESCUED THE RUNNERS READER: SEARCH FOR THE ASSET.**
These are sprites -- one badge, one banner, identical every time -- so
`cv2.matchTemplate` over a generous window answers "is it there" and "which one"
at once, with no assumption about where it sits. The gate then sits between two
measured populations: the shield's peak correlation is p05 0.843 on shielded
cards against p99 0.541 on unshielded, an empty band, and SHIELD_MIN is its
midpoint.

**HOW TO RECOGNISE IT WITHOUT GUESSING.** Build a contact sheet of the cards the
reader called unsure and LOOK. The tactics one was settled in a single glance:
the banner text was PLAINLY LEGIBLE in nearly every "unsure" card, sitting off to
one side with a stranger's banner beside it. A recogniser that cannot read
legible text is not failing to recognise; it is being handed the wrong crop.
Section 10.15 in a new place -- and the cheapest diagnostic on this project.

**AND MEASURE THE OFFSET FROM WHAT WAS FOUND, NOT FROM THE ANCHOR.** The first
shield measurement put dy at 48-68px with a 20px spread and looked like a fixed
asset; it was measured against the SLOT anchor, so it was reporting the cursor
lift as if it were sprite variance. `read_hand` rows now carry the found `y`
alongside `x` for exactly this reason.

**THE PAID MODEL IS NOT GROUND TRUTH HERE, AND THE CONTROL SAYS SO.** Nine of the
ten remaining shield disagreements are cards with NO BADGE AT ALL that the paid
model gave a number to. The mechanism is measured, not asserted: on the 684 cards
where the badge IS found, the claimed `secondary` equals the card's own POWER
**0 times**; on the 20 where it is not, **5 times**. It is reading the card frame.
That is the sixth independent way this model has been shown wrong (three 6s as
5s, discards 0/8, a Fielding Play bonus, four phase labels, a runner's name).

**A TEST FOR THIS DOES NOT BITE BY DEFAULT.** Removing the tactics recentring left
every check in its test file green, because the fixtures all sat near their
anchors. It needed fixtures chosen for how far OFF the anchor they sit -- 43px in
y, 63px in x -- and the "the anchor alone cannot read it" half scored at the
anchor DIRECTLY, because the reader's own fallback tries both anchors and would
have masked it.


**30. A TEMPLATE MUST BE KEPT AT ITS NATIVE SIZE AND NEVER AVERAGED ACROSS EXAMPLES.**
2026-09-10, building the RESULT screen reader -- the last field with no local answer, and
the one paid call left in the turn loop. Three attempts, and the first two produced
populations that OVERLAPPED:

    what was cut / how it was scored                 result frames   non-result MAX
    the union of every bright blob in a wide band      0.497-0.547        0.603
    the word, STRETCHED to one size, banks AVERAGED    0.370-0.441        0.428
    the word, at NATIVE size, one template per example 0.955-0.988        0.733

The first is 10.23 in a new place: the union swallowed the matchbox labels along the top
edge, so two thirds of the "template" was scenery. The second is the new lesson and it
has two halves, both of which read as tidiness:

  * **STRETCHING destroys the discrimination.** WINNER is wider than LOSER; resizing both
    to one box made them the same shape, and after `TM_CCOEFF_NORMED` normalises away
    brightness there was almost nothing left to tell apart. Every WINNER frame matched the
    LOSER bank. It also means the template no longer has the size of the thing on screen,
    so the search is looking for something that is not there.
  * **AVERAGING blurs two different things into one.** The banner's arch FLATTENS as it
    animates in: the same word measures 102x22 in one frame and 95x14 in another. Averaged,
    neither is matched. Keeping each example as its own template costs nothing -- the score
    is the max over the bank -- and is what took the reader from 0.44 to 0.98.

**AND SCORE IT ACROSS SESSIONS, BECAUSE A TEMPLATE MATCHES ITS OWN SOURCE AT 1.000.** The
native-size version's first table read "result frames 1.000, non-result max 0.495, EMPTY
band" -- and every one of those 1.000s was a frame that had supplied a template (10.22's
shape). The real measurement came from 31 result screens found in OTHER runs' `stream.mp4`
recordings, at 960x540 and 1920x1080: 0.955-0.988, both classes, adjudicated by eye.

**THE CENSUS SIZE IS THE at_table LESSON AGAIN, AND THIS TIME IT PAID.** A 16,381-frame
still census put the non-result maximum at 0.543. Sweeping every 20th frame of all 17
archived run videos -- 55,937 more frames -- raised it to **0.733**, against a gate of 0.75.
The four highest were extracted and LOOKED AT: all four are result screens caught HALF
FADED, on the way in or out. So they are not false positives, they are the reader
abstaining during the fade, and that costs nothing because the banner then sits fully
opaque for a measured 4.0 s at its shortest (25 sightings, median 7.0 s). Zero false
positives in 72,318 frames. **Had the four not been looked at, the honest reading of the
same numbers would have been "the gate has 0.017 of headroom" and the reader would have
been rebuilt for nothing.**

`local_state.read_result(full_frame)`; `tests/minigame/test_result_reader.py` (7 mutants,
all caught). It takes the WHOLE frame -- handed a crop, the scaled templates collapsed to
4x4 and `matchTemplate` returned a number anyway (10.1's "a success path and a no-op path
with identical output"), so there is now a floor on the input width.

**31. A CLASSIFIER WITH A MISSING CLASS DOES NOT ABSTAIN -- IT MANUFACTURES NEGATIVES, AND
THEY POISON THE CENSUS THAT WOULD HAVE CAUGHT IT.** 2026-09-10, the same reader, hours later.

The result reader shipped knowing WINNER and LOSER. There is also a **DRAW!**, and 5 of the
52 matches on record are draws. The reader called every draw "not a result screen" at
0.42-0.49, `local_game_state` fell through to the hand reader, and the loop reported
`hand: 0 rows, expected 5` about a screen with no hand on it.

**THE SELF-CONCEALING PART.** The census that was supposed to catch this listed its top four
"non-result" frames by score. **Two of them were draws** -- `r2_0092` and `r3_0073`, both
plainly showing DRAW! over the medallion. They ranked highest among the negatives precisely
BECAUSE they were the thing the reader could not name, and being unnameable is what filed
them as negatives. One was even promoted to a test fixture called
`top_negative_turn_768.jpg`. So the missing class inflated its own false-negative rate into
the negative population and reported the gap as healthy headroom. **A census cannot discover
a class its own labeller does not have.** The only thing that broke it was opening the frames
a stalled run was staring at.

**IT ALSO HID A SECOND FORM OF THE SAME WORDS.** Every shipped template was the SETTLED form
-- a small ARCHED word on a thin bright arc. Mid-animation, before the arch sets, the word is
LARGER and FLAT and scores ~0.50. A visibly-legible LOSER read "not a result screen".

**AND A DRAW IS NOT A LOSS.** `run()` prefers a score comparison over `result_won` for
exactly this reason -- `result_won` is a bool and cannot express a tie. But `ocr_scoreboard`
is not reliable on the RESULT screen: over 76 draw frames it reads both rows on **12**, and
one of those 12 returns `[0,1,5]` against a board plainly showing `1 0 1 / 0 1 1`. A wrong
score is worse than no score, because `run()` acts on it. So the reader supplies NO scores
and names the outcome directly, and `run()` prefers that over both. Mapping draw ->
`result_won=False` would have logged every draw as a loss; that mutant is pinned.

**THE GATE MOVED, AND NOT TO THE MIDPOINT.** With three classes the negative population
reaches **0.742** (seven frames extracted and adjudicated: all of them the world -- the bar,
the dealer prompt, the office door), which left the old 0.75 with 0.008 of headroom. The two
errors are not symmetric: a false positive logs a match that never finished, a false
negative costs one poll because the banner holds 4.0 s at its shortest. `RESULT_MIN = 0.80`
sits 0.058 clear of every adjudicated negative and far under the held-out p05 of 0.954. It
costs exactly one of 342 held-out frames -- a half-transparent DRAW! ghosting in.

**A TEMPLATE CUT "EVENLY ACROSS THE RANGE" GRABS THE FADE.** Spreading the new bank across
the word's area range took 14x39 and 10x36 crops holding a stroke or two. A tiny template
correlates with anything: a turn frame with no banner on it read DRAW at 0.935, and every
negative rose (the quest log 0.543 -> 0.682). Verified words run 82-102 px wide at reference
scale and fragments 36-39, so the floor sits between two measured populations.

**THE SHAPE TO RECOGNISE.** Before trusting any classifier's negative population, ask what
it CANNOT name -- and go and look at its highest-scoring negatives, because that is exactly
where the unnameable class will be sitting.


**24. THE PAID VISION MODEL DOES NOT READ CARDS -- IT ANSWERS WITH A DEFAULT, AND THAT
DEFAULT WAS HIDING EVERY LOCAL NUMBER BEHIND IT.** 2026-09-09, at the user's call:
*"comment out the API reads for all card reading... leaving them in is hiding the real
values and your also wasting my IRL money."* Both halves measured:

- **It never read a card NAME.** Over 2,171 recorded hand cards `name` came back as
  'Batter' (493) or 'Pitcher' (394) -- the TYPE BANNER, the only text on the card --
  plus '' (113), 'None' (274), 'Unknown' (23), and 57 invented names including SIX
  spellings of the same one (M. J. / P.J. / J.J. / M.J. / P. J. / R.J. Gain). Section 3
  has said "hand cards do not display a name" since day one.
- **It answers on frames with nothing on them.** On 32 of 33 crops containing NO CARDS AT
  ALL it returned a full five-card hand with powers and shields; on frames that did
  contain cards, 325 of 327. "Five cards" is a DEFAULT, the same shape as `discards_left`
  answering 2 on 286 of 360 turns.

The second one is why this mattered beyond the bill: those are exactly the frames the
LOCAL reader refuses, so the local reader's "failures" were being scored against
fabrication. `PAID_READS_CARDS = False` in orchestrator; nothing is deleted and the flag
restores it.

**THE ONE FIELD WHERE THE PAID MODEL WAS RIGHT AND THE LOCAL READER WAS WRONG** is `kind`,
and it is worth knowing because it is the exception: the fan decides kind BY POSITION, and
a slot no candidate reached was emitted as `tactics` by default -- wrong on 10 of 17. I
reported the opposite before opening the frames, and the contact sheet corrected me.

---

**25. THE CAPTURE MOMENT, NOT THE READER, IS WHAT IS LEFT -- AND THE RETRIES WERE AN
ACCIDENTAL WAIT MECHANISM.** Measured over 514 recorded turns before changing anything
(`agent_progress/convergence/`):

    reads per turn                      1.44        (1.00 = no retries)
    turns needing no retry              379 (74%)
    FIRST read of a turn                median 11.96 s after the play
    the read that WORKS on a retry      median 17.59 s after the play

Nothing differs between those two except that the deal finished in between. **A quarter of
all turns were spending a paid API call to wait**, which is why the retry rate sat at
1.24-1.52 across every run of the day regardless of what was patched -- none of it touched
the moment.

**A FIXED SLEEP CANNOT FIX IT.** Filmed after the play, the deal STARTS at +1.5 s on one
turn, +5.5 s on another, +6.5 s on a third. What is constant is the SHAPE: a frame-to-frame
delta spike of 30-43 as the cards fly in, then quiet, then readable within half a second.

**AND "WAIT FOR QUIET" IS THE WRONG INSTRUMENT, MEASURED.** A SETTLED HAND reads a delta of
~4.6; an EMPTY TABLE reads ~2.5. The empty table is QUIETER than the hand, so quiet cannot
tell "the cards have landed" from "there are no cards" -- which is the exact mistake being
fixed -- and no threshold on that quantity separates them (10.4). The first version of that
measurement came out with the two populations the wrong way round because "moving" was
mostly the empty table BEFORE the deal, and a constant was nearly shipped off it.

So the gate asks the question that is actually wanted: `local_hand_cards()` returns a hand
only when every card reads, twice running. ~21 ms against a 150 ms poll, and NO constant is
invented anywhere in the rule.

---

**26. A READER THAT LOOKS STABLE ON A STILL PICTURE MAY NOT BE. FILM IT.** The single
cheapest diagnostic found this year. A hand that was NOT MOVING was filmed for 28
consecutive frames: one card read 7 / unread / 7 / unread with the score swinging 0.57 to
0.91. The picture was identical to the eye; the fitted circle alternated between r=19 and
r=20, and `read_digit` resamples to a fixed 24x24, so one pixel of radius rescales the
digit inside the tile. Searching the radius recovered 16 of 24 unread cards over 1,181
real captures, all 16 agreeing with the paid model, and changed 0 of 1,157 answers that
already read.

**A SINGLE FRAME CANNOT SHOW YOU THIS.** Accuracy measured on one frame per hand reports a
coin flip as a property of the frame.

---

**27. THE PAID MODEL'S REPLACEMENT MUST BE MEASURED ON THE MONEY FIELD, NOT ON ACCURACY.**
2026-09-09, a local VLM on Snoopy (Ollama, RTX 3080). On 29 frames hand-labelled off a
contact sheet -- ambiguous frames EXCLUDED rather than guessed, and the count excluded
reported:

    qwen2.5vl:7b, loose prompt    69%   6 frames falsely called match_start_prompt
    qwen2.5vl:7b, strict prompt   79%   1 frame  falsely called match_start_prompt
    qwen3-vl:8b,  strict prompt  100%   0        (5.6 s/frame against 0.2)

`screen == "match_start_prompt"` is the branch that does `balance -= 50`. CLAUDE.md already
records a ROUND 1 overlay read as match_start_prompt, one guard from a second $50
(2026-08-25) -- and qwen2.5vl reproduced that exact failure six times in 29 frames. So the
number that decides a screen reader is its FALSE POSITIVE RATE ON THE MONEY SCREEN, and it
is measured the way `at_table()` is: over every frame on disk, where one false positive
anywhere is a veto. A 29-frame result is enough to DISQUALIFY and never enough to CERTIFY;
the 500-frame sample that said 0 and fired on the 701st is the precedent.

**AND IT IS A LABELLING AID, NOT PART OF THE LADDER.** The user's call the same evening,
after the sweep came back clean: *"for the record, Snoopy was used to help speed you up in
labeling. I wouldn't wire it up in the ladder."* Snoopy is a SECOND MACHINE for offline
work -- labelling corpora, adjudicating frames, running sweeps that would otherwise
saturate this Mac (10.13). It is NOT a runtime dependency of the live loop, and nothing on
the $50 path may come to depend on a model being up on another box. A clean 422-frame
sweep is a reason to trust it for LABELLING, not a reason to wire it into `read_game_state`
-- and `result` still has no local detector, which stays an open gap rather than being
quietly filled by a network call to another computer.


**28. A CARD CAN BE UNREADABLE FROM EVERY FRAME, AND NO INPUT UNCOVERS IT. THE HAND MUST
SURVIVE THAT.** 2026-09-09, live on the console, at the user's prompting.

A hand sat with slot 1's power disc hidden under its neighbour in the fan. Everything was
tried, on the live console, one press at a time:

    move the cursor RIGHT one slot      disc still hidden
    move the cursor ONTO the card       the card RISES above its neighbours -- still hidden

    **CORRECTION 2026-09-20: HOVER DOES NOT LIFT A CARD.** Measured over 277 five-row
    fans (`agent_progress/cursor-lift-refutation/measure_lift_vs_glow.py`): rise vs the
    slot anchor is p50 7.0 hovered and 7.0 not at slot 3, -10.0 either way at slot 4.
    The "rises" above was a live eyeball reading. SELECTION lifts a card (~44 px,
    `SELECTED_MIN_RISE` 25); hovering does not, so a cursor reader built on hover
    lift is dead and the probe-select in `_walk_cursor_to` (ISSUES.md I-02) uses the
    selection lift instead.
    SELECT the card (cross)             "kind unknown" -> "player, power unread"; still no digit
    four local re-grabs, 0.25 s apart   0 of 15 recovered

The occlusion is STABLE, not an animation, so re-grabbing the same scene four times gets
the same answer four times. That was a fix I shipped without thinking the mechanism
through, and the frames it added are what disproved it the same hour.

**IT IS NOT ONE BAD CARD.** The user's hypothesis, and worth testing because it would have
been a cheap fix. Within one match it looks true -- 15 of 15 refusals were the same card at
slot 1. Across the corpus it is false: 10 refusals spanning 08:17 to 13:34 and many matches
fall at FOUR different slots (1 x5, 2 x2, 4 x2, 3 x1) on visibly different cards, one of
them a named "PEPAN BLACK". So it is an OCCLUSION that can happen to any card, and once it
happens it persists for the whole hand.

**WHAT THAT MEANS FOR THE DESIGN.** ALL-OR-NOTHING WAS TOO STRICT. A hand with four cards
read and one genuinely invisible is still playable -- you simply do not play the invisible
one -- and rejecting the whole hand instead turns an unreadable CARD into an unreadable
STATE, which then costs a paid call per turn. Measured: that mistake took the loop from
1.44 read_game_state calls per turn to 5.00, and then to 8.67.

**AND A WARNING ABOUT PRESSING BUTTONS TO INVESTIGATE.** The sequence above ended with a
"Give up?" dialog on screen, one CROSS away from forfeiting a paid match. Circle answered
NO and the match survived. Investigating a live match with real presses is worth doing --
it is what settled this -- but every press is a real move, and the escape from a wrong one
has to be known BEFORE it is made (section 4: NO = circle, YES = cross).


**29. AN INVESTIGATION THAT LEAVES STATE BEHIND POISONS THE NEXT EXPERIMENT, AND THE
RESULT STILL LOOKS LIKE A FINDING.** 2026-09-09, live, caught by the user watching the
stream.

Probing why a card could not be read, I pressed `select_card` on it. `close_result`
afterwards did NOT deselect -- it opened the "Give up?" dialog, which was answered NO --
so the card stayed SELECTED. Several minutes later `select_and_play(2)` ran to test whether
playing the neighbour would uncover it. `confirm_play` played the card that was ALREADY
committed: the hidden card itself, not its neighbour.

**THE RESULT READ PERFECTLY AS A SUCCESS.** Slot 1 went from unreadable to "5" and the hand
came back COMPLETE, which is exactly what the experiment predicted. It was reported as
"your test worked, the hidden card is a 5". It was a NEW card in that slot.

**THE EVIDENCE WAS IN MY OWN OUTPUT.** Before `[tactics, ?, 4, 4, 5]`, after
`[tactics, 5, 4, 4, 5]` -- slots 2, 3 and 4 UNCHANGED, so the neighbour was never
replaced. One glance at the row I had already printed says which card was played.

**AND IT NEARLY BECAME A SECOND WRONG DIAGNOSIS.** The next step drafted was a cursor-map
sweep to hunt an off-by-one in `select_and_play`, a function whose docstring carries a
Fisher p = 0.0048 for the homing fix it already has. There was no off-by-one. The user
stopped it.

**THE RULES THIS EARNS.** Before any experiment on a live match, ASSERT THE STARTING STATE
rather than assume it -- nothing selected, no dialog up. After any probe that presses a
button, RESTORE what it changed and verify the restore landed; `close_result` is not a
deselect. And when an experiment confirms its own prediction, check the control -- here,
the three slots that should have been untouched.



---


## Five more guards that could not fire, and one that wrote to the rig (2026-09-06)

All five found by re-verifying claims rather than by a failure. Same shape every
time: something reported clean while the thing it guarded was broken.

**THE OFFLINE SUITE WAS WRITING THE RIG'S CALIBRATION FILES.**
`compass_scale.json` and `view_bounds.json` are read back by LIVE runs — the
scale cache sets degrees-per-pixel on the compass strip, the view cache moves the
view centre and hence every bearing — and both were written unconditionally.
`./run_tests.sh` added a key derived from DEMO ARCHIVE frames at 1400x787, a
geometry no live capture produces, to the file the rig uses. Nothing errored;
nothing ever does when a cache is quietly wrong. Only the WRITE is now suppressed
under `BASEBALL_TEST_RUN` — the in-memory cache fills exactly as it would live,
so tests exercise the same path with the same values. Pinned by
`tests/harness/test_caches_not_written_in_tests.py`, which also refuses a
demo-archive geometry key found in either real file, catching the pollution even
if it arrives by another route. §11's OPEN-6 audit named this hazard and nothing
had closed it.

**THE OPEN-16 C++ CHECK WENT VACUOUS IF A CONSTANT CHANGED.**
`tests/cpp/test_injectinput.cpp` mirrors the injector's `RELEASE_MS` as a local
100, with a comment claiming the duplicate was safe because it "only ever chooses
between PASS and INCONCLUSIVE". False: it also set the pump horizon, so a real
`RELEASE_MS` above 250 stopped the loop BEFORE the real deadline. Demonstrated —
with the OPEN-16 fix DELETED and `RELEASE_MS` raised to 300, the file reported
`pass=21 fail=0` and "all green". The mirror is now a FLOOR; the check takes the
larger of it and the window this process actually MEASURED a moment earlier, so
load lengthens both together and waiting longer only makes the bug more certain
to fire. Same mutation now gives `pass=20 fail=1`.

*If you mutate `injectinput.cpp`: `g_inject.release_until = 0;` appears TWICE.
Line 193 is the fix; line 325 is the release path. A count-blind replace mutates
both and measures nothing (§10.10).*

**THE PATCH DIVERGENCE LIST WAS GUARDED BY COUNT, NOT COVERAGE.** See the OPEN-11
entry — replacing a row rather than deleting it kept the count at five and left a
patched file compared against nothing.

**HARNESS CLEANUPS RESTORED STALE DEFAULTS.** Every A/B flips a `graph_walk` flag
and restores it in a `finally`, and every one restored a LITERAL — what the
default was on the day that script was written. Two had already rotted:
`ab_leg_speed` restored `LEG_SPEED_BY_LEG = {}` after leg 1 shipped an override,
and `ab_stall` restored `STALL_CHANGE = 2.5` after it became 6.0. In-process
only, so nothing on disk was damaged — but a cleanup that reinstates a stale
default looks like tidiness and installs an arm. All four now capture the flag at
import. `tests/harness/test_harness_restores_shipped_value.py` enforces it, and
exempts subprocess harnesses for a reason worth keeping: they set the arm inside
the `run_trial` child, which then exits, so process death IS the restore and it
cannot be written wrong. That is a second reason to prefer that pattern.

**`profile_trial.py` MEASURED THE WRONG THING THREE WAYS.** It wrapped
`walk_steps.walk_forward`/`turn_to`, which a LEG NEVER CALLS (legs go through
`slow_traverse`); it profiled `reset` plus two legs rather than the §8(a) route;
and it summed NESTED timers, so its "65% unaccounted" was an artefact of the
arithmetic. It now profiles the route through `follow_verified` and records
INCLUSIVE and EXCLUSIVE seconds, so the exclusive column sums to elapsed time and
the residual is real. **Read the exclusive column.** Pinned offline against a
synthetic call tree by `tests/harness/test_profile_exclusive_time.py`.

**A NOTE ON WHERE THE STAIRS POSE LIVES.** `STAIRS_APPROACH.md` holds the
hand-measured doorway approach — bearing, pitch, and three pitch constants that
contradict each other — derived live with the user watching the stream. Nothing
in this file referenced it, which is how a measured document becomes invisible.
Read it before touching leg 2 or anything about pitch.

---
