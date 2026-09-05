"""Turn the recorded run into a WORLD-SPACE path of short straight steps.

The character's direction of travel is not where the camera points: it is the
camera bearing combined with the angle of the left stick. Recovering that gives
a path that can be walked as "face a bearing, walk forward", with no turning
while moving — which is where position error came from.

STEPS ARE KEPT SHORT ON PURPOSE. An earlier version grouped any samples within
18 degrees of each other and produced a 6.3 second step covering the whole
corridor. That flattened a curving path — one that threads a doorway and
crosses a street — into a single straight line, and the run ended up short,
still inside the building, while the recording was already outside at the L&B
entrance. Capping each step forces the path to follow its actual curve.
"""

import json
import math

MAX_STEP_SEC = 0.8         # a straight line is only a good approximation briefly
GROUP_DEGREES = 8.0        # bearing change that starts a new step
MIN_SPEED = 0.15
MIN_STEP_SEC = 0.10


def _err(a, b):
    return (a - b + 540) % 360 - 180


def _heading_at(hp, t):
    if t <= hp[0][0]:
        return hp[0][1]
    for (a, ha), (b, hb) in zip(hp, hp[1:]):
        if t <= b:
            f = 0.0 if b == a else (t - a) / (b - a)
            return (ha + _err(hb, ha) * f) % 360
    return hp[-1][1]


def build(demo_dir, headings_path, t0=9.0, t1=25.2, out="route_steps.json"):
    inp = json.load(open(f"{demo_dir}/input.json"))
    hp = [(h["t"], h["heading"]) for h in json.load(open(headings_path))]

    moving = []
    for s in inp:
        t = s["t"]
        if not (t0 <= t <= t1):
            continue
        a = s["axes"]
        lx, ly = a.get("lx", 0.0), a.get("ly", 0.0)
        speed = math.hypot(lx, ly)
        if speed < MIN_SPEED:
            continue
        world = (_heading_at(hp, t) + math.degrees(math.atan2(lx, -ly))) % 360
        moving.append((t, world, speed))

    steps, cur = [], None
    for t, w, sp in moving:
        same = (cur and abs(_err(w, cur["w"])) < GROUP_DEGREES
                and t - cur["t1"] < 0.15
                and t - cur["t0"] < MAX_STEP_SEC)
        if same:
            cur["t1"] = t
            cur["n"] += 1
            cur["sp"] += sp
            cur["w"] = (cur["w"] + _err(w, cur["w"]) / cur["n"]) % 360
        else:
            if cur:
                steps.append(cur)
            cur = {"w": w, "t0": t, "t1": t, "n": 1, "sp": sp}
    if cur:
        steps.append(cur)

    out_steps = [{"bearing": round(s["w"], 2),
                  "dur": round(s["t1"] - s["t0"], 3),
                  "speed": round(s["sp"] / s["n"], 3),
                  "t0": round(s["t0"], 3),
                  "cam": round(_heading_at(hp, s["t1"]), 2)}
                 for s in steps if s["t1"] - s["t0"] >= MIN_STEP_SEC]
    json.dump(out_steps, open(out, "w"), indent=1)
    return out_steps


if __name__ == "__main__":
    st = build("demos/walk_20260827_214446", "route_headings.json")
    print(f"  {len(st)} steps, {sum(s['dur'] for s in st):.2f}s of walking")
    for i, s in enumerate(st, 1):
        print(f"   {i:2}  t={s['t0']:5.2f}  bearing {s['bearing']:6.1f}  "
              f"{s['dur']:.2f}s  speed {s['speed']:.2f}")
