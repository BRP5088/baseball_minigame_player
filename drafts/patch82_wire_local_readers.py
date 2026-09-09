"""patch82 -- the local readers CORRECT the paid model's answer where they are measured better.

THIS DOES NOT YET REMOVE A PAID CALL. It fixes what that call gets WRONG, which is the
first honest step and is worth having on its own.

DISCARDS_LEFT IS THE CASE THAT FORCED IT. Over 360 recorded turns the local dot counter and
the paid model disagreed 155 times. The user adjudicated eight of those by eye, chosen to
span every disagreement shape:

    LOCAL 8 of 8 correct        PAID 0 of 8 correct

The paid model answers 2 on 286 of 360 turns -- a default, not a reading -- and returned an
impossible 3 in a live run, which orchestrator already has to clamp. THE USER NAMED THE
MECHANISM: "the letter S that's next to the circles has a fat middle so it looks like
another dot." The local reader samples two fixed anchors and never looks at the letters.

discards_left feeds should_redraw(), so this decides whether the agent DISCARDS or PLAYS.

THE OTHER TWO, over the same 360 turns:

    runners   99% answered, 97.2% agreeing with the paid model
    phase     86% answered, 96.1% agreeing

They are wired the same way but with a WEAKER claim, and the code says which is which: on
discards the local reader OVERRIDES, because it is measured better against human truth. On
runners and phase it only fills a field the paid model left EMPTY, because "agrees 97% of
the time" is not evidence about who is right on the other 3%.

EVERY OVERRIDE PRINTS. A silent correction is indistinguishable from no correction at all,
which is this project's signature failure (CLAUDE.md 10.1), and these run on a money path.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

ANCHOR = '''    text = "".join(block.text for block in response.content if block.type == "text").strip()
    state = extract_json(text)
    repair_misread_cards(state)
    repair_phase_from_hand(state)
    validate_game_state(state)
    return state'''
assert s.count(ANCHOR) == 1, f"read_game_state tail anchor x{s.count(ANCHOR)}"

NEW = '''    text = "".join(block.text for block in response.content if block.type == "text").strip()
    state = extract_json(text)
    repair_misread_cards(state)
    repair_phase_from_hand(state)
    apply_local_readers(state)
    validate_game_state(state)
    return state


def apply_local_readers(state: dict, crops: dict = None) -> None:
    """Correct the paid model's answer with the local readers, in place. Never raises.

    TWO DIFFERENT CLAIMS, and the code keeps them apart:

      OVERRIDE  discards_left. Measured against the USER'S OWN EYES on eight boards
                spanning every disagreement shape: local 8 of 8, paid 0 of 8. The paid
                model answers 2 on 286 of 360 turns, which is a default rather than a
                reading, and once returned an impossible 3. The user found the mechanism --
                the fat middle of the S in DISCARDS reads as a third dot -- and the local
                reader samples two fixed anchors and never sees the letters.
                This feeds should_redraw(), so it decides DISCARD against PLAY.

      FILL ONLY  runners and phase. Local agrees with the paid model 97.2% and 96.1% of
                the time over 360 turns, and agreement is NOT evidence about who is right
                on the rest. So they only supply a field the paid model left empty, and a
                disagreement is reported and then LEFT ALONE.

    Every correction prints. A silent one is indistinguishable from none at all, and these
    run on a $50 path.
    """
    if crops is None:
        crops = _last_gameplay_crops
    if not crops or state.get("screen") not in ("turn", "discard_prompt"):
        return
    try:
        import local_state
    except Exception:
        return

    if crops.get("scoreboard") is not None:
        try:
            got = local_state.read_discards_left(crops["scoreboard"])
        except Exception:
            got = None
        if got is not None and got != state.get("discards_left"):
            print(f"  [local] discards_left {state.get('discards_left')} -> {got} "
                  f"(the dot counter; the paid model was 0 of 8 against the user's eyes "
                  f"on this field)")
            state["discards_left"] = got

    if crops.get("hand") is not None and not state.get("phase"):
        try:
            ph, _ = local_state.read_phase(crops["hand"])
        except Exception:
            ph = None
        if ph:
            print(f"  [local] phase was empty -> {ph} (the card banners, unanimous)")
            state["phase"] = ph

    bases = ("third_base", "second_base", "first_base")
    if state.get("runners") is None and all(crops.get(b) is not None for b in bases):
        try:
            out = local_state.read_runners(*[crops[b] for b in bases])
        except Exception:
            out = None
        if out and out.get("count") is not None:
            # The count is all decision_engine consumes (it branches on runners being
            # non-empty). A NAME cannot be supplied by a disc reader, so the entries are
            # explicitly nameless rather than invented.
            state["runners"] = [{"name": None, "power": None, "secondary": None}
                                for _ in range(out["count"])]
            print(f"  [local] runners was empty -> {out['count']} on base "
                  f"(bases read locally; names not available and not invented)")'''

io.open(P, "w", encoding="utf-8").write(s.replace(ANCHOR, NEW, 1))
print("orchestrator.py: apply_local_readers wired into read_game_state")
