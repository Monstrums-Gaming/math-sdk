"""Event emitters for Chicken Crossing (2_7).

Per-round event order (the book contract with the frontend):
    crossingSetup -> crossingResult -> finalWin

Conventions:
  * `ladder` and `payoutMultiplier` are **raw multiplier floats** (snapped onto the
    0.1x grid: 1.0, 1.1, 24.2, 1055.8, ...), NOT cents.
  * `maxWin` is the mode's top achievable multiplier (the last rung of the ladder).
  * `cashOutStep` (win) / `poppedAtStep` (loss) are 0-based step indices; the other
    is null. The book PREDETERMINES the outcome — the cash-out step is not chosen by
    the player at runtime (see readme.txt warning #1).
  * `finalWin.amount` is the integer "cents" scale (multiplier*100) the client uses
    for money; `finalWin.multiplier` is the raw round multiplier. (The engine's
    authoritative book payout used for the LUT hash is set by update_final_win;
    these events are descriptive replay data.)
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def crossing_setup_event(
    gamestate,
    difficulty: str,
    cost_multiplier: int,
    num_steps: int,
    ladder: list,
    max_win: float,
) -> None:
    """Announce the difficulty ladder for the round (multiplier per crossable step)."""
    event = {
        "index": len(gamestate.book.events),
        "type": "crossingSetup",
        "difficulty": difficulty,
        "costMultiplier": cost_multiplier,
        "numSteps": num_steps,
        "ladder": list(ladder),
        "maxWin": max_win,
        "productMode": "base",
    }
    gamestate.book.add_event(event)


def crossing_result_event(
    gamestate,
    difficulty: str,
    is_win: bool,
    cash_out_step,
    popped_at_step,
    payout_multiplier: float,
) -> None:
    """Report the predetermined outcome: cash out at a step, or pop at a step."""
    event = {
        "index": len(gamestate.book.events),
        "type": "crossingResult",
        "difficulty": difficulty,
        "isWin": is_win,
        "cashOutStep": cash_out_step,    # int on win, else None
        "poppedAtStep": popped_at_step,  # int on loss, else None
        "payoutMultiplier": payout_multiplier,
    }
    gamestate.book.add_event(event)


def crossing_final_win_event(gamestate, amount: int, multiplier: float) -> None:
    """Close the round with the total win (cents) and its raw multiplier."""
    event = {
        "index": len(gamestate.book.events),
        "type": "finalWin",
        "amount": amount,
        "multiplier": multiplier,
    }
    gamestate.book.add_event(event)
