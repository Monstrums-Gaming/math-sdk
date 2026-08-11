"""Event emitters for Boat Race (3_0).

Per-round book = ONE certified 4-boat race. Event order:

    place 2/3 (paid)   : raceSetup -> raceRun -> raceResult -> finalWin
    place 4   (unpaid) : raceSetup -> raceRun -> raceResult -> finalWin
    place 1   (3.00x)  : raceSetup -> raceRun -> raceResult -> wincap -> finalWin

`wincap` and `finalWin` are emitted by the base engine. Books are PICK-NEUTRAL: the
transcript addresses racers r0..r3 where r0 is always the player's chosen boat; the
client maps the pick onto r0 at render time (see game_config's module docstring).

Units: `payoutMultiplier`, `payoutLadder` entries and the engine's `wincap`/`finalWin`
amounts are INTEGER HUNDREDTHS (300 == 3.00x); `winChance` alone is a probability.
`result` is capitalized "Win"/"Lose" alongside the boolean `isWin`, and
`payoutMultiplier` is present win or lose — the crashRound/priceCall convention.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def race_setup_event(gamestate, params: dict) -> None:
    """Announce the race parameters and the Win/Place payout ladder."""
    event = {
        "index": len(gamestate.book.events),
        "type": "raceSetup",
        "numBoats": params["num_boats"],
        "laps": params["laps"],
        "gates": params["gates"],
        "costMultiplier": 1.0,
        "payoutLadder": list(params["payout_ladder_cents"]),
        "maxWin": float(gamestate.config.wincap),
        "productMode": "base",
    }
    gamestate.book.add_event(event)


def race_run_event(gamestate, ranks: list) -> None:
    """The certified rank timeline — one row per gate segment.

    `fieldOrder` + fixed-order int arrays (the porkageddon compression idiom):
    row = [segment, rank of r0, rank of r1, rank of r2, rank of r3], ranks 1..4.
    Rows change only by adjacent-rank swaps and the final row equals the ranks implied
    by raceResult.finishOrder (asserted at generation AND by verify_books.py).
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "raceRun",
        "fieldOrder": ["seg", "r0", "r1", "r2", "r3"],
        "ranks": ranks,
    }
    gamestate.book.add_event(event)


def race_result_event(
    gamestate,
    is_win: bool,
    player_place: int,
    finish_order: list,
    payout_cents: int,
    win_chance: float,
) -> None:
    """Report the certified result: r0's place, the full finishing order, the payout."""
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
