"""Event emitters for Chart Race (2_11).

Per-round book = ONE certified 3-line race outcome. Event order:

    loss : raceResult -> finalWin
    win  : raceResult -> wincap -> finalWin

`wincap` and `finalWin` are emitted by the base engine; both markets' win payout equals
the global cap, so EVERY winning book carries `wincap`. Books are PICK-NEUTRAL: racers
are r0..r2 where r0 is always the player's picked company; the client maps the pick onto
r0 at render time (see game_config's module docstring).

There is no rank timeline (contrast 3_0_boat_race): the chart is continuous, so the book
certifies the finishing ORDER only and the frontend draws seeded cosmetic paths obliged
to arrive at exactly that order at the settlement line.

Units: `payoutMultiplier` and the engine's `wincap`/`finalWin` amounts are INTEGER
HUNDREDTHS (300 == 3.00x); `winChance` alone is a probability. `result` is capitalized
"Win"/"Lose" alongside the boolean `isWin`, and `payoutMultiplier` is present win or
lose — the crashRound/priceCall/zoneRound convention.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def race_result_event(
    gamestate,
    is_win: bool,
    player_place: int,
    finish_order: list,
    payout_cents: int,
    win_chance: float,
) -> None:
    """Report the certified result: r0's place, the full finishing order, the payout.

    `finishOrder` is a permutation of racer ids [0, 1, 2] indexed by place — element 0
    is the racer that finishes HIGHEST, element 2 the racer that finishes LOWEST.
    `playerPlace` is r0's 1-based place and always equals finishOrder.index(0) + 1.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "raceResult",
        "result": "Win" if is_win else "Lose",
        "isWin": is_win,
        "playerPlace": player_place,
        "finishOrder": list(finish_order),
        "payoutMultiplier": payout_cents,
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
