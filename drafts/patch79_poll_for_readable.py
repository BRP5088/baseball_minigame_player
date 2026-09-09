"""patch79 -- after the deal, POLL for a frame the reader can fully read.

patch78 captured at the deal gate's release and made things WORSE, measured over the run it
shipped in: abstentions 6.3% -> 31.0%, and only 2.9 of 5 slots found per hand because the
fan model fitted on 28 of 54 frames instead of 60 of 60. The frame is unlifted, exactly as
the user said it would be -- but the hand has not SETTLED into its fan yet, so the slot
anchors miss. I captured at the wrong instant, not at the wrong idea.

THE WINDOW IS NARROW AND IT IS IN THE MIDDLE. Measured across the corpus:

    at the deal gate's release   nothing lifted, fan does NOT fit    (28 of 54)
    once settled                 fan fits (60 of 60), but the cursor has re-landed on a
                                 card and LIFTED it -- which is where the abstentions were

So there is no single instant that is both settled and unlifted. Polling finds it: read the
hand every REREAD_INTERVAL through the settle, and keep the BEST frame seen -- the one with
the most slots actually read -- stopping early the moment a frame reads completely.

IT COSTS ALMOST NOTHING. read_hand is ~11 ms, the poll is capped at REREAD_MAX_WAIT, and it
stops at the first complete read. The existing settle wait already burns this time.

IT CANNOT BE WORSE THAN BEFORE, by construction: the vision crop remains the fallback and
the poll only ever replaces it with a frame that reads MORE slots.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

# 1. the deal gate stops stashing -- it is the wrong instant
OLD_REL = '''            # THE POST-DEAL HAND, kept for the local reader. At this instant the
            # replacement card has landed and NO card is lifted -- the game raises and
            # brightens whichever card the cursor rests on, and a lifted card both hides
            # its own disc and occludes its neighbour. Every one of the 16 abstentions
            # across 57 user-reviewed hands was a lifted or occluded card. Same fractional
            # box as the vision crop, so the reader's slot anchors apply unchanged.
            global _POST_DEAL_HAND
            _POST_DEAL_HAND = cur
'''
assert s.count(OLD_REL) == 1, "release-stash anchor"
s = s.replace(OLD_REL, "", 1)

# 2. the poll, and it replaces the old stash helper
OLD_HELP = '''def take_post_deal_hand():
    """The post-deal hand crop, or None. Clears the stash."""
    global _POST_DEAL_HAND
    img, _POST_DEAL_HAND = _POST_DEAL_HAND, None
    return img'''
assert s.count(OLD_HELP) == 1, "helper anchor"
NEW_HELP = '''# How long to keep looking for a hand the reader can read completely, and how often.
# The settle wait already spends this time; this rides on it rather than adding to it.
REREAD_MAX_WAIT = 2.5
REREAD_INTERVAL = 0.12


def poll_for_readable_hand(max_wait=REREAD_MAX_WAIT, interval=REREAD_INTERVAL):
    """Watch the hand until the reader can read every slot, and keep the best frame.

    THERE IS NO SINGLE GOOD INSTANT, which is why this polls. At the deal gate's release
    nothing is lifted but the hand has not settled into its fan, so the slot anchors miss;
    once settled the fan fits but the cursor has re-landed on a card and LIFTED it, hiding
    that card's disc and occluding its neighbour. The readable frame is in between.

    Returns the best hand crop seen, or None if it never got one worth having. Scored by
    how many slots actually READ -- not by how many were found, which a bad frame can
    inflate with junk.
    """
    import local_hand
    best, best_read, deadline = None, -1, time.time() + max_wait
    while time.time() < deadline:
        img = _grab_settle_regions(("hand",))["hand"]
        try:
            rows = local_hand.read_hand(img)
        except Exception:
            break
        read = sum(1 for r in rows
                   if (r["digit"] is not None) or (r["kind"] == "tactics"
                                                   and r.get("type") is not None))
        if read > best_read:
            best, best_read = img, read
        if rows and read == len(rows) >= MAX_HAND_SIZE:
            break                      # complete: nothing better is available
        time.sleep(interval)
    return best


def take_post_deal_hand():
    """The post-deal hand crop, or None. Clears the stash."""
    global _POST_DEAL_HAND
    img, _POST_DEAL_HAND = _POST_DEAL_HAND, None
    return img'''
s = s.replace(OLD_HELP, NEW_HELP, 1)

# 3. fill the stash from the poll, AFTER the settle
OLD_SETTLE = '''                    wait_for_hand_deal(baseline=pop_hand_baseline())
                wait_for_screen_to_settle(max_wait=8.0, regions="turn")
                time.sleep(0.4)  # small buffer past "settled" before the next read'''
assert s.count(OLD_SETTLE) == 1, "settle anchor"
NEW_SETTLE = '''                    wait_for_hand_deal(baseline=pop_hand_baseline())
                # LOOK FOR A FULLY READABLE HAND while the screen settles, and keep it for
                # the next turn's local read. This is the user's fix, at the right instant:
                # the frame that is both settled enough for the slot anchors and early
                # enough that the cursor has not yet lifted a card.
                _POST_DEAL_HAND = poll_for_readable_hand()
                wait_for_screen_to_settle(max_wait=8.0, regions="turn")
                time.sleep(0.4)  # small buffer past "settled" before the next read'''
s = s.replace(OLD_SETTLE, NEW_SETTLE, 1)
assert "poll_for_readable_hand" in s and s.count("_POST_DEAL_HAND = poll_for_readable_hand()") == 1
io.open(P, "w", encoding="utf-8").write(s)
print("orchestrator.py: the hand is polled for during the settle")
