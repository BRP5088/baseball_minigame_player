"""The reveal banner reader: HOME RUN! and PLAY BALL!, and what it must refuse.

The game PRINTS the outcome, so a home run need not be inferred from a margin --
which needs both cards read, and on 2026-09-16 a sampler that spent its budget on
the diamond could not say whether a hit was a tie or a fielding subtraction.

Plain asserts: this suite has four incompatible check() signatures and a reversed
call to a name-first one prints "PASS True" and can never fail.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import reveal_banner as rb

# FIXTURES LIVE IN test_fixtures/, NOT agent_progress/. That directory is
# gitignored and "safe to delete wholesale" by its own README, and CLAUDE.md
# records a test whose population came from a live-run directory silently
# changing when a run appended to it.
FR = os.path.join(_ROOT, "test_fixtures/reveal_banner")
fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


def frame(n):
    p = os.path.join(FR, f"{n}.jpg")
    return Image.open(p) if os.path.exists(p) else None


hr, pb, neg = frame("home_run"), frame("play_ball"), frame("turn_no_banner")
want("the fixture frames are present", all(x is not None for x in (hr, pb, neg)),
     f"missing under {FR} -- this test cannot bite without them")

if hr is not None:
    lab, det = rb.read_banner(hr)
    want("HOME RUN! is read", lab == "home_run", det)
    lab, det = rb.read_banner(pb)
    want("PLAY BALL! is read", lab == "play_ball", det)
    lab, det = rb.read_banner(neg)
    want("a plain turn frame is refused", lab is None, det)

    # THE TWO WORDS MUST NOT BE CONFUSABLE. They are different widths (328 vs
    # 578), and CLAUDE.md 30 records that stretching both to one box made WINNER
    # and LOSER score alike -- so this pins that they stayed native.
    s = rb.scores(hr)
    want("HOME RUN! does not score as PLAY BALL!",
         s["home_run"] - s["play_ball"] > 0.5, str(s))
    s = rb.scores(pb)
    want("PLAY BALL! does not score as HOME RUN!",
         s["play_ball"] - s["home_run"] > 0.5, str(s))

# THE GATE IS PINNED AS A LITERAL so raising the constant cannot make its own
# guard pass (CLAUDE.md 10.11). Measured: non-banner MAX 0.589 over 6,833 frames
# from three other sessions; settled banners >= 0.80.
want("the gate sits between the measured populations",
     0.60 <= rb.BANNER_MIN <= 0.99,
     f"non-banner MAX is 0.589 and settled banners reach 0.995 -- got {rb.BANNER_MIN}")
want("and it clears the non-banner maximum", rb.BANNER_MIN > 0.589)

# A CROP MUST BE REFUSED, NOT SILENTLY RESIZED. Handed one, matchTemplate would
# either raise or return a number anyway -- 10.1's success-and-no-op-alike.
try:
    rb.scores(Image.new("RGB", (400, 300)))
    raised = False
except ValueError:
    raised = True
want("a too-small frame raises rather than answering", raised,
     "a crop was accepted and scored")

# THE TEMPLATES ARE NATIVE SIZE AND NOT AVERAGED: one entry per example.
bank = rb._bank()
want("the bank holds one template per example, unaveraged", len(bank) >= 3,
     f"{len(bank)} templates")
want("every template clears the fragment floor",
     all(t.shape[1] >= rb.FRAGMENT_MIN_W for _l, t in bank),
     f"widths {[t.shape[1] for _l, t in bank]} -- a fragment correlates with anything")

# AND THE FLOOR BITES AT MATCH TIME, not only when the bank is built. Checking
# the STORED widths passed while a mutant truncated the templates inside
# scores() -- the check was reading the argument, not the code.
_real = rb._bank()
try:
    rb._BANK = [(l, t[:, :120]) for l, t in _real]      # every template a fragment
    lab, det = rb.read_banner(hr) if hr is not None else (None, "")
    want("a fragment template is skipped rather than matched", lab is None,
         f"a 120px fragment was matched and returned {lab!r} ({det})")
finally:
    rb._BANK = _real

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
