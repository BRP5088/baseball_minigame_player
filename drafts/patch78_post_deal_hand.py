"""patch78 -- read the hand from the POST-DEAL frame, where no card is lifted.

THE USER, explicitly: "if you use the screenshot after cards are dealt it guarantees that
you can see all the cards since none of them are selected. that solves all issues. its
cheap, easy and the correct solution. do not go chasing dragons."

They are right, and I was modelling the animation instead of avoiding it. What the review
established, from their own labels on 62 hands:

    the game LIFTS and HIGHLIGHTS the card the cursor rests on. A lifted card renders
    brighter, so its ink passes above DARK = 110 and the finder never sees the disc; and
    the lift OCCLUDES its neighbour, which costs a second card. Worse, the lift is
    ANIMATED (their note on hand 55: "the 8 looks like it's selected and going through the
    animation"), so the same card reads in one frame and not the next -- which is why
    hands 20 and 22 read a selected card fine and hands 14, 17, 33, 35, 49 and 55 did not.

16 of 16 abstentions across 57 reviewed hands, and ZERO wrong reads. So the abstentions
are the whole remaining gap, and this removes their cause rather than compensating for it.

WHY IT IS FREE. wait_for_hand_deal already grabs the hand region on every poll, over the
SAME fractional box the vision crop uses (_settle_region_box -> GAMEPLAY_REGIONS_FRAC), and
throws it away. At the moment it releases, the replacement card has landed and nothing is
lifted. That frame is stashed and the reader is handed it.

The stash is CLEARED ON USE, so a hand left over from an earlier turn can never be read as
this turn's -- a stale frame that looks fresh is this project's signature failure and would
be invisible here.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

OLD_REL = '''        if seen and time.time() - start >= POST_PLAY_MIN_WAIT:
            print(f"  [deal] replacement card seen; released {time.time() - start:.1f}s "
                  f"after the play (threshold {th:g}, biggest delta {biggest:.1f})")
            return True'''
assert s.count(OLD_REL) == 1, f"release anchor x{s.count(OLD_REL)}"
NEW_REL = '''        if seen and time.time() - start >= POST_PLAY_MIN_WAIT:
            # THE POST-DEAL HAND, kept for the local reader. At this instant the
            # replacement card has landed and NO card is lifted -- the game raises and
            # brightens whichever card the cursor rests on, and a lifted card both hides
            # its own disc and occludes its neighbour. Every one of the 16 abstentions
            # across 57 user-reviewed hands was a lifted or occluded card. Same fractional
            # box as the vision crop, so the reader's slot anchors apply unchanged.
            global _POST_DEAL_HAND
            _POST_DEAL_HAND = cur
            print(f"  [deal] replacement card seen; released {time.time() - start:.1f}s "
                  f"after the play (threshold {th:g}, biggest delta {biggest:.1f})")
            return True'''

OLD_DECL = '''def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,'''
assert s.count(OLD_DECL) == 1, "decl anchor"
NEW_DECL = '''# The hand as it looked the instant the deal finished, with nothing lifted. Set by
# wait_for_hand_deal and CLEARED ON USE, so a hand from an earlier turn can never be
# mistaken for this turn's -- a stale frame that looks fresh is exactly the failure this
# project keeps producing.
_POST_DEAL_HAND = None


def take_post_deal_hand():
    """The post-deal hand crop, or None. Clears the stash."""
    global _POST_DEAL_HAND
    img, _POST_DEAL_HAND = _POST_DEAL_HAND, None
    return img


def wait_for_hand_deal(max_wait: float = POST_PLAY_DEAL_MAX_WAIT,'''

OLD_USE = '''        import local_hand
        vision_hand = {c.get("hand_index"): c for c in (state_json.get("hand") or [])}
        try:
            rows = local_hand.read_hand(crops["hand"])'''
assert s.count(OLD_USE) == 1, "reader call anchor"
NEW_USE = '''        import local_hand
        vision_hand = {c.get("hand_index"): c for c in (state_json.get("hand") or [])}
        # PREFER THE POST-DEAL FRAME. The vision crop is taken later, by which time the
        # cursor is resting on a card and that card is lifted, brightened and occluding
        # its neighbour. The post-deal frame has nothing lifted, which is the user's own
        # fix and removes the cause rather than compensating for it.
        hand_img = take_post_deal_hand() or crops["hand"]
        hand_src = "post-deal" if hand_img is not crops["hand"] else "vision-crop"
        try:
            rows = local_hand.read_hand(hand_img)'''

OLD_REC = '''        record_local_hand(crops, rows, state_json)'''
assert s.count(OLD_REC) == 1, "record anchor"
NEW_REC = '''        record_local_hand(dict(crops, hand=hand_img), rows, state_json, hand_src)'''

OLD_SIG = '''def record_local_hand(crops, rows, state_json):'''
assert s.count(OLD_SIG) == 1, "recorder signature anchor"
NEW_SIG = '''def record_local_hand(crops, rows, state_json, hand_src="vision-crop"):'''

OLD_ROW = '''                "t": stamp, "crop": saved.get("hand"), "crops": saved,'''
assert s.count(OLD_ROW) == 1, "row anchor"
NEW_ROW = '''                "t": stamp, "crop": saved.get("hand"), "crops": saved,
                "hand_src": hand_src,'''

out = (s.replace(OLD_DECL, NEW_DECL, 1).replace(OLD_REL, NEW_REL, 1)
        .replace(OLD_USE, NEW_USE, 1).replace(OLD_REC, NEW_REC, 1)
        .replace(OLD_SIG, NEW_SIG, 1).replace(OLD_ROW, NEW_ROW, 1))
assert "take_post_deal_hand" in out and out.count("_POST_DEAL_HAND") >= 4
io.open(P, "w", encoding="utf-8").write(out)
print("orchestrator.py: the hand is read from the post-deal frame")
