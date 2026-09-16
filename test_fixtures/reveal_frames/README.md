# Reveal frames — 23 captures of one match's reveals, at native 1920x1080

MOVED HERE FROM `agent_progress/base-timing/reveal/` ON 2026-09-17, because two
tests had come to depend on them there and **CLAUDE.md says of that directory:
"agent_progress/ is gitignored and safe to delete wholesale."** A test whose corpus
lives somewhere documented as disposable is one tidy-up away from silently losing
its evidence — and CLAUDE.md already records that exact failure in another form:
`test_map_admit` globbed `overnight/failframes/*.jpg`, a live run appended 165
frames to it, and a pinned profile went 15 -> 9 with no code change.

WHAT THEY ARE USED FOR, and each is a measurement that would be expensive to retake:

    test_scoreboard_populations.py   ocr_scoreboard reads BOTH rows on 33 of 33
                                     frames where a scoreboard is drawn -- the
                                     population that showed the failure is
                                     RESULT-screen-only, not general
    test_round5_fixes.py             r_001099.jpg is the frame where _discs returned
                                     (1019, 781) AND (1020, 781): the same disc at
                                     two DARK_THRESHOLDS, one pixel apart, straddling
                                     the old `x // 20` bucket edge. It is the only
                                     frame on disk that reproduces it.
    test_reveal_readers_scale.py     r_002387 and r_005783 are the HELD-OUT positives
                                     (copied separately into reveal_banner/); the
                                     rest are the negative population

THE SOURCES ARE STILL IN agent_progress/ and may be deleted freely; these are the
copies the suite reads. Do not point a test back at the originals.
