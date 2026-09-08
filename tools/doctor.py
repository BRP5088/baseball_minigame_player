"""Is the whole chain actually up? Each line is a thing that has broken. MOVES NOTHING.

    .venv/bin/python -B tools/doctor.py

Ported from `Bretts_walk.py doctor` / `where` when that entry point was deleted
(2026-09-07). Read-only: captures the game window and reads it; presses nothing.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def snapshot(log=print):
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
    log(f"  served by {'the frame DUMP' if img.info.get('frame_dump') else 'the SCREEN'}")
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


def main():
    import ensure_stream
    import kill_runaways
    ok = True
    chiaki = subprocess.run(["pgrep", "-x", "chiaki"], capture_output=True).returncode == 0
    print(f"  chiaki running     {chiaki}")
    ok &= chiaki
    fifo = os.path.exists(os.environ.get("CHIAKI_INJECT_INPUT", "/tmp/chiaki_input"))
    print(f"  inject FIFO        {fifo}"
          f"{'' if fifo else '   <- input will fall back to the keyboard path'}")
    try:
        streaming = ensure_stream.streaming()
    except Exception as e:
        streaming = f"error: {type(e).__name__}"
    print(f"  streaming          {streaming}")
    try:
        frozen = ensure_stream.is_frozen()
        print(f"  picture frozen     {frozen}"
              f"{'   <- decoder stalled; ./restart_chiaki.sh' if frozen else ''}")
        ok &= not frozen
    except Exception as e:
        print(f"  picture frozen     unknown ({type(e).__name__})")
    # WHICH PATH SERVED THE FRAME. The whole point of the dump is that a
    # capture no longer needs chiaki's window to be on the current Space, so
    # "is the dump alive" is now a rig fact on the same footing as "is the
    # FIFO there" -- and when it is NOT alive, every capture is back to
    # grabbing the screen and will die at the next Space switch. Silence here
    # would make the two states look identical, which is this project's
    # signature failure.
    try:
        import frame_dump
        st = frame_dump.stats()
    except Exception as e:
        st = None
        print(f"  frame dump         unreadable ({type(e).__name__}: {e})")
    if st is not None:
        # The gate the reader would actually apply, which is derived from the
        # writer's own throttle -- not the module's floor.
        fresh = st["age_s"] <= st.get("age_limit_s", frame_dump.MAX_AGE_S)
        print(f"  frame dump         {st['path']}  {st['width']}x{st['height']} "
              f"seq {st['seq']}  age {st['age_s'] * 1000:.0f}ms"
              f"  push {st['push_us']}us"
              f"{'' if fresh else '   <- STALE; captures fall back to the screen'}")
    else:
        print(f"  frame dump         absent   <- captures grab the SCREEN, which "
              f"fails when chiaki's window leaves the current Space "
              f"(is CHIAKI_FRAME_DUMP exported? does the log say 'frame dump'?)")
    print("  --- current frame ---")
    ok &= snapshot() is not None
    stray = kill_runaways.find()
    print(f"  runaway processes  {len(stray)}"
          f"{'   <- run: python3 kill_runaways.py --kill' if stray else ''}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
