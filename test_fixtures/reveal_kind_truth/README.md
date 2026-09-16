# reveal_kind_truth — ground truth for the tactics-KIND reader

48 reveal frames whose played card is KNOWN, because we played it:

    reveal6/f_*.jpg   25 frames   we PITCHED a fielding boost; they BATTED a speed boost
    reveal/r_*.jpg    23 frames   we BATTED a power swing;     they PITCHED a pitch focus

WHY THEY LIVE HERE. These are the only frames that can re-measure
`reveal_cards.TACTICS_KIND_MIN` (0.75), a shipped gate, and the only source the
shipped template banks are cut from. They sat in `agent_progress/base-timing/`
until 2026-09-17 -- gitignored, untracked, and named by CLAUDE.md as "safe to
delete wholesale". Nothing would have failed when they went; the gate would
simply have become unmeasurable and the banks unbuildable.

FIVE OF THEM SUPPLIED TEMPLATES and must stay excluded from any scoring run --
a template matches its own source at 1.000 (CLAUDE.md 10.30):

    f_001503.jpg  f_002645.jpg  f_003571.jpg  r_003660.jpg  r_006285.jpg

`tools/banner_kind_census.py` holds that exclusion list and scores the rest.
`tools/base_timing.py` still WRITES new captures to `agent_progress/base-timing/`;
that is scratch, and this is the kept copy.
