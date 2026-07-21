"""Event emitters for Kong Climb (2_4)."""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def dice_result_event(
    gamestate,
    direction: str,
    target: float,
    win_chance: float,
    is_win: bool,
    multiplier: float,
    roll: float,
) -> None:
    """Reveal the dice outcome for one round.

    `payoutMultiplier` is the multiplier *on offer* for this mode (present whether
    the round wins or loses), emitted in the integer "cents" scale (×100) the
    client uses for every win amount. `target` is the slider threshold (the
    integer NN in the mode name) and `winChance` the integer win percentage.

    `roll` is the displayed dice result on the 00.00–100.00 scale (2 decimals),
    generated seeded/reproducibly and always consistent with `isWin`: for
    `over_NN` a win rolls > NN and a loss rolls ≤ NN; for `under_NN` a win rolls
    < NN and a loss rolls ≥ NN. It is stored in the book so a replay is stable and
    the number shown matches the RGS-selected result (the seed pair selects the
    book; this roll is that book's certified outcome).
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "diceResult",
        "direction": direction,
        "target": target,
        "winChance": win_chance,
        "isWin": is_win,
        "payoutMultiplier": int(round(multiplier * 100, 0)),
        "roll": round(roll, 2),
    }
    gamestate.book.add_event(event)
