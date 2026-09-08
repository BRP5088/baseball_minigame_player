# The chiaki-ng patch — analog + button injection

## Read this first

**The authoritative copy of the patch is `git diff` in `chiaki-ng-src/`.**

    cd chiaki-ng-src && git diff

That is a real checkout of upstream with our edits on top, so the diff is
always current and always complete. This directory is a convenience copy and
has been wrong before — until 2026-09-04 its README said the patch was "the two
edits in streamsession.cpp" and told you to "apply only these". **Following
that produces a binary that compiles, links, launches, prints nothing unusual,
and never delivers a single input.**

## The patch is FIVE edits across THREE files, plus two new files

Two of the five fail SILENTLY, and they are the two that were missing:

| # | file | edit | fails how |
|---|---|---|---|
| 1 | `gui/src/streamsession.cpp` | `#include "injectinput.h"` | compile error — loud |
| 2 | `gui/src/streamsession.cpp` | the 8ms `inject_pump_timer` in the constructor | input applied but never pumped |
| 3 | `gui/src/streamsession.cpp` | `InjectInputApply(&state)` in `SendFeedbackState()` — **not** its twin `DpadSendFeedbackState` | nothing is ever applied |
| 4 | `gui/CMakeLists.txt` | add `src/injectinput.cpp` to `SOURCE_FILES` | **SILENT** — sources are LISTED, not globbed, so the file is simply never compiled |
| 5 | `gui/src/main.cpp` | call `InjectInputStart()` | **SILENT** — the FIFO listener never starts, every symbol still links, the build looks fine |

Plus the two new files that edit 4 compiles in:

    injectinput.cpp   injectinput.h    ->  chiaki-ng-src/gui/src/

## The SECOND patch: the frame dump (2026-09-08)

Same shape, three more edits, and one of them is the same silent one.

chiaki writes its DECODED frames into a memory-mapped file, and the Python side
reads that instead of grabbing chiaki's window off the screen. The screen path
depends on the window being composited on the CURRENT macOS Space —
`input_controller.game_window_rect()` lists ON-SCREEN windows only, and
`CGWindowListCreateImage` returns nothing for a window on an inactive Space —
so switching Spaces killed six walks between 10:30 and 11:05 that morning.

| # | file | edit | fails how |
|---|---|---|---|
| 6 | `gui/CMakeLists.txt` | add `src/framedump.cpp` to `SOURCE_FILES` | **SILENT** — same reason as edit 4 |
| 7 | `gui/src/main.cpp` | `#include "framedump.h"` + `FrameDumpStart()` beside `InjectInputStart()` | **SILENT** — no mapping is ever opened |
| 8 | `gui/src/qmlbackend.cpp` | `FrameDumpPush(frame.frame)` right after `chiaki_ffmpeg_decoder_pull_frame` | nothing is ever dumped |

Plus the two new files:

    framedump.cpp   framedump.h   ->  chiaki-ng-src/gui/src/

**Edit 8 is in `qmlbackend.cpp` and NOT in `streamsession.cpp`, deliberately.**
`streamsession.cpp`'s `FfmpegFrameCb` only emits a Qt signal; it never holds an
`AVFrame`. The lambda at `gui/src/qmlbackend.cpp:1107` is the ONLY caller of
`chiaki_ffmpeg_decoder_pull_frame`, and that function CONSUMES frames from the
codec (`avcodec_receive_frame`), so pulling a second time anywhere else would
take frames AWAY from the renderer rather than copy them. The push sits BEFORE
`prepareFrameForPresentation` so the dump does its own hardware transfer into
its own frame and the render path is bit-identical with the dump on or off.

**It is OPT-IN, like the injector.** Unset `CHIAKI_FRAME_DUMP` and
`FrameDumpStart()` returns at once, the mapping is null, and `FrameDumpPush()`
is one load and a return. `restart_chiaki.sh` exports it beside
`CHIAKI_INJECT_INPUT` and greps the launch log for `frame dump`.

The file format — a 4096-byte header, one packed NV12/I420 slot, and a
two-counter seqlock for tearing — is documented at the top of `framedump.h`,
which is the authority; `frame_dump.py` parses exactly that layout and the
struct offsets are `static_assert`ed on the C++ side.

## What is in this directory

    injectinput.cpp        the new source
    injectinput.h          its header
    framedump.cpp          the frame dump's source
    framedump.h            its header AND the file-format spec
    streamsession.cpp      full patched copy (edits 1-3)
    gui/CMakeLists.txt     full patched copy (edits 4 and 6)
    gui/src/main.cpp       full patched copy (edits 5 and 7)
    gui/src/qmlbackend.cpp full patched copy (edit 8)

`gui/CMakeLists.txt` and `gui/src/main.cpp` were added on 2026-09-04. Before
that they existed **only as prose in CLAUDE.md**, which is why this README could
claim the patch was two edits and nobody noticed.

**All five are now compared byte for byte against `chiaki-ng-src/` by
`tests/cpp/test_injectinput_cpp.py`**, which the offline suite runs. This README
is prose and cannot fail; that test can. If a sixth file joins the patch, add it
to `PATCH_FILES` there as well as to the table above — the check refuses to run
against a trimmed list, so a missing row fails loudly rather than quietly
guarding less.

## How the omission was found

`nm -U <binary> | grep -i inject` on the shipped app showed the symbol was
present, which meant something had called `InjectInputStart()` — so the call had
to exist somewhere that had never been saved back. That is the check to run if
input ever stops reaching the console after a rebuild.

## Building

The recipe, the brew dependencies and the cmake line are in CLAUDE.md §1. Note
`chiaki-ng-src/build/` **does exist** (this README used to claim there was no
working build directory and that a rebuild needed a fresh checkout — both
false), and `restart_chiaki.sh` installs from it.

## The FIFO protocol

`/tmp/chiaki_input`, one field per newline-terminated line:

    left_x  <int16>              set an axis
    right_x <int16> <hold_ms>    set it and release after hold_ms
    buttons <bitmask>            SEE THE WARNING BELOW
    clear                        release everything

The optional third field is a hold in milliseconds; chiaki releases it on its
own `steady_clock`, so the release does not depend on the writing process waking
up. Under `MAX_TIMED_HOLD` (4.5s, below `INJECT_TIMEOUT_MS` 5000) a hold needs no
chunking.

**An untimed write must not cancel a sibling axis's deadline.** `right_x 32767
400` followed by `right_y 0` — the natural way to set a stick — had the untimed
second line clear the deadline set by the first, so a 1.0s command turned for
~1.4s and it looked like drift.

## THE BUTTON BITS DO NOT WORK ON THIS CONSOLE

Measured 2026-09-03: `buttons 4096` (options) produced nothing after 4 seconds,
while the keyboard path opened the pause menu in 0.5s. The bit values were never
confirmed — this README said so, and CLAUDE.md wrongly said they were "measured
empirically" until it was corrected.

`input_controller.INJECT_BUTTONS = False`. **Buttons go through the keyboard;
STICKS stay on the FIFO**, where every walk the router makes proves them.

The failure was not the wrong bits. It was that `_inject_press` returned True
because the WRITE succeeded, so `press()` believed the button had been pressed
and never fell through to the path that works — silently disabling every button
in the system. If you re-enable this, verify against the pause menu: press
options, look for the book. It is a free and harmless target.
