"""Event emitters for Trading Roulette (2_9).

Per-round book = ONE board round (a zone win/lose bet at a fixed multiplier). Event
order:

    lose (all modes)      : zoneRound -> finalWin
    win  (20 lower cells) : zoneRound -> finalWin
    win  (zone_line)      : zoneRound -> wincap -> finalWin

`wincap` and `finalWin` are emitted for free by the base engine; only the exact-line
cell's payout reaches the global 21x cap, so only it emits `wincap` (see game_config's
"Global wincap" section).

Like the sibling `2_8_market_crash` — and unlike `2_7_prediction_market`, whose chart
direction is synthesized client-side — the visual outcome here is CERTIFIED: `landRow` is
in the book and the frontend animation is obliged to land the line in that row exactly.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def zone_round_event(
    gamestate,
    is_win: bool,
    zone_id: str,
    land_row: int,
    payout_cents: int,
    win_chance: float,
) -> None:
    """Report the round outcome and the certified landing row.

    Units: `payoutMultiplier` is INTEGER HUNDREDTHS (400 == 4.00x) and equals the cell's
    multiplier on offer — present whether the round wins or loses, matching the
    `crashRound` / `priceCall` / `cellCall` convention. `winChance` alone is a probability
    in [0, 1]. `result` is capitalized ("Win"/"Lose") to match the same.

    `landRow` is the SIGNED INTEGER row the line crosses at the right edge: 0 exactly on
    the start line, +1..+6 the fine rows over (nearest..farthest), -1..-6 under, +/-7 the
    off-scale tails. `zone` is the bet cell's id (the mode name minus the `zone_` prefix);
    the row is in the cell's zone if and only if the round wins. It is generated seeded
    and verdict-consistent (see game_executables) so a `/bet/replay` of the same book
    always shows the same landing, and it is presentation + fairness data only — the
    published odds derive from the lookup table and are unaffected by it
    (`build_odds_bundle.py` asserts this mechanically).
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "zoneRound",
        "result": "Win" if is_win else "Lose",
        "isWin": is_win,
        "zone": zone_id,
        "landRow": land_row,
        "payoutMultiplier": payout_cents,
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
