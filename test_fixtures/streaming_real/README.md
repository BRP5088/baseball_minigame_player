# 260 real streaming frames — the NEGATIVE population for streaming()

Copied 2026-09-17 from the four directories this test used to glob live:
demos/ (80), screenshot_log/ (80), explore/ (60), overnight/ (40). The source
directory is kept in each filename, so provenance survives the flattening.

TWO REASONS THEY HAD TO MOVE, and the second is the serious one.

1. demos/, screenshot_log/ and explore/ are GITIGNORED. The population did not
   exist on a fresh clone, so the check could not run for anyone else.

2. overnight/ IS WRITTEN BY LIVE RUNS, so the population CHANGED UNDER THE TEST.
   CLAUDE.md records this precise failure in another file: "test_map_admit fed
   overnight/failframes/*.jpg to admit() as its failure population; the 2026-09-06
   streak runs appended 165 leg-end frames there and G5's pinned profile went
   15 -> 9 with no code change." A false-positive RATE is only meaningful against a
   population that holds still.

WHAT THEY PROVE: streaming() must not reject a real stream. They include match play
from screenshot_log -- ban grids and gameplay, where no compass exists -- so a
compass-shaped discriminator fails here rather than passing on walk frames alone.
