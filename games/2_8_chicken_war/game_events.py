"""Event emitters for Chicken Run (2_8).

Per-round book = ONE lane wager. Event order: `outcome` -> `finalWin`. The `outcome`
event mirrors the real game's `state:[{type:"outcome", result:"Win"|"Lose", ...}]`,
plus the lane / difficulty / multiplier the frontend needs to animate the crossing.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def outcome_event(
    gamestate,
    difficulty: str,
    lane: int,
    win_chance: float,
    is_win: bool,
    multiplier: float,
) -> None:
    """Report the single lane-wager outcome. `payoutMultiplier` is the raw multiplier
    on offer for this lane (present whether the wager wins or loses)."""
    event = {
        "index": len(gamestate.book.events),
        "type": "outcome",
        "result": "Win" if is_win else "Lose",
        "difficulty": difficulty,
        "lane": lane,
        "winChance": win_chance,
        "isWin": is_win,
        "payoutMultiplier": multiplier,
    }
    gamestate.book.add_event(event)
