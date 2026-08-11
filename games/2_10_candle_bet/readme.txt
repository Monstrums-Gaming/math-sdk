Candle Bet (2_10) — bet on the next candle (direction + size)
==============================================================

Forked 2026-08-11 from 2_7_prediction_market (same engine and book contract) so
Candle Bet publishes as its own game. Pairs with web apps/2-10-candle-bet.

Mechanic
--------
The player picks a CANDLE SIZE (ANY / BIG / HUGE) and calls UP or DOWN, then bets.
The next candle of a live candlestick chart forms and settles on its close vs its
open; on BIG/HUGE the close must also clear a marked target line. The round WINS
the offered multiplier if the certified verdict lands the player's way, otherwise
pays 0. There is no board, no reels and no free-spin round.

This is a direct-probability game (like games/mystery_box and the dice / limbo /
chicken games): the odds are authored in game_config.py and the Rust optimiser is
disabled. Published odds equal the per-criteria book counts.

The chart does NOT use real market prices — the frontend renders a candle
consistent with the returned win/lose verdict (direction from the pick, magnitude
from the size tier); thresholds and the target line are client presentation. The countdown timer,
"online" count, live-bets feed and "watch ad" chrome in the mockup are pure frontend
presentation and have no bearing on the math.

Direction-neutral book (why direction is not a mode)
----------------------------------------------------
UP and DOWN are SYMMETRIC — identical odds. So from the book's point of view the
direction is cosmetic: each round's book encodes only win/lose and the offered
multiplier. The frontend derives which way the chart finishes from the player's
chosen side plus isWin:

    candleUp = (pickedUp == isWin)
      picked UP,   win  -> candle UP      picked UP,   lose -> candle DOWN
      picked DOWN, win  -> candle DOWN    picked DOWN, lose -> candle UP

Direction is therefore never a published mode — each size-tier mode serves both
buttons. The bet chips ($10/$50/$100/MAX) are ACP BET LEVELS (dashboard template),
also not published modes.

Candle-size ladder (multipliers, grid + RTP)
--------------------------------------------
Three size tiers are published, one mode each (mode keys unchanged from the parent
2_7 game so the web tier mapping carries over; the parent's 1.40x rung is dropped —
no honest candle-size rule yields a 68.75% win chance). Every multiplier is a
multiple of 0.10 (the ACP 0.1x grid). For each multiplier M the win probability is
the smallest-denominator rational a/b whose realised RTP (a/b)*M lands in
[96.00%, 96.70%] (game_config.py::_simplest_fraction_in, the limbo/chicken
Stern-Brocot descent); num_sims = b yields exactly a winning books, so published
odds equal the book counts.

    Size   Multiplier  Mode name    Win chance      RTP
    ANY     2.00x      call_200     12/25 (48.00%)  96.00%
    BIG     5.00x      call_500      5/26 (19.23%)  96.15%
    HUGE   10.00x      call_1000     5/52 ( 9.62%)  96.15%

wincap = 10.00 (the top payout). The tiers live in _MULTIPLIERS in game_config.py —
add/remove entries there and everything (modes, num_sims, wincap, configs)
regenerates.

ACP math rules (enforced server-side)
-------------------------------------
  1. 0.1x LUT grid: every payout (200/500/1000 cents) is a multiple of 10.
     lut_grid_exempt = False keeps the SDK grid check ON as a regression guard.
  2. RTP band (per-mode): each mode's RTP is pinned into [96.00%, 96.70%].
  3. RTP consistency (cross-mode): all modes share the same pin, so the spread is
     <= 1.00% (game_config.py::_validate asserts it).
  4. Risk / star-rating (Max Payout, Tail Probability, ETL, CVaR, Std Dev): the game is
     rated off its tamest mode — the lowest tier 2.00x has payout std ~0.999 (>= the
     0.60 volatility floor), and the highest tier 10.00x is far under the ~100x
     all-or-nothing ceiling that capped limbo.

Per-round events
----------------
    priceCall : {result:"Win"|"Lose", isWin, payoutMultiplier(cents = mult*100),
                 winChance(probability)}   (direction-neutral; emitted every round)
    finalWin  : {amount(cents)}   (amount = mult*100 on a win, else 0; base engine)

Build
-----
Dev (readable books):
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_10_candle_bet/run.py
Production (compressed + format-checked):
    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_10_candle_bet/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels (the bet-chip amounts)
and gameID are set in ACP, not here. provider_number is a placeholder (2) pending
the ACP-assigned value.

A standalone frontend_demo/ replays the published win/lose books on an animated
chart (see frontend_demo/README.md); build_demo_data.py emits candle_bet_rgs.json,
the odds bundle the web app mirrors.
