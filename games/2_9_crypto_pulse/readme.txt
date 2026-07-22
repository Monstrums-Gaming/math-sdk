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

Direction-neutral book (why direction is not a mode)
----------------------------------------------------
HIGH and LOW are SYMMETRIC — identical odds. So from the book's point of view the
direction is cosmetic: each round's book encodes only win/lose and the offered
multiplier. The frontend derives which way the chart finishes from the player's
chosen side plus isWin:

    endsHigh = (pickedHigh == isWin)
      picked HIGH, win  -> ends HIGH      picked HIGH, lose -> ends LOW
      picked LOW,  win  -> ends LOW       picked LOW,  lose -> ends HIGH

Direction is therefore never a published mode — each difficulty mode serves both
buttons. The bet chips ($10/$50/$100/MAX) are ACP BET LEVELS (dashboard template),
also not published modes.

Difficulty ladder (multipliers, grid + RTP)
-------------------------------------------
Four difficulty tiers are published, one mode each. Every multiplier is a multiple of
0.10 (the ACP 0.1x grid — the mockup's off-grid 1.87x is replaced by 1.90x). For each
multiplier M the win probability is the smallest-denominator rational a/b whose
realised RTP (a/b)*M lands in [96.00%, 96.70%] (game_config.py::_simplest_fraction_in,
the limbo/chicken Stern-Brocot descent); num_sims = b yields exactly a winning books,
so published odds equal the book counts.

    Difficulty  Multiplier  Mode name   ~Win chance   RTP
    Easy        1.40x       call_140     ~69%         ~96.x%
    Medium      1.90x       call_190     ~51% (29/57)  96.67%
    Hard        3.00x       call_300     ~32%         ~96.x%
    Expert      5.00x       call_500     ~19%         ~96.x%

(Exact a/b and RTP are derived at build time and printed by run.py.) wincap = 5.00
(the top payout). The tiers live in _MULTIPLIERS in game_config.py — add/remove entries
there and everything (modes, num_sims, wincap, configs) regenerates.

ACP math rules (enforced server-side)
-------------------------------------
  1. 0.1x LUT grid: every payout (140/190/300/500 cents) is a multiple of 10.
     lut_grid_exempt = False keeps the SDK grid check ON as a regression guard.
  2. RTP band (per-mode): each mode's RTP is pinned into [96.00%, 96.70%].
  3. RTP consistency (cross-mode): all modes share the same pin, so the spread is
     <= 1.00% (game_config.py::_validate asserts it).
  4. Risk / star-rating (Max Payout, Tail Probability, ETL, CVaR, Std Dev): the game is
     rated off its tamest mode — the lowest tier 1.40x has payout std ~0.649 (>= the
     0.60 volatility floor), and the highest tier 5.00x is far under the ~100x
     all-or-nothing ceiling that capped limbo.

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
