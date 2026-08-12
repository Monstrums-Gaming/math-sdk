"""Event emitters for Market Crash (2_8).

Per-round book = ONE index run (a SELL AT win/lose bet at a fixed multiplier). Event
order:

    lose (all modes)      : crashRound -> finalWin
    win  (29 lower rungs) : crashRound -> finalWin
    win  (crash_10000)    : crashRound -> wincap -> finalWin

`wincap` and `finalWin` are emitted for free by the base engine; only the top rung's
payout reaches the global 100x cap, so only it emits `wincap` (see game_config's
"Global wincap" section).

Unlike the sibling `2_7_prediction_market` — where the chart direction is synthesized
client-side from `endsHigh = pickedHigh == isWin` — the visual outcome here is CERTIFIED:
`crashPoint` is in the book and the frontend animation is obliged to land on it exactly.
"""

from src.events.events import *  # noqa: F401,F403  (kept for parity with other games)


def crash_round_event(
    gamestate,
    is_win: bool,
    sell_at_cents: int,
    crash_point: int,
    win_chance: float,
) -> None:
    """Report the round outcome and the certified rug multiplier.

    Units: `target`, `crashPoint` and `payoutMultiplier` are all INTEGER HUNDREDTHS
    (250 == 2.50x); `winChance` alone is a probability in [0, 1]. `payoutMultiplier` is
    the multiplier on offer and equals `target` (the target IS the mode, and the mode pays
    its target) — it is present whether the round wins or loses, matching the `priceCall`
    / `cellCall` convention. `result` is capitalized ("Win"/"Lose") to match the same.

    `crashPoint` is the multiplier at which the index rugged: `>= target` on a win,
    `< target` on a loss, floored to hundredths, never below 100 (1.00x = an instant rug),
    never above this mode's display cap. It is generated seeded and outcome-consistent
    (see game_executables) so a `/bet/replay` of the same book always shows the same rug,
    and it is presentation + fairness data only — the published odds derive from the
    lookup table and are unaffected by it (`build_odds_bundle.py` asserts this
    mechanically).
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "crashRound",
        "result": "Win" if is_win else "Lose",
        "isWin": is_win,
        "target": sell_at_cents,
        "crashPoint": crash_point,
        "payoutMultiplier": sell_at_cents,
        "winChance": win_chance,
    }
    gamestate.book.add_event(event)
