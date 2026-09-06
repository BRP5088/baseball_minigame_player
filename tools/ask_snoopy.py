"""Ship a drive to Snoopy, reconstruct it there, and ask ONE question:

    am I getting geometry out of this ground, or not?

WHY THIS EXISTS. The office drive looked perfect on this machine -- 1064 frames,
95% headings, all eight approach angles, the stick logged on every frame, the
stream alive on every pair -- and its reconstruction kept THREE points out of
196,198 tracks. Nothing visible locally could have said so. The camera had
rotated for 61% of the drive and translated for 17%, and a camera that only
rotates carries no depth information at all: the rays stay parallel and every
distance fits equally well.

That took a whole room's worth of driving to discover. Snoopy can answer it in
about two minutes, because it holds the only thing the Mac does not -- the
reconstruction itself.

THE ANSWER IS A DIAGNOSIS, NOT A SCORE. The multi-view stage records WHY each
track was rejected, and those reasons map onto different mistakes:

    positions too close   the camera is not translating -- too much turning
    too few views         features are not surviving between frames -- too fast
    behind a camera       the trajectory is wrong, not the driving
    reprojection          the poses disagree with what was seen

Nothing here drives anything, and it is safe to run while a collection is in
progress: the copy and the SSH are light and the reconstruction happens on the
other machine.
"""
import json
import os
import subprocess
import sys

KEY = os.path.expanduser("~/.ssh/id_ed25519_snoopy")
HOST = "Brett@snoopy"
REMOTE = "C:/baseball/data/drives"


def sn(cmd, timeout=1800):
    r = subprocess.run(["ssh", "-i", KEY, "-o", "BatchMode=yes", HOST, cmd],
                       capture_output=True, text=True, timeout=timeout)
    out = "\n".join(l for l in (r.stdout or "").splitlines()
                    if "post-quantum" not in l and "openssh.com/pq" not in l
                    and not l.startswith("** "))
    return r.returncode, out.replace("\r", "")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: ask_snoopy.py <drive-directory>")
    d = sys.argv[1].rstrip("/")
    name = os.path.basename(d)
    meta = os.path.join(d, "meta.json")
    if not os.path.exists(meta):
        raise SystemExit(f"{d} has no meta.json — nothing to reconstruct")
    n_local = len([f for f in os.listdir(d) if f.endswith(".jpg")])
    print(f"asking Snoopy about {name} ({n_local} frames)")

    subprocess.run(["scp", "-q", "-r", "-i", KEY, "-o", "BatchMode=yes",
                    d, f"{HOST}:{REMOTE}/"], check=False, timeout=3600)
    rc, far = sn(f"(Get-ChildItem '{REMOTE}/{name}'.Replace('/','\\\\') "
                 f"-Filter *.jpg | Measure-Object).Count")
    far = (far.strip().splitlines() or ["0"])[-1]
    if far != str(n_local):
        raise SystemExit(f"  copy incomplete: local {n_local}, Snoopy {far} — "
                         f"not reconstructing a partial drive")
    print(f"  shipped and verified ({far} frames)")

    rc, out = sn(f'C:\\baseball\\venv\\Scripts\\python.exe '
                 f'C:\\baseball\\reconstruct_mv.py '
                 f'C:\\baseball\\data\\drives\\{name} '
                 f'C:\\baseball\\data\\{name}_mv.json')
    print(out.strip())

    # ---- the verdict ----------------------------------------------------
    rc2, js = sn(f'Get-Content C:\\baseball\\data\\{name}_mv.json -Raw')
    try:
        r = json.loads(js)
    except Exception:
        raise SystemExit("  could not read the result back")
    st = r.get("stats", {})
    kept = st.get("kept", 0)
    total = sum(st.get(k, 0) for k in
                ("short", "tight", "dlt", "cheir", "depth", "reproj", "kept"))
    print("\n--- VERDICT ---")
    print(f"  {kept} points from {total} tracks "
          f"({100*kept/max(total,1):.2f}%)")
    if total == 0:
        print("  nothing to judge — no tracks were built at all")
        return
    worst = max(("short", "tight", "cheir", "depth", "reproj"),
                key=lambda k: st.get(k, 0))
    share = 100 * st.get(worst, 0) / total
    advice = {
        "tight": ("the camera is not MOVING between views. Walk in straight "
                  "lines and turn only at the ends -- turning on the spot "
                  "contributes no depth at all."),
        "short": ("features are not surviving between frames. You are moving "
                  "or turning too FAST for 5 Hz; slow down."),
        "cheir": ("points are landing behind the camera, which means the "
                  "TRAJECTORY is wrong rather than the driving. Do not collect "
                  "more until that is fixed."),
        "depth": ("points are landing on the camera path. Same cause as "
                  "'behind a camera': the trajectory, not the driving."),
        "reproj": ("the poses disagree with what was seen. Heading or distance "
                   "is drifting -- check how many frames carried a stale "
                   "heading."),
    }[worst]
    if kept >= 2000:
        print(f"  GOOD — this ground is producing geometry. Keep driving it.")
    elif kept >= 200:
        print(f"  THIN — some geometry, not much.")
        print(f"  biggest loss: {worst} at {share:.0f}% of tracks. {advice}")
    else:
        print(f"  NO GEOMETRY. Do not collect more of this kind.")
        print(f"  biggest loss: {worst} at {share:.0f}% of tracks. {advice}")


main()
