"""Does Haiku classify SCREENS as reliably as Sonnet?

Reading card names and power stays on Sonnet — Haiku was measured misreading
names three different ways for one card and getting a power stat wrong, and this
pipeline treats a confident wrong read as worse than none.

But most API traffic during a match is not reading stats, it is answering "what
screen is this" — a five-way choice with no fine text. That is the cheap
question, and if Haiku answers it as reliably then most of the per-turn cost
moves to the cheap model while the accuracy-critical read does not.

Frames are replayed by patching game_capture.grab(), which is possible only
because every capture in the codebase now goes through that one function.
"""

import glob
import os
import sys
import time


def run(n=6, log=print):
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    from PIL import Image
    import game_capture
    import orchestrator as orch

    # A LABELLED set, so this measures accuracy rather than agreement. The
    # earlier version compared the two models against each other on frames that
    # were all the same screen type, which cannot distinguish "both right" from
    # "both wrong" and had no turn screens in it at all.
    frames = sorted(glob.glob("test_fixtures/screens/*.jpg"))
    picks = frames[:n] if n else frames
    log(f"  {len(picks)} labelled frames, {2 * len(picks)} API calls\n")

    real_grab = game_capture.grab
    agree = 0
    correct = {"sonnet": 0, "haiku": 0}
    times = {"sonnet": [], "haiku": []}
    rows = []
    for f in picks:
        img = Image.open(f).convert("RGB")
        game_capture.grab = lambda width=None, _i=img: (
            _i if not width or _i.width == width
            else _i.resize((width, int(_i.height * width / _i.width))))
        got = {}
        try:
            for label, model in (("sonnet", "claude-sonnet-5"),
                                 ("haiku", "claude-haiku-4-5-20251001")):
                old = orch.MODEL
                orch.MODEL = model
                t0 = time.time()
                try:
                    st = orch.read_game_state()
                    got[label] = st.get("screen")
                except Exception as exc:
                    got[label] = f"error:{type(exc).__name__}"
                finally:
                    orch.MODEL = old
                times[label].append(time.time() - t0)
        finally:
            game_capture.grab = real_grab
        truth = os.path.basename(f).split("__")[0]
        s_ok = got.get("sonnet") == truth
        h_ok = got.get("haiku") == truth
        correct["sonnet"] += s_ok
        correct["haiku"] += h_ok
        agree += got.get("sonnet") == got.get("haiku")
        rows.append((truth, got.get("sonnet"), got.get("haiku")))
        log(f"  {truth:20} sonnet={got.get('sonnet')!s:20}{'ok' if s_ok else 'WRONG':6}"
            f" haiku={got.get('haiku')!s:20}{'ok' if h_ok else 'WRONG'}")

    done = len(rows)
    if done:
        log(f"\n  --- {done} labelled frames ---")
        for k in ("sonnet", "haiku"):
            log(f"    {k:7} correct {correct[k]}/{done} "
                f"({100.0 * correct[k] / done:.0f}%)  "
                f"mean {sum(times[k]) / len(times[k]):.1f}s")
        log(f"    models agreed with each other on {agree}/{done}")
        log("\n  VERDICT: " + (
            "Haiku matches Sonnet's accuracy — move classification to it."
            if correct["haiku"] >= correct["sonnet"] and correct["haiku"] == done
            else f"Haiku {correct['haiku']}/{done} vs Sonnet "
                 f"{correct['sonnet']}/{done}. Classification decides which key "
                 "is pressed, so a wrong screen is a wrong keypress into a live "
                 "match."))


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
