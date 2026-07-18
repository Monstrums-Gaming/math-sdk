Crypto Pulse (2_9) — Stake-style HIGH/LOW binary game
====================================================

Mechanic
--------
The player picks HIGH or LOW and a bet amount, then presses the button. A BTC/USD
chart animates for ~5-8 seconds and finishes above or below the starting line. The
round WINS the offered multiplier if the price finishes on the player's chosen side,
otherwise pays 0. There is no board, no reels and no free-spin round.

This is a direct-probability game (like games/mystery_box and the dice / limbo /
chicken games): the odds are authored in game_config.py and the Rust optimiser is
disabled. Published odds equal the per-criteria book counts.

The chart does NOT use real BTC prices — the frontend generates a realistic-looking
random-walk price path from the returned win/lose result. The countdown timer,
"online" count, live-bets feed and "watch ad" chrome in the mockup are pure frontend
presentation and have no bearing on the math.

Direction-neutral book (why there is only one mode)
---------------------------------------------------
HIGH and LOW are SYMMETRIC — identical odds. So from the book's point of view the
direction is cosmetic: each round's book encodes only win/lose and the offered
multiplier. The frontend derives which way the chart finishes from the player's
chosen side plus isWin:

    endsHigh = (pickedHigh == isWin)
      picked HIGH, win  -> ends HIGH      picked HIGH, lose -> ends LOW
      picked LOW,  win  -> ends LOW       picked LOW,  lose -> ends HIGH

A single published `base` mode therefore serves both buttons. The bet chips
($10/$50/$100/MAX) are ACP BET LEVELS (dashboard template), not published modes.

The multiplier (grid + RTP)
---------------------------
The reference mockup shows 1.87x, which is OFF the ACP 0.1x grid (187 cents is not a
multiple of 10) and cannot be published literally. 1.90x (190 cents) is the nearest
grid-legal value, used as both the LUT payout and the honest displayed multiplier.

The win probability is the smallest-denominator rational a/b whose realised RTP
(a/b)*1.90 lands in [96.00%, 96.70%] (game_config.py::_simplest_fraction_in, the
limbo/chicken Stern-Brocot descent):

    p = 29/57 (~50.88%)  ->  RTP = 29/57 * 1.90 = 96.67%

num_sims = 57 yields exactly 29 winning and 28 losing books, so the published odds
equal the book counts. wincap = 1.90 (the single payout is the win cap). To offer a
payout ladder instead, add multipliers to _MULTIPLIERS in game_config.py — each
becomes its own dot-free mode with its own exact num_sims, and the cross-mode RTP
spread stays <= 1.00% because every mode is pinned into [96.00%, 96.70%].

ACP math rules (enforced server-side)
-------------------------------------
  1. 0.1x LUT grid: 1.90x = 190 cents (a multiple of 10). lut_grid_exempt = False
     keeps the SDK grid check ON as a regression guard.
  2. RTP band (per-mode): "Return to Player must be between 90% and 96.70%" (96.67%).
  3. RTP consistency (cross-mode): trivially satisfied (single mode).
  4. Risk / star-rating (Max Payout, Tail Probability, ETL, CVaR, Std Dev): clean.
     The two-outcome payout std is ~0.95 (>= the 0.60 volatility floor) and 1.90x is
     far under the ~100x all-or-nothing ceiling that capped limbo.

Per-round events
----------------
    priceCall : {result:"Win"|"Lose", isWin, payoutMultiplier(cents = mult*100),
                 winChance(probability)}   (direction-neutral; emitted every round)
    finalWin  : {amount(cents)}   (amount = mult*100 on a win, else 0; base engine)

Build
-----
Dev (readable books):
    PYTHONPATH="$(pwd)" ./env/bin/python games/2_9_crypto_pulse/run.py
Production (compressed + format-checked):
    PYTHONPATH="$(pwd)" COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        ./env/bin/python games/2_9_crypto_pulse/run.py
Then upload library/publish_files/{index.json, books_<mode>.jsonl.zst,
lookUpTable_<mode>_0.csv} via the ACP dashboard. Bet levels (the bet-chip amounts)
and gameID are set in ACP, not here. provider_number is a placeholder (2) pending
the ACP-assigned value.

A standalone frontend_demo/ replays the published win/lose books on an animated
BTC chart (see frontend_demo/README.md).
