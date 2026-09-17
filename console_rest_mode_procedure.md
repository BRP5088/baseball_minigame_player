# Putting the PS5 into rest mode, and waking it again

Walked end to end on 2026-09-17 with a paid match on screen. Everything below is
measured on this rig, not recalled. `CLAUDE.md` section 1 carries the short
version; this file is the one to open while actually doing it.

**The whole procedure is STEP AND LOOK. There is deliberately no one-shot
script**, and the reason is measured: the console ignores a large share of
presses (section 5: 15.20% over n=1000, and they CLUSTER). Tonight, on this
overlay, **10 right presses moved 6 icons, the next 4 moved 2, and the first X on
the Power icon was dropped outright.** A blind sequence lands three icons away
from where it thinks it is, and one of the wrong places powers the console off.

---

## 0. CHECK WHETHER IT IS ALREADY ASLEEP. IT USUALLY IS.

No input required, nothing moves:

```bash
.venv/bin/python -B -c "
import game_capture, ensure_stream
img = game_capture.grab()
print('capture size :', img.size)
print('looks_like_ui:', ensure_stream.looks_like_ui(img))
print('streaming()  :', ensure_stream.streaming())
"
```

    ASLEEP        size is NOT 1920x1080 (it is the chiaki window, e.g. 1867x1050)
                  looks_like_ui  True
                  streaming()    False

    AWAKE         size IS 1920x1080
                  looks_like_ui  False
                  streaming()    True

The window size is the fastest of the three: a capture that is not the PS5's
1920x1080 means you are looking at chiaki, not at the game.

**IF IT IS ALREADY ASLEEP, DO NOTHING.** The user's call, 2026-09-13: *"maybe
its already asleep. if so, leave it alone."* And do NOT press `ps_button` to find
out -- with no session running that press raises chiaki's own "Quit" dialog, one
keystroke from killing the app. Escape dismisses it (Qt treats Escape as reject);
never Enter or Space, because Yes is the left button.

---

## 1. Open the Control Center

```bash
.venv/bin/python -B -c "
import time, game_capture, input_controller as ic
ic.press('ps_button'); time.sleep(2.5)
game_capture.grab().save('/tmp/cc.png')
"
```

`ps_button` is a **TOGGLE**. Press it ONCE and then poll -- a retry loop that
presses on every poll closes the menu and reopens it forever.

**Focus opens on a CARD TILE, not on the icon bar.** The big tile is highlighted
and shows a hint under it (`▢ Resume Game`). This is the step that is easy to
miss, and missing it is what makes the next ten presses do nothing useful.

---

## 2. Drop to the icon bar -- ONE press

```bash
.venv/bin/python -B -c "
import time, game_capture, input_controller as ic
ic.press('dpad_down'); time.sleep(2.0)
game_capture.grab().save('/tmp/cc.png')
"
```

Confirm by **reading the label above the bar**. When focus is on the bar, the
focused icon sits in a white circle AND its name appears above the strip --
`Home` on arrival. `Customize` also appears at the far right of the bar. If no
label is visible, focus is still in the tiles: press `dpad_down` again.

---

## 3. Walk right to `Power`, reading the label after every batch

The bar is **11 icons**, and Power is the last:

    home · the game · notifications · friends · music · downloads · sound ·
    mic · accessories · profile · POWER

From `Home` that is **10 moves**. Send a batch, then LOOK:

```bash
.venv/bin/python -B -c "
import time, game_capture, input_controller as ic
for i in range(10):
    ic.press('dpad_right'); time.sleep(0.9)
time.sleep(2.0)
game_capture.grab().save('/tmp/cc.png')
"
```

Then read the label and send however many more are needed. Tonight that took
three batches: `Home` -> `Sound` -> `Accessories` -> `Power`.

**NEVER dead-reckon the position from the number of presses sent.** See the drop
figures at the top of this file. The label is the only thing that answers "where
am I".

**AND DO NOT CROP TIGHT TO THE ICONS.** Two 2x zoomed crops of the icon strip,
one with focus on the bar and one without, were **indistinguishable** here -- the
focus ring does not survive the stream's compression at that scale. The LABEL is
the readable signal and it sits ABOVE the strip, so a crop tight to the icons
throws away the only usable evidence. Look at the whole lower third of the frame.

---

## 4. Open the Power menu, then take `Enter Rest Mode`

```bash
.venv/bin/python -B -c "
import time, game_capture, input_controller as ic
ic.press('cross'); time.sleep(3.0)
game_capture.grab().save('/tmp/cc.png')
"
```

**LOOK BEFORE THE SECOND X.** The menu is three rows:

    Enter Rest Mode      <- PRE-SELECTED, top. "suspend your games"
    Turn Off PS5         <- directly underneath
    Restart PS5

