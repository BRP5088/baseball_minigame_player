"""patch80 -- read BOTH frames and keep the better one. My "cannot be worse" was false.

patch79 polls during the settle and keeps the frame that reads the most slots -- but it
compared the polled frames only WITH EACH OTHER, then handed the winner over
unconditionally. When every frame in the window is bad, a bad frame replaces a good vision
crop. Measured on the run it shipped in, 43 hands:

    5 of 5 read      12
    4 of 5 read      17
    3 of 5 read       1
    COUNT MISMATCH   13, of which TEN found ZERO positions

Ten hands where the reader found nothing at all is worse than anything the vision crop ever
did. I wrote "it cannot be worse than before by construction" in patch79's own message.
That was wrong, and it was wrong in the specific way this project keeps repeating: the
comparison that would have shown it was never made.

THE FIX IS TO ACTUALLY COMPARE. Read the polled frame AND the vision crop, score both by
slots actually read, and keep the better -- ties going to the vision crop, which is the
older and better-understood path. Two reads is ~22 ms.

This is not a smaller claim than patch79's, it is a CHECKED one: the fallback is now
measured against, not assumed better than.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''        # PREFER THE POST-DEAL FRAME. The vision crop is taken later, by which time the
        # cursor is resting on a card and that card is lifted, brightened and occluding
        # its neighbour. The post-deal frame has nothing lifted, which is the user's own
        # fix and removes the cause rather than compensating for it.
        hand_img = take_post_deal_hand() or crops["hand"]
        hand_src = "post-deal" if hand_img is not crops["hand"] else "vision-crop"
        try:
            rows = local_hand.read_hand(hand_img)
        except Exception as e:
            print(f"  [local-check] hand: local reader failed ({e})")
            rows = []'''
assert s.count(OLD) == 1, f"reader-call anchor x{s.count(OLD)}"

NEW = '''        # READ BOTH FRAMES AND KEEP THE BETTER. The polled frame is usually the good one
        # -- the vision crop is taken after the cursor has re-landed and LIFTED a card,
        # which hides that card's disc and occludes its neighbour. But the poll can also
        # come back with nothing usable, and patch79 handed its winner over regardless:
        # ten hands in one run found ZERO positions, which is worse than the crop it
        # replaced. So the two are scored against each other rather than ranked by
        # assumption. Ties go to the vision crop, the older and better-understood path.
        def _n_read(rr):
            return sum(1 for r in rr
                       if (r["digit"] is not None)
                       or (r["kind"] == "tactics" and r.get("type") is not None))

        def _try(img):
            try:
                return local_hand.read_hand(img)
            except Exception as e:
                print(f"  [local-check] hand: local reader failed ({e})")
                return []

        polled = take_post_deal_hand()
        rows = _try(crops["hand"])
        hand_img, hand_src = crops["hand"], "vision-crop"
        if polled is not None:
            alt = _try(polled)
            if _n_read(alt) > _n_read(rows):
                rows, hand_img, hand_src = alt, polled, "post-deal"'''

io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
print("orchestrator.py: both frames are read and the better one kept")
