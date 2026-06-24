"""Event emitters for Cash Paradise (3_2)."""

from src.events.events import *


def mystery_reveal_event(gamestate, symbol: str, prize_name: str, payout: float) -> None:
    """Reveal the single prize won when the box is opened.

    `payout` is the RGS multiplier (base-bet units); it is emitted in the same
    integer "cents" scale (x100) the client uses for every other win amount.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "mysteryReveal",
        "prize": symbol,
        "prizeName": prize_name,
        "amount": int(round(min(payout, gamestate.config.wincap) * 100, 0)),
    }
    gamestate.book.add_event(event)
