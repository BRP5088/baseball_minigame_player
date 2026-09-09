"""The per-run EVENT LOG: when each capture, press, read and reveal episode happened and
which dump frame it saw. Joined on `seq` with a tools/record_stream.py recording's
frames.jsonl, it lets an agent open the exact frame a read used.

Enabled by BASEBALL_EVENT_LOG=<path> (read at CALL time, CLAUDE.md 10.18); every call is
a no-op otherwise. Writes are appends of one JSON line; a failed write never raises.
"""
import json
import os
import time


def path(env=None):
    return (os.environ if env is None else env).get("BASEBALL_EVENT_LOG") or None


def _dump_seq():
    """The dump's current seq and monotonic stamp, or (None, None). Under
    BASEBALL_TEST_RUN frame_dump refuses the rig's file, so this is None there."""
    try:
        import frame_dump
        s = frame_dump.stats()
        return (s or {}).get("seq"), (s or {}).get("mono_ns")
    except Exception:
        return None, None


def log_event(kind, **fields):
    """Append one row. Returns True when a row was written."""
    p = path()
    if not p:
        return False
    seq, mono = _dump_seq()
    row = {"t": round(time.time(), 4), "kind": kind, "seq": seq, "dump_mono_ns": mono}
    row.update(fields)
    try:
        with open(p, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        return True
    except OSError:
        return False


def log_regions():
    """The crop tables, once per run: where every read looks, as fractions of the frame."""
    try:
        import orchestrator as o
        import table_prompt as tp
        return log_event("regions",
                         gameplay=o.GAMEPLAY_REGIONS_FRAC,
                         reveal_centre=list(o.REVEAL_CENTER_REGION),
                         ban_cols=o.BAN_GRID_COL_X_FRAC, ban_rows=o.BAN_GRID_ROW_Y_FRAC,
                         prompt_text_box=list(tp.TEXT_BOX),
                         settle_width=o.SETTLE_CALIBRATION_WIDTH,
                         screenshot_max_width=o.SCREENSHOT_MAX_WIDTH,
                         reveal_threshold=o.REVEAL_EDGE_THRESHOLD)
    except Exception as e:
        return log_event("regions", error=repr(e))


def caller_name(depth=2):
    import sys
    try:
        return sys._getframe(depth).f_code.co_name
    except Exception:
        return None
