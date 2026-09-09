"""Record the game stream from chiaki's frame dump to an H.264 file at the delivered frame
rate, with a per-frame index -- the source of truth an agent can review frame by frame.

    .venv/bin/python -B tools/record_stream.py <out_dir> [seconds]     (default: until Ctrl-C)

Writes <out_dir>/stream.mp4 (h264_videotoolbox, the Mac's hardware encoder: near-zero CPU)
and <out_dir>/frames.jsonl, one row per frame: {"i": frame index in the video, "seq": the
dump's sequence number, "t": wall seconds since start, "mono_ns": the dump's monotonic
stamp}. Extract frame i with:
    ffmpeg -i stream.mp4 -vf "select=eq(n\\,I)" -vframes 1 frame.png
The raw NV12 payload goes straight to ffmpeg (no RGB conversion here); the dump is polled
every 2 ms and only NEW seq numbers are written, so the video runs at whatever the writer
delivers (FRAME_DUMP_MIN_INTERVAL_MS: 50 -> 20 fps, 10 -> 60 fps). Read-only on the rig.
"""
import os, sys, time, json, subprocess, signal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import frame_dump

FFMPEG = "/opt/homebrew/opt/ffmpeg@7/bin/ffmpeg"
PIX = {frame_dump.FMT_NV12: "nv12", frame_dump.FMT_I420: "yuv420p"}

def main(out_dir, seconds=None, path=None, fps_hint=60):
    os.makedirs(out_dir, exist_ok=True)
    path = frame_dump.dump_path(path)
    m = frame_dump._mapping(path)
    if m is None:
        print(f"no dump at {path} (is the patched chiaki running with CHIAKI_FRAME_DUMP set?)"); return 1
    snap = None
    for _ in range(50):                      # a torn read returns None; retry briefly
        snap = frame_dump._snapshot(m)
        if snap is not None:
            break
        time.sleep(0.01)
    if snap is None:
        print("no consistent frame in the dump (is the patched chiaki streaming?)"); return 1
    hdr, payload = snap
    w, h, fmt = hdr["width"], hdr["height"], hdr["pix_fmt"]
    if not frame_dump._planes_are_packed(hdr):
        print("dump planes are not packed; cannot pipe raw"); return 1
    ff = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                           "-f", "rawvideo", "-pix_fmt", PIX[fmt], "-s", f"{w}x{h}", "-r", str(fps_hint), "-i", "-",
                           "-c:v", "h264_videotoolbox", "-b:v", "8M", "-pix_fmt", "yuv420p",
                           os.path.join(out_dir, "stream.mp4")], stdin=subprocess.PIPE)
    idx = open(os.path.join(out_dir, "frames.jsonl"), "w")
    t0 = time.time(); last_seq = None; n = 0; torn = 0
    stop = {"now": False}
    signal.signal(signal.SIGINT, lambda *a: stop.__setitem__("now", True))
    try:
        while not stop["now"] and (seconds is None or time.time() - t0 < seconds):
            snap = frame_dump._snapshot(m)
            if snap is None:
                torn += 1; time.sleep(0.002); continue
            hdr, payload = snap
            if hdr["seq"] != last_seq:
                last_seq = hdr["seq"]
                ff.stdin.write(payload[:hdr["frame_bytes"]])
                idx.write(json.dumps({"i": n, "seq": hdr["seq"], "t": round(time.time() - t0, 4),
                                      "mono_ns": hdr.get("mono_ns")}) + "\n")
                n += 1
            time.sleep(0.002)
    finally:
        ff.stdin.close(); ff.wait(); idx.close()
    span = time.time() - t0
    print(f"{n} frames in {span:.1f}s = {n / span:.1f} fps -> {out_dir}/stream.mp4 "
          f"({os.path.getsize(os.path.join(out_dir, 'stream.mp4')) / 1e6:.1f} MB), torn reads {torn}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None))
