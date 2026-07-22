"""Event emitters for Battleships (2_3) — conserved-board, per-click wager model.

Per-round book = ONE tile-click wager, priced by the board's remaining pool. Event
order: `outcome` -> `finalWin` (the base engine emits `finalWin`). The `outcome` event
carries the remaining-board state (shipsLeft / minesLeft) and the rung multiplier the
frontend needs to reveal the tile. All money on the wire is integer cents.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def outcome_event(
    gamestate,
    ships_left: int,
    mines_left: int,
    win_chance: float,
    is_win: bool,
    multiplier_cents: int,
) -> None:
    """Report the single tile-click wager outcome for state (shipsLeft, minesLeft).

    `payoutMultiplierCents` is the rarity-priced multiplier (in cents, x100) on offer at
    this remaining-board state (present on win AND lose)."""
    event = {
        "index": len(gamestate.book.events),
        "type": "outcome",
        "result": "Win" if is_win else "Lose",
        "shipsLeft": ships_left,
        "minesLeft": mines_left,
        "tilesLeft": ships_left + mines_left,
        "winChance": win_chance,
        "isWin": is_win,
        "payoutMultiplierCents": multiplier_cents,
    }
    gamestate.book.add_event(event)
