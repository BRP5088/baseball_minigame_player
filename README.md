# Auto Baseball

Automates the "Baseball Cards" minigame in *Mouse: P.I. for Hire*. The game
runs on a PS5 and is streamed to a Mac through a patched build of chiaki-ng;
this project reads the stream, decides what to play, and sends the input back
over that same patched client. Current record: **163W 20L 19D**.

## How it works

- **Navigation.** A closed-loop walker gets the character to the dealer's
  table, checking its position from the screen after every push rather than
  from the stick. It reached 40 arrivals out of 40 trials with a median time
  of 76 seconds.
- **Reading the screen.** Local, non-paid readers cover the hand, the ban
  screen, the card reveal, and the result banner. Money is only readable on
  the pause menu.
- **Playing.** A card engine chooses each play from what the readers report.
  A match costs $50 in-game.
- **Input.** Button presses go to the keyboard. Analog stick movement is
  written to a FIFO that the patched chiaki-ng client reads and applies to
  the PS5 session.

## Requirements

- A PS5 running the minigame, and a Mac to stream it to.
- The **patched** chiaki-ng build in `chiaki-ng-build/`, started with
  `./restart_chiaki.sh`. The patch (source in `chiaki-patch/`) adds input
  injection and a frame dump on top of upstream chiaki-ng; the stock
  `/Applications/chiaki-ng.app` does not accept injected input at all.
- Python 3.14 in a local `.venv`, with packages pinned in `requirements.txt`
  (Pillow, numpy, opencv-python, scipy, mss, pytesseract, pyautogui,
  pygetwindow, pyobjc-framework-Quartz, anthropic, tesserocr).
- A second, separate Python 3.11 virtualenv, `paddle_venv/`, which the result
  banner reader (`result_ocr.py`) spawns as a subprocess to read WINNER /
  LOSER / DRAW at the end of a match. It is not the project's main
  interpreter and must not be selected as one.
- `tesserocr` is a real, in-process OCR dependency (not optional); it needs
  no local compiler, since pip installs a prebuilt wheel.

## Setup

```
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # fill in PERSONAL_ANTHROPIC_API_KEY
```

`.env` is gitignored and machine-local.

Build and run the patched chiaki-ng client per `chiaki-patch/README.md`. In
short: clone `chiaki-ng` upstream, apply the patch (five edits across three
files plus two new source files — `injectinput.cpp`/`.h`, and
`framedump.cpp`/`.h` for the frame-dump variant), build with CMake/Ninja
against the brew dependencies it lists, then use `./restart_chiaki.sh` to
stop any running copy, install the freshly built binary, re-sign it, and
relaunch it with injection enabled. The chiaki-ng-src `git diff` itself is
the authoritative copy of the patch; `chiaki-patch/` is a convenience copy of
the same edits.

## Running

`tools/doctor.py` is the read-only health check — it captures the current
game frame and reports capture geometry, compass bearing, table proximity,
and location, without pressing anything:

```
.venv/bin/python -B tools/doctor.py
```

`orchestrator.py` holds the match engine; its `run(target_wins=...)` function
is the entry point for playing matches (its `__main__` block calls
`run(target_wins=17)` by default). `run_cycles.py` wraps that for unattended
play: it reloads the last save, walks to the table, and plays matches until
the in-game balance runs out, repeating for a given number of cycles:

```
.venv/bin/python -B run_cycles.py [cycles]
```

Both write to a progress file that tracks wins/losses/draws and the running
balance; a live run should pass `progress_file="progress_testing.json"`
explicitly rather than use the default, to avoid mixing records. Starting a
live run means real input reaches a real PS5 session — see RIG.md before
doing so.

## Tests

```
PATH="$PWD/.venv/bin:$PATH" ./run_tests.sh
```

This runs every `tests/<area>/test_*.py` file, recursively, each as its own
`python3` process (no test framework) under a per-file timeout. It sets
`BASEBALL_TEST_RUN=1` for every child process, which holds every input path
off — nothing it runs presses a key or writes to the FIFO. Anything that
spawns test files of its own must pass that variable down, or it will send
real input.

Most tests read fixtures from `test_fixtures/`, which is checked in. About a
dozen files also need local data that is gitignored and so is not in this
repo: `demos/` recordings, `screenshot_log/` frames, `overnight/` run logs,
the `chiaki-ng-src/` checkout, and a compiled C++ test binary. In a fresh
clone those files fail; the rest of the suite does not depend on them.

A `.githooks/pre-commit` hook runs a fast subset of the suite (a handful of
tests chosen because each one guards something that actually broke a live
run before); the full suite above is the real gate.

## Project docs

This README covers setup and running. Everything else — every measurement,
correction and incident behind the rules above — lives in topic files at the
repo root, split out of `CLAUDE.md` once it grew past a size that made sense
to load into every session:

| Topic | File |
| --- | --- |
| The rig: PS5, chiaki-ng, the stream, the test environment | `RIG.md` |
| Screen readers: hand, ban screen, reveal, balance | `READERS.md` |
| Game rules and money | `RULES.md`, `GAME.md` |
| Input paths, the FIFO, the keymap | `INPUT.md` |
| Navigation, the closed-loop walker | `NAVIGATION.md` |
| Navigation and rig changes that were tried and did not help | `GRAVEYARD.md` |
| How experiments, A/Bs, and mutation testing are run here | `METHODOLOGY.md` |
| Open tickets | `OPEN.md` |
| Closed tickets | `CLOSED.md` |

`CLAUDE.md` itself is the always-loaded core and the index into these files;
read it first if you're picking this project up.

## Safety

This project sends real keyboard and analog input to a real PS5 session
through the patched chiaki-ng client — there is no simulator or dry-run mode
for the live path. Only the patched build in `chiaki-ng-build/` (started via
`./restart_chiaki.sh`) accepts injected input; the stock
`/Applications/chiaki-ng.app` silently accepts none of it. Never copy a new
binary over a running chiaki process — macOS invalidates its code signature
and kills it. If you need to put the console into rest mode by hand, follow
the documented procedure exactly: the PS5 overlay drops presses, and in its
power menu "Turn Off PS5" sits directly beneath "Enter Rest Mode."