If the first X was dropped the menu will not have opened at all, which is what
happened tonight. Send another X -- Power is still highlighted, so it is safe.
Once the menu IS open and `Enter Rest Mode` is the highlighted row, one more X
takes it.

**This is the single most dangerous moment in the procedure.** X is SUBMIT and
takes whatever the cursor sits on. A blind double-X after a dropped press puts
the cursor one row low, on **Turn Off PS5**, with $50 on the table. The other
hazard is earlier: from a fresh Control Center an X can reach the **PS5 HOME
SCREEN**, out of the match.

---

## 5. Confirm with the three tells, not with the absence of an error

Re-run the block from step 0. All three must agree:

    game_capture.grab()             (1867, 1050)   <- the chiaki WINDOW
    ensure_stream.looks_like_ui()   True
    ensure_stream.streaming()       False

---

## Waking it again

`ensure_stream.ensure_live()` wakes a sleeping console; measured at **8 s** on
2026-09-13.

**`ensure_live()` returning True means the STREAM is up, NOT that the game will
take input.** After a wake, the PS5 overlay can still be on top of the game, and
presses fired into that gap reach chiaki, reach the console, and change nothing.
Do not press until a reader that only answers ON THE SCREEN YOU WANT says yes:

    a ban screen     orchestrator.read_ban_counter(img) is not None
    a turn screen    local_hand.read_hand(...) returns its rows
    the dealer       table_prompt.at_table(img)

---

## Rest mode and an open match

The menu entry says it itself: rest mode **suspends your games**. An open match
survives, and `match_in_progress` stays set -- correctly, because the match
really is still in progress. Section 2's rule holds: that flag is often NOT
stale, so check the screen before clearing it.

---

## THE CHIAKI-SIDE SLEEP PATH IS UNREACHABLE ON macOS. DO NOT RETRY IT.

chiaki can sleep the console, and on another platform this would be the better
route because it avoids the overlay entirely. On this Mac nothing can reach it.
Recorded so the next session does not spend the time again.

The chain is real, and reading it is what makes the dead end certain:

    QEvent::Close on the main window    qmlmainwindow.cpp:7487 -> backend->closeRequested()
    DisconnectAction::Ask (the DEFAULT) qmlbackend.cpp:1275 -> emit sessionStopDialogRequested()
                                        returns FALSE, so the window does NOT close
    the popup                           StreamView.qml:1257 opens sessionStopDialog
                                        (or separateSessionStopWindow -- identical)
    focus                               onVisibleChanged -> view.grabInput(sleepButton)
    RETURN                              Keys.onReturnPressed -> closeAction = 1
                                        -> Chiaki.stopSession(true) -> GoToBed() + Stop()
    ESCAPE                              closeAction stays 0 -- a harmless abort

**But the only keyboard route in is compiled out.** `qmlmainwindow.cpp:7412`:

    case Qt::Key_Q:
    #ifndef Q_OS_MACOS
        close();
    #endif
        return true;          // swallowed on macOS, does nothing

Qt maps its `ControlModifier` to COMMAND on macOS, so chiaki's own Cmd+Q is that
`#ifndef` and is a no-op. **Cmd+W is not bound at all** -- sent live at the
frontmost chiaki with a match on screen: no dialog, window still open, the scene
identical before and after. And the window is FULLSCREEN with **zero AX
buttons**, so there is no close control to press either. Setting
`DisconnectAction` to `AlwaysSleep` changes nothing, because nothing can end the
session to trigger it.

**The user's call on that attempt, 2026-09-17: *"Don't do cmd+w. That's dumb and
dangerous."*** Correct, and the reason generalises past this one key: the
dialog's whole safety argument is that Sleep is focused and Escape aborts -- but
that only holds IF THE DIALOG OPENS. If the keystroke turns out to be bound to a
plain window close instead, the same press quits chiaki mid-match. **Do not probe
an application's keymap by pressing keys at it while a paid match is live.**

---

## Two instrument traps found while checking all this

Both made a verification look like it had verified something, which is
`CLAUDE.md` 10.1's whole family.

    chiaki runs on the SECOND display    the LG ULTRAWIDE, window at (-2560, 0),
                                         2560x1080, while the Mac's built-in is
                                         3456x2234
    screencapture -x one.png             captures the BUILT-IN display only. The
                                         "before" shot of chiaki was a picture of
                                         the Claude app, and was briefly accepted
                                         as evidence. Use
                                         `screencapture -x a.png b.png` -- one
                                         path per display, in order
    frontmost_app() == "chiaki"          says which APP has focus. It says nothing
                                         about which MONITOR that app is on, so it
                                         cannot corroborate a screenshot

The user spotted the first one instantly (*"Wrong monitor"*).

**For anything inside the stream, prefer `game_capture.grab()` over
`screencapture`** -- it targets the chiaki window directly, the PS5 overlay
renders into the stream so it is captured too, and it cannot photograph the wrong
display.
