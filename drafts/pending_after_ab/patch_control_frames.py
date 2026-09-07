"""graph_walk: both control frames on both outcomes. APPLY ONLY WHEN NO LIVE RUN IMPORTS graph_walk."""
p = "graph_walk.py"; s = open(p).read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:70]); s = s.replace(old, new)
rep('''        # ...and it must be the frame follow() published at the leg's END. It
        # was `before` until 2026-09-07 — the capture taken before the whole
        # attempt, i.e. the PREVIOUS node's arrival: both ok_dealer_table
        # frames from OPEN-14 read bearing 0.8 and identified bar_jukebox at
        # 491 and 295 matches. The comment eight lines up already names that
        # trap for failures; the success path had walked into it anyway.
        end = _LAST_LEG_END.get(node)
        if shots and ok and end is not None:
            try:
                _save_shot(os.path.join(shots, "success"), f"ok_{node}", end)
            except Exception:
                pass                        # bookkeeping must never end a run
''', '''        # TWO CONTROL FRAMES, because two different questions need them.
        #   start_<node>  the pose the attempt began from (`before`). This is
        #                 the control tests/routing/test_success_control_frames.py
        #                 was written for: start-pose spread of arrivals against
        #                 start-pose spread of failures (§8(i)). Written on BOTH
        #                 outcomes (the failure side is below), so the
        #                 comparison has both groups.
        #   ok_<node>     the frame follow() published at the leg's END, the
        #                 twin of fail_<node>, which has been the leg end since
        #                 OPEN-1. Until 2026-09-07 this slot held `before` under
        #                 the name ok_, deliberately (the start-pose control) —
        #                 and a leg-end census therefore had no arrivals to
        #                 compare against: both OPEN-14 ok_dealer_table frames
        #                 identified bar_jukebox. For a few hours on 2026-09-07
        #                 it held ONLY the leg end, which threw the start-pose
        #                 control away; the test caught that.
        if shots and ok:
            try:
                _d = os.path.join(shots, "success")
                if before is not None:
                    _save_shot(_d, f"start_{node}", before)
                end = _LAST_LEG_END.get(node)
                if end is not None:
                    _save_shot(_d, f"ok_{node}", end)
            except Exception:
                pass                        # bookkeeping must never end a run
''')
rep('''            if shots and img is not None:
                try:
                    import os as _os
                    _os.makedirs(shots, exist_ok=True)
''', '''            # The start pose of a FAILED attempt: the other half of the
            # start-pose control (see the success path above).
            if shots and before is not None and before is not img:
                try:
                    _save_shot(shots, f"start_{node}", before)
                except Exception:
                    pass
            if shots and img is not None:
                try:
                    import os as _os
                    _os.makedirs(shots, exist_ok=True)
''')
open(p, "w").write(s); print("patched graph_walk.py (control frames)")
