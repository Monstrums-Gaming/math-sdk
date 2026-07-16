"""Event emitters for Kong Climb (2_4)."""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def dice_result_event(
    gamestate,
    direction: str,
    target: float,
    win_chance: float,
    is_win: bool,
    multiplier: float,
) -> None:
    """Reveal the dice outcome for one round.

    `payoutMultiplier` is the multiplier *on offer* for this mode (present whether
    the round wins or loses), emitted in the integer "cents" scale (×100) the
    client uses for every win amount. `target` is the slider threshold (the
    integer NN in the mode name) and `winChance` the integer win percentage.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "diceResult",
        "direction": direction,
        "target": target,
        "winChance": win_chance,
        "isWin": is_win,
        "payoutMultiplier": int(round(multiplier * 100, 0)),
    }
    gamestate.book.add_event(event)
