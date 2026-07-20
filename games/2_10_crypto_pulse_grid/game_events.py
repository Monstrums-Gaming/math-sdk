"""Event emitters for Crypto Pulse Grid (2_10).

Per-round book = ONE chip (a tap-cell win/lose bet at a fixed multiplier). Event
order: `cellCall` -> (`wincap` on a win, emitted by the base engine) -> `finalWin`.

The book is POSITION-NEUTRAL: the tapped cell (its row/column on the grid) is pure
client-side presentation, so the book encodes only win/lose and the offered
multiplier. The frontend steers the price line to hit or miss the tapped cell from
the player's tap + `isWin`. `finalWin` is emitted for free by the base engine
(evaluate_finalwin) and carries `amount` only (no float multiplier).
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def cell_call_event(
    gamestate,
    is_win: bool,
    multiplier: float,
    win_chance: float,
) -> None:
    """Report the single chip outcome.

    `payoutMultiplier` is the multiplier on offer (present whether the chip wins or
    loses), in the integer "cents" scale (x100) the client uses for every amount.
    `result` is capitalized ("Win"/"Lose") to match the 2_9 priceCall convention.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "cellCall",
        "result": "Win" if is_win else "Lose",
        "isWin": is_win,
        "payoutMultiplier": int(round(multiplier * 100, 0)),
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
