"""Event emitters for Candle Bet (2_10).

Per-round book = ONE UP/DOWN call. Event order: `priceCall` -> `finalWin`.

The book is DIRECTION-NEUTRAL: UP and DOWN have identical odds, so it encodes only
win/lose (and the offered multiplier). The frontend derives which way the BTC chart
finishes from the player's chosen side + `isWin`:  candleUp = (pickedUp == isWin).
`finalWin` is emitted for free by the base engine (evaluate_finalwin).
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def price_call_event(
    gamestate,
    is_win: bool,
    multiplier: float,
    win_chance: float,
) -> None:
    """Report the single call outcome.

    `payoutMultiplier` is the multiplier on offer (present whether the call wins or
    loses), in the integer "cents" scale (×100) the client uses for every amount.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "priceCall",
        "result": "Win" if is_win else "Lose",
        "isWin": is_win,
        "payoutMultiplier": int(round(multiplier * 100, 0)),
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
