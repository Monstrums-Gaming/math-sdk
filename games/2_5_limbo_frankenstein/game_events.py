"""Event emitters for Limbo Frankenstein (2_5)."""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def limbo_win_info_event(
    gamestate,
    is_win: bool,
    offered_multiplier: float,
    win_amount: float,
    target: float,
    win_chance: float,
) -> None:
    """Reveal the Limbo outcome for one round (matches the reference `winInfo` shape).

    `payoutMultiplier` is the multiplier on offer for this mode (= the LUT win
    payout W = target*cost), present whether the round wins or loses, in the
    integer "cents" scale (×100) the client uses for every amount. `totalWin` is
    the amount actually won (W on a win, 0 on a loss). `target` and `winChance`
    (probability) are included for the frontend replay.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "winInfo",
        "isWin": is_win,
        "payoutMultiplier": int(round(offered_multiplier * 100, 0)),
        "totalWin": int(round(win_amount * 100, 0)),
        "target": target,
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
