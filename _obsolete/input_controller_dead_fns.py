"""M10: navigate_grid() and select_bans_and_start() — removed from
input_controller.py 2026-08-25. Only select_bans_and_start_full() is used by
orchestrator.py; navigate_grid was used exclusively by the dead variant.
"""

def navigate_grid(from_row: int, from_col: int, to_row: int, to_col: int):
    """Move the cursor from one grid cell to another on the ban screen."""
    row_diff = to_row - from_row
    col_diff = to_col - from_col
    vertical = "move_down" if row_diff > 0 else "move_up"
    horizontal = "move_right" if col_diff > 0 else "move_left"
    for _ in range(abs(row_diff)):
        press(vertical)
    for _ in range(abs(col_diff)):
        press(horizontal)


def select_bans_and_start(grid: list, banned_names: set):
    """
    Navigate the pre-match ban screen, toggle each card whose name is in
    banned_names, then confirm to start the match.

    grid: list of (row, col, PlayerCard) tuples for every card visible
    on the ban screen, as read off the current screenshot.

    Assumptions not yet directly confirmed — worth watching on the first
    live run:
    - The cursor starts at grid position (0, 0) when this screen opens.
    - Toggling a card (Cross) doesn't move the cursor off that card.
    """
    current_row, current_col = 0, 0

    for row, col, card in grid:
        if card.name in banned_names:
            navigate_grid(current_row, current_col, row, col)
            press("select_card")
            current_row, current_col = row, col

    press("confirm_play")  # Triangle -> confirms the 3 bans and starts the match


