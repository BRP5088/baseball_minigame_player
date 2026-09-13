# ban_grid fixtures

Three ban-screen frames, NAMED not globbed, each chosen for a different failure mode of
`ban_grid.find_card_rows`:

| file | why it is here |
|---|---|
| `scroll_p00.png` | top of the grid. Card rows at 0.280 / 0.607, hand-read off a ruler. |
| `scroll_p04.png` | a DIFFERENT scroll position, rows at 0.229 / 0.557 — the rows MOVE, and a fixed fraction cannot frame both frames. |
| `tactics_row.png` | the tactics rows. Their cards carry the name at the TOP, and most are LOCKED (sd 16-19 against an owned card's 62-66), so per-row detection finds nothing here. It is the frame that forced the phase to be solved across all rows at once. |

The row tops quoted above are the ground truth in `tests/minigame/test_ban_grid.py`. They
were read off a ruler laid on the frame by hand, not produced by the code under test.
