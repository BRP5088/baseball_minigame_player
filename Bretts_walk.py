"""Brett's driver — one entry point, one subcommand per thing you want to do.

    python3 Bretts_walk.py where          # report position, MOVES NOTHING
    python3 Bretts_walk.py doctor         # is everything actually up?
    python3 Bretts_walk.py connect        # bring chiaki + the stream up
    python3 Bretts_walk.py reset          # reload the save -> stand at the spawn
    python3 Bretts_walk.py walk           # spawn -> the minigame table
    python3 Bretts_walk.py last-mile      # just Wanda -> corner -> jukebox -> table
    python3 Bretts_walk.py last-mile --durations 2.0 3.3 4.1

Each of these is a debug profile in .vscode/launch.json, so Cursor's Run and
Debug panel drives them directly and you can breakpoint into the real code.

WHY SUBCOMMANDS AND NOT SEPARATE SCRIPTS
----------------------------------------
There are already 97 modules at the root and about a fifth of them are dead
one-off scripts. Another script per task is how that happened. One file with
subcommands keeps the launch profiles to a single program and an argument.

EVERY COMMAND CHECKS THE PICTURE FIRST. On 2026-09-02 chiaki was not running,
capture silently returned the CLAUDE DESKTOP WINDOW instead, and a whole setup
pass was spent reading a screenshot of a chat window as if it were the game.
compass.fast_capture() now raises NoGameWindow, and `doctor` exists so you can
see that state in one command instead of inferring it.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SPAWN = "office_corridor"
GOAL = "dealer_table"


# --- helpers --------------------------------------------------------------

def _live(log=print):
    """True once there is a game window with a picture that is updating."""
    import ensure_stream
    return ensure_stream.ensure_live(log=log)


def _snapshot(log=print):
    """Everything worth knowing about the current frame. Moves nothing."""
    import compass
    import places
    import table_prompt as tp
    import worldmap
    import graph_walk

    try:
        img = compass.fast_capture()
    except compass.NoGameWindow as e:
        log(f"  NO GAME WINDOW: {e}")
        return None

    w, h = img.size
    aspect = w / h
    log(f"  capture   {w}x{h}  aspect {aspect:.3f}"
        f"{'' if abs(aspect - 16 / 9) < 0.01 else '   <- NOT 16:9, the crop is wrong'}")
    log(f"  bearing   {compass.read_bearing(img)}")
    log(f"  at_table  {tp.at_table(img)}   (ink {tp.ink(img):.4f})")
    log(f"  identify  {places.identify(img)}")
    try:
        m = worldmap.WorldMap.load()
        log(f"  locate    {graph_walk.locate(m, img=img, log=lambda *a: None)}")
    except Exception as e:
        log(f"  locate    unavailable ({type(e).__name__}: {e})")
    return img


# --- commands -------------------------------------------------------------

def cmd_where(args):
    """Report position. Deliberately moves nothing — safe to run any time."""
    return 0 if _snapshot() is not None else 1


def cmd_doctor(args):
    """Is the whole chain actually up? Each line is a thing that has broken."""
    import subprocess

    ok = True
    chiaki = subprocess.run(["pgrep", "-x", "chiaki"], capture_output=True).returncode == 0
    print(f"  chiaki running     {chiaki}")
    ok &= chiaki

    fifo = os.path.exists(os.environ.get("CHIAKI_INJECT_INPUT", "/tmp/chiaki_input"))
    print(f"  inject FIFO        {fifo}"
          f"{'' if fifo else '   <- input will fall back to the keyboard path'}")

    import ensure_stream
    try:
        streaming = ensure_stream.streaming()
    except Exception as e:
        streaming = f"error: {type(e).__name__}"
    print(f"  streaming          {streaming}")

    try:
        frozen = ensure_stream.is_frozen()
        print(f"  picture frozen     {frozen}"
              f"{'   <- decoder stalled; connect will restart it' if frozen else ''}")
        ok &= not frozen
    except Exception as e:
        print(f"  picture frozen     unknown ({type(e).__name__})")

    print("  --- current frame ---")
    ok &= _snapshot() is not None

    import kill_runaways
    stray = kill_runaways.find()
    print(f"  runaway processes  {len(stray)}"
          f"{'   <- run: python3 kill_runaways.py --kill' if stray else ''}")
    return 0 if ok else 1


def cmd_connect(args):
    """Bring chiaki and the stream up, restarting whatever is wedged."""
    return 0 if _live() else 1


def cmd_reset(args):
    """Reload the last save and end up standing at the spawn point."""
    import reset_env

    if not _live():
        return 2
    for attempt in range(args.attempts):
        try:
            bearing = reset_env.reset_environment(log=print)
            print(f"  at the spawn, bearing {bearing}")
            _snapshot()
            return 0
        except Exception as e:
            print(f"  reset attempt {attempt + 1}/{args.attempts}: {e}")
            time.sleep(2)
    print("  could not reset")
    return 1

def cmd_brett_walk(args):
    """Walk the full route to the table."""
    import perform_brett_walk
    return 0 if perform_brett_walk.main(log=print) else 1


def cmd_walk(args):
    """Walk the whole route: spawn -> table."""
    import graph_walk
    import worldmap

    if not _live():
        return 2
    m = worldmap.WorldMap.load()
    if args.reset and cmd_reset(args) != 0:
        return 1
    res = graph_walk.follow(m, args.start, GOAL, log=print, shots=args.shots)
    print(f"\n  {'ARRIVED' if res['arrived'] else 'did not arrive'} — "
          f"reached {res.get('reached')!r} ({res.get('reason')})")
    return 0 if res["arrived"] else 1


def cmd_last_mile(args):
    """Just the final stretch, from wherever the character is standing."""
    import last_mile

    if not _live():
        return 2
    return last_mile.main(tuple(args.durations), log=print)


def cmd_label(args):
    """Save the current view as a reference frame for a place YOU name.

    This is the one thing the automation cannot do for itself. Room recognition
    fails when the executor stops somewhere the reference set does not cover —
    a different spot, or the NPCs moved — and the fix is a frame taken there,
    labelled by someone who can see the screen. Each one added this way took a
    room from "abstains" to recognised: portrait_room went to 11 of 11.

    It refuses to label a frame with too little structure. A near-blank frame
    is not a fingerprint of anywhere, and adding one poisons the whole set: a
    dark office door once matched the BAR at 0.906, higher than any real match.
    """
    import compass
    import places

    img = _snapshot()
    if img is None:
        return 2
    _, desc = places.keypoints(img)
    n = 0 if desc is None else len(desc)
    if n < args.min_keypoints:
        print(f"  REFUSING: only {n} keypoints (need {args.min_keypoints}). "
              f"A frame with no structure matches every other blank frame — "
              f"that is how an upstairs door scored 0.906 as the bar.")
        return 1
    path = places.add(args.place, img)
    print(f"  saved {path}  ({n} keypoints)")
    print(f"  now identifies as: {places.identify(img)}")
    return 0


def _to_node(node, log=print, allow_reset=True):
    """Stand at `node` and prove it. Returns True only if the localiser agrees."""
    import graph_walk
    import worldmap

    m = worldmap.WorldMap.load()
    where, _ = graph_walk.locate(m, log=lambda *a: None)
    if where == node:
        return True
    if not allow_reset:
        return False
    return graph_walk.go_to_node_verified(m, node, log=log, attempts=2)


def cmd_sweep(args):
    """Try a grid of last-mile durations and report which reach the table.

    Repositions itself between trials rather than asking you to re-park: it
    resets and walks to portrait_room, which the localiser has recognised in 11
    of 11 passes and is where the Wanda drop-off lands anyway.

    The point is to replace tuning three numbers by hand, one live run at a
    time, with one unattended pass that says which combination actually works.
    """
    import itertools
    import json

    import compass
    import last_mile
    import table_prompt as tp

    if not _live():
        return 2

    grid = list(itertools.product(args.corner, args.jukebox, args.table))
    print(f"  {len(grid)} combinations x ~{sum(args.corner)/len(args.corner) + sum(args.jukebox)/len(args.jukebox) + sum(args.table)/len(args.table) + 25:.0f}s each\n")
    rows = []
    for i, durs in enumerate(grid, 1):
        if not _to_node(args.start, log=lambda *a: None):
            print(f"  [{i}/{len(grid)}] could not get back to {args.start}; skipping")
            rows.append({"durations": durs, "error": "setup"})
            continue
        last_mile.main(durs, log=lambda *a: None)
        img = compass.fast_capture()
        hit = bool(tp.at_table(img))
        rows.append({"durations": durs, "at_table": hit,
                     "ink": round(tp.ink(img), 4)})
        print(f"  [{i}/{len(grid)}] corner {durs[0]:.1f} jukebox {durs[1]:.1f} "
              f"table {durs[2]:.1f} -> at_table={hit} (ink {rows[-1]['ink']:.4f})")

    if args.out:
        json.dump(rows, open(args.out, "w"), indent=1)
        print(f"\n  wrote {args.out}")
    hits = [r for r in rows if r.get("at_table")]
    print(f"\n  reached the table: {len(hits)}/{len([r for r in rows if 'error' not in r])}")
    for h in hits:
        print(f"    WORKS: corner {h['durations'][0]} jukebox {h['durations'][1]} "
              f"table {h['durations'][2]}")
    if not hits:
        best = max((r for r in rows if "error" not in r),
                   key=lambda r: r.get("ink", 0), default=None)
        if best:
            print(f"    none reached it; closest was {best['durations']} "
                  f"at ink {best['ink']:.4f} (threshold ~0.024)")
    return 0 if hits else 1


def cmd_record_leg(args):
    """Walk one leg from where the EXECUTOR stands and save it if it lands.

    The legs in world_map.json came from a human's recorded walk, which started
    from a different pose than the bot reaches. Measured 2026-09-02: a bearing
    that provably worked from one pose failed from another 157px away, and the
    character cannot always correct because it is against the bar stools. So a
    leg is only worth recording FROM the pose the executor actually arrives at.

    Refuses to save unless the localiser confirms the destination — an
    unverified leg in the map is worse than no leg, because routing will plan
    through it forever.
    """
    import compass
    import places
    import table_prompt as tp
    import walk_steps as ws
    import worldmap

    if not _live():
        return 2
    if not _to_node(args.start, log=print):
        print(f"  could not verify standing at {args.start}; refusing to record "
              f"a leg from an unknown pose")
        return 1

    print(f"  at {args.start}; walking {args.bearing:.1f} for {args.duration:.2f}s")
    ws.turn_to(args.bearing % 360.0, log=lambda *a: None)
    time.sleep(0.3)
    left = args.duration
    while left > 0.01:                       # <=0.8s pushes: chiaki's watchdog
        step = min(0.8, left)
        ws.walk_forward(args.speed, step)
        time.sleep(0.2)
        left -= step
    time.sleep(0.5)

    img = compass.fast_capture()
    if args.end == GOAL:
        arrived = bool(tp.at_table(img))
        detail = f"at_table={arrived}"
    else:
        room, n, ratio = places.identify(img)
        arrived = room == args.end
        detail = f"identify={room} ({n} matches, ratio {ratio})"
    print(f"  arrived at {args.end}? {arrived}   {detail}")
    if not arrived:
        print("  NOT saving: the destination was not confirmed. A leg the "
              "router plans through must be one that was actually walked.")
        return 1

    m = worldmap.WorldMap.load()
    for n_ in (args.start, args.end):
        if n_ not in m.landmarks:
            m.mark(n_)
    m.connect(args.start, args.end,
              [{"bearing": round(args.bearing % 360.0, 1),
                "dur": round(args.duration, 2), "speed": args.speed}],
              one_way=True,
              note=f"recorded from the executor's own {args.start} pose")
    m.save()
    print(f"  saved {args.start} -> {args.end}: bearing "
          f"{args.bearing % 360.0:.1f} for {args.duration:.2f}s")
    return 0


def cmd_calibrate_window(args):
    """Record the chiaki window's current position as this machine's reference.

    THE GUARD THIS ARMS HAS NEVER FIRED. input_controller.window_drift() cannot
    report drift until a reference exists, and save_window_reference() had ZERO
    callers — it was named only inside a preflight help string, so
    window_reference.json was never written and the check could only ever say
    "ok". What it guards, measured: a 58px displacement changed nothing, 110px
    silently FLIPPED a ban-grid cell, banning a different card with no error.

    Run this ONCE when the regions are known good — i.e. when a ban screen is
    reading correctly. Re-running it re-baselines to wherever the window is
    now, which silently forgives real drift, so do not run it to make preflight
    quiet.
    """
    import input_controller as ic
    rect = ic.save_window_reference()
    if rect is None:
        print("the chiaki window is not open — start the stream first")
        return 1
    print(f"calibrated: window at {tuple(int(v) for v in rect)}")
    print(f"preflight will now fail if it moves more than "
          f"{ic.WINDOW_DRIFT_MAX_PT:.0f}pt")
    return 0


COMMANDS = {
    "where": (cmd_where, "report position; moves nothing"),
    "calibrate-window": (cmd_calibrate_window,
                         "record the window position preflight checks against"),
    "doctor": (cmd_doctor, "check chiaki, FIFO, stream, frame, runaways"),
    "connect": (cmd_connect, "bring chiaki and the stream up"),
    "reset": (cmd_reset, "reload the save and stand at the spawn"),
    'brett-walk': (cmd_brett_walk, "walk the full route to the table"),
    "walk": (cmd_walk, "walk the full route to the table"),
    "last-mile": (cmd_last_mile, "Wanda -> corner -> jukebox -> table"),
    "label": (cmd_label, "save the current view as a reference for a place"),
    "sweep": (cmd_sweep, "grid-search the last-mile durations"),
    "record-leg": (cmd_record_leg, "walk a leg and save it if it lands"),
}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subs = p.add_subparsers(dest="command", required=True)
    for name, (_fn, help_text) in COMMANDS.items():
        sp = subs.add_parser(name, help=help_text)
        if name == "reset":
            sp.add_argument("--attempts", type=int, default=3)
        if name == "walk":
            sp.add_argument("--start", default=SPAWN)
            sp.add_argument("--shots", default=None,
                            help="directory to save an arrival frame per node")
            sp.add_argument("--reset", action="store_true",
                            help="reload the save first")
            sp.add_argument("--attempts", type=int, default=3)
        if name == "label":
            sp.add_argument("place", help="e.g. bar_jukebox")
            sp.add_argument("--min-keypoints", type=int, default=200)
        if name == "sweep":
            sp.add_argument("--corner", type=float, nargs="+", default=[1.6, 2.0, 2.4])
            sp.add_argument("--jukebox", type=float, nargs="+", default=[2.6, 3.3, 4.0])
            sp.add_argument("--table", type=float, nargs="+", default=[3.4, 4.1, 4.8])
            sp.add_argument("--start", default="portrait_room")
            sp.add_argument("--out", default="overnight/sweep.json")
        if name == "record-leg":
            sp.add_argument("start")
            sp.add_argument("end")
            sp.add_argument("--bearing", type=float, required=True)
            sp.add_argument("--duration", type=float, required=True)
            sp.add_argument("--speed", type=float, default=0.25)
        if name == "last-mile":
            sp.add_argument("--durations", type=float, nargs=3,
                            default=[2.0, 3.3, 4.1],
                            metavar=("CORNER", "JUKEBOX", "TABLE"))
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command][0](args)


if __name__ == "__main__":
    sys.exit(main())
