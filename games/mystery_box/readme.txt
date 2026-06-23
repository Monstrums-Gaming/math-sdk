Mystery Box (2_1_85)
====================

Mechanic
--------
Not a slot. The player pays a fixed cost of 32.94x the base bet to open one
"mystery box" and instantly receives exactly ONE prize, drawn from a fixed
probability table. There is no board, no spin, no free-spin round and no
optimisation step — the prize odds are authored directly in game_config.py.

Bet mode
--------
A single bet mode, "base", cost = 32.94 (base-bet units), target RTP = 85%.

Prize table (engine symbol -> fiction / catalog value / probability)
--------------------------------------------------------------------
  P1  Blue Checkmark      $7.00         7.000%
  P2  Grok Subscription   $30.00        7.000%
  P3  Cybertruck          $130,000.00   0.002%   (max win / wincap)
  P4  Dogecoin            $0.10         30.000%
  P5  TBC Hat             $40.00        8.000%
  P6  SpaceX Hoodie       $129.00       5.500%
  P7  Plaid Hat           $68.80        6.000%
  P8  Tesla Model 4       $80,600.00    0.003%
  P9  Neuralink Hat       $60.00        3.500%
  P10 Voucher             $0.01         21.895%  (below RGS minimum -> pays 0)
  P11 Flamethrower        $540.00       0.100%
  P12 Biography           $30.00        11.000%

Each prize pays its full catalog value as the RGS multiplier (base bet = 1
currency unit), so the wallet total equals the catalog value with no top-up.
The only exception is the Voucher: its $0.01 value is below the RGS minimum
payout (0.1x), so it resolves to 0. Probabilities sum to 1.0 and the expected
payout is 28.001, giving 28.001 / 32.94 = 85.00% RTP.

How the math is produced
-------------------------
- Each prize is its own simulation "criteria" with quota equal to its
  probability, so the published odds match the table (zero-payout outcomes use
  criteria "0"; the single max-win prize uses criteria "wincap").
- run_spin draws one prize for the round's criteria, pays it, and emits a
  mysteryReveal event followed by the standard winInfoSpecial / setWin /
  setTotalWin / finalWin events.
- The optimiser is disabled; lookup weights are uniform (1 per book), so prize
  frequency == draw frequency. Increase num_sims in run.py for finer resolution
  on the rare jackpots.

Files
-----
  game_config.py        prize table, bet mode, per-prize distributions
  game_calculations.py  draw_prize() weighted prize draw
  game_executables.py   evaluate_mystery_box() reveal + win events
  game_override.py       state hooks (no special symbols)
  gamestate.py           run_spin() — one box per round
  game_events.py         mysteryReveal emitter
  game_optimization.py   disabled stub (fixed odds, no optimisation)
  run.py                 driver: sims -> configs -> analysis -> format checks
  reels/BR0.csv          prize symbol list (descriptive only; not evaluated)
