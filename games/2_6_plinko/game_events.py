"""Event emitters for Plinko (2_6).

Per-round event order (matches the reference RGS book):
    gameSetup -> dropBatch -> finalWin

Conventions:
  * `payoutCells` and each drop's `payoutMultiplier` are **raw multiplier floats**
    (the contract the frontend reads: 0.1, 2.5, 970, ...), NOT cents.
  * `maxWin` is the largest achievable round multiplier = edge * dropCount (raw).
  * `finalWin.amount` is in the integer "cents" scale (multiplier*100) the client
    uses for money; `finalWin.multiplier` is the raw round multiplier. (The engine's
    authoritative book payout — used for the LUT hash — is the book's cents-scaled
    `payoutMultiplier`, set by update_final_win; these events are descriptive.)
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def game_setup_event(
    gamestate,
    cost_multiplier: int,
    difficulty: str,
    drop_count: int,
    max_win: float,
    payout_cells: list,
    product_mode: str,
    rows: int,
) -> None:
    """Announce the board for the round (bins + their payout multipliers)."""
    event = {
        "index": len(gamestate.book.events),
        "type": "gameSetup",
        "costMultiplier": cost_multiplier,
        "difficulty": difficulty,
        "dropCount": drop_count,
        "maxWin": max_win,
        "payoutCells": list(payout_cells),
        "productMode": product_mode,
        "rows": rows,
    }
    gamestate.book.add_event(event)


def drop_batch_event(gamestate, drops: list) -> None:
    """Report where every dropped ball landed (one drop for the base product)."""
    event = {
        "index": len(gamestate.book.events),
        "type": "dropBatch",
        "drops": list(drops),
    }
    gamestate.book.add_event(event)


def plinko_final_win_event(gamestate, amount: int, multiplier: float) -> None:
    """Close the round with the total win (cents) and its raw multiplier."""
    event = {
        "index": len(gamestate.book.events),
        "type": "finalWin",
        "amount": amount,
        "multiplier": multiplier,
    }
    gamestate.book.add_event(event)
