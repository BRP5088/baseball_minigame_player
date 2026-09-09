"""patch73 -- REVEAL_MAX_WAIT 75s -> 15s. It was set from the wrong quantity.

THE COST. Over the 2026-09-09 measured cycle (3,037 s of play), waiting for a reveal that
never came was 1,650 s -- 54% OF THE WHOLE RUN -- against 457 s (15%) for every paid vision
call put together. Twenty-two turns each sat for the full 75 s.

THE CONSTANT WAS SET FROM TURN PERIOD, WHICH IS A DIFFERENT POPULATION. Its comment reasons
from "turn period p50 32s p75 59s p90 83s" and concludes 75 "buys the 45->75 band for
nothing on any turn that works ... only a turn with no reveal coming pays the extra". Two
things are wrong with that. The quantity that decides this wait is not how long a TURN
takes, it is how long AFTER THE PLAY the reveal appears. And the population it dismisses is
not rare: 67 of 139 plays on disk have no reveal at all.

THE RIGHT QUANTITY, pooled over every log on disk -- 4 logs, 72 real reveals:

    t_first after the play   min 0.90   p50 3.80   p95 5.80   p99 7.90   MAX 7.90
    1s bins                  0-1:1  1-2:2  2-3:7  3-4:32  4-5:18  5-6:9  7-8:3
    reveals that never came  67

Nothing above 7.9 s in 72 samples, and the two populations do not overlap -- one arrives
inside 8 s, the other never arrives. 15.0 is 1.9x the observed maximum.

WHAT IT SAVES, on the run it was measured from: 22 x 60 s = 1,320 s, 43% of the run, and
zero of the 72 real reveals would have been lost.

WHAT IS NOT FIXED HERE: why 48% of plays produce no reveal at all. That is a separate
question and it is the reason the misfire check misses those turns; this patch only stops
paying 75 s to discover it.
"""
import io

P = "orchestrator.py"
s = io.open(P, encoding="utf-8").read()

OLD = """# 75 buys the 45->75 band for nothing on any turn that works: this returns the
# instant the reveal is seen, and a reveal stays up 6s (p50), far longer than
# the 0.25s poll. Only a turn with no reveal coming pays the extra, and those
# were already paying 45s to fail. Not pushed to 90: the last 12 points of
# coverage cost every failing turn another 15s, and a turn period that long is
# more likely a stall than a slow deal.
REVEAL_MAX_WAIT = 75.0"""
assert s.count(OLD) == 1, f"anchor x{s.count(OLD)}"

NEW = """# THE REASONING ABOVE IS THE WRONG QUANTITY, and it cost 54% of a measured run.
#
# Turn PERIOD does not decide this wait. What decides it is how long AFTER THE PLAY the
# reveal appears -- and that is a different, much tighter distribution. Pooled over every
# log on disk, 4 logs, 72 real reveals:
#
#     t_first after the play   min 0.90   p50 3.80   p95 5.80   p99 7.90   MAX 7.90
#     1s bins                  0-1:1  1-2:2  2-3:7  3-4:32  4-5:18  5-6:9  7-8:3
#
# The other half of the sentence above is false too. "Only a turn with no reveal coming
# pays the extra" treats that as an edge case; it is 67 of 139 plays on disk. On the
# 2026-09-09 cycle those 22 turns cost 1,650 s -- 54% OF THE WHOLE RUN, against 457 s (15%)
# for every paid vision call put together.
#
# So the two populations are: a reveal that is coming, which has always arrived inside
# 7.9 s, and one that is not, which never arrives at any budget. 15.0 is 1.9x the observed
# maximum and loses none of the 72. It saves 60 s on every turn with no reveal.
REVEAL_MAX_WAIT = 15.0"""

io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
print("REVEAL_MAX_WAIT 75.0 -> 15.0")
