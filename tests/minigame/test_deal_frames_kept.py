"""The deal gate KEEPS the frames it already grabs, and clears them per deal.

WHY THIS IS WORTH A TEST. wait_for_hand_deal has captured the hand region every
poll for the life of the project and kept only a mean-abs-delta number. Those
pixels are the ONLY record of a card while it is still in flight -- and the hail
mary cannot recover a card dealt straight into occlusion, because it looks for
that card unoccluded in an EARLIER HAND. So "the frames were kept" and "the
frames were silently dropped" must not look the same, which is CLAUDE.md 10.1's
whole family.

Plain asserts on purpose: this suite has four incompatible check() signatures
and a reversed call to a name-first one prints "PASS True" and can never fail.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import orchestrator as o

fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


def drive(polls, base):
    """Run the gate against stubs for `polls` polls. Returns the kept frames.

    Every capture is stubbed, so NOTHING reaches the console -- and the frames
    differ per poll so a keep that stored one image N times is visible.
    """
    made = []
    state = {"n": 0}

    def fake_fast_grab():
        return Image.new("RGB", (1920, 1080), 0)

    def fake_crop(img):
        state["n"] += 1
        # A DIFFERENT IMAGE EVERY POLL. Identical frames would let a broken keep
        # that appends the same object every time pass.
        im = Image.new("RGB", (979, 307), (base + state["n"]) % 251)
        made.append(im)
        return [("hand", im)]

    def fake_settle(names):
        # Delta stays UNDER the threshold, so the gate never releases early and
        # runs the full window -- the keep is what is under test, not the gate.
        return {"hand": Image.new("L", (100, 100), 0)}

    saved = {k: getattr(o, k) for k in
             ("_fast_grab", "crop_gameplay_regions", "_grab_settle_regions",
              "pop_deal_inputs", "_hand_signature")}
    try:
        o._fast_grab = fake_fast_grab
        o.crop_gameplay_regions = fake_crop
        o._grab_settle_regions = fake_settle
        o.pop_deal_inputs = lambda: []
        o._hand_signature = lambda img: None
        o.wait_for_hand_deal(max_wait=polls * 0.05, poll_interval=0.02)
    finally:
        for k, v in saved.items():
            setattr(o, k, v)
    return o.deal_frames(), made


kept, made = drive(6, base=10)

# 1. THE FRAMES SURVIVE THE GATE.
want("the deal gate kept frames", len(kept) > 0,
     f"kept {len(kept)} of {len(made)} captured")

# 2. THEY ARE THE POLLS' OWN FRAMES, not one image repeated.
colours = {im.getpixel((0, 0)) for _, im in kept}
want("the kept frames are distinct per poll", len(colours) == len(kept),
     f"{len(colours)} distinct of {len(kept)}")

# 3. EACH CARRIES ITS TIME, ascending, so a later reader can order the deal.
ts = [t for t, _ in kept]
want("timestamps ascend", ts == sorted(ts), str(ts))
want("the first frame is near the start of the gate", ts and ts[0] < 0.5, str(ts[:1]))

# 4. THE NEXT DEAL DOES NOT INHERIT THIS ONE. Without the reset, a deal that
#    captured nothing would be handed the PREVIOUS deal's frames and a reader
#    would attribute one deal's cards to another -- confidently.
first_colours = colours
kept2, _ = drive(6, base=120)
want("a second deal does not carry the first deal's frames",
     not (first_colours & {im.getpixel((0, 0)) for _, im in kept2}),
     "frames leaked between deals")

# 5. THE CAP IS REAL, so a gate that never releases cannot grow without bound.
want("the keep is bounded", o._DEAL_FRAMES.maxlen == o.DEAL_FRAME_KEEP,
     f"maxlen {o._DEAL_FRAMES.maxlen} vs DEAL_FRAME_KEEP {o.DEAL_FRAME_KEEP}")

# 6. keep_deal_frame NEVER RAISES -- it sits inside the deal gate, and the gate
#    escaping is what ended a run on 2026-09-14.
try:
    o.keep_deal_frame(None, 0.0)
    o.keep_deal_frame("not an image", 1.0)
    ok = True
except Exception as exc:
    ok = False
want("keep_deal_frame swallows bad input", ok, "it raised")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
