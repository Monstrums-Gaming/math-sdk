Cash Paradise (3_2)
===================

Mechanic
--------
Not a slot. The player pays a fixed cost of 4.98x the base bet to open one
"mystery box" and instantly receives exactly ONE cash-voucher prize, drawn from
a fixed probability table. There is no board, no spin, no free-spin round and no
optimisation step — the prize odds are authored directly in game_config.py.

Bet mode
--------
A single bet mode, "base", cost = 4.98 (base-bet units), target RTP = 85%.

Prize table (engine symbol -> fiction / catalog value / probability)
--------------------------------------------------------------------
  CP1  $0.01 Voucher    $0.01        30.200%  (below RGS minimum -> pays 0)
  CP2  $0.10 Voucher    $0.10        28.000%
  CP3  $1 Voucher       $1.00        25.000%
  CP4  $2 Voucher       $2.00         5.000%
  CP5  $5 Voucher       $5.00         5.000%
  CP6  $10 Voucher      $10.00        5.000%
  CP7  $50 Voucher      $50.00        1.000%
  CP8  $100 Voucher     $100.00       0.600%
  CP9  $1,000 Voucher   $1,000.00     0.200%  (max win / wincap)

Each prize pays its full catalog value as the RGS multiplier (base bet = 1
currency unit), so the wallet total equals the catalog value with no top-up.
The only exception is the $0.01 Voucher: its $0.01 value is below the RGS minimum
payout (0.1x), so it resolves to 0. Probabilities sum to 1.0.

RTP
---
The authored expected payout over the full catalog values is 4.23102, giving a
nominal 4.23102 / 4.98 = 84.96%. Because the $0.01 voucher resolves to 0 (RGS
minimum), the effective expected payout is 4.22800, so the ACTUAL RTP is
4.22800 / 4.98 = 84.90%. (A box cost of 4.97767 would hit exactly 85.00% nominal;
4.98 is the rounded price in use, slightly below the 85% target.)

How the math is produced
-------------------------
- Each prize is its own simulation "criteria" with quota equal to its
  probability, so the published odds match the table (zero-payout outcomes use
  criteria "0"; the single max-win prize uses criteria "wincap").
- run_spin draws one prize for the round's criteria, pays it, and emits a
  mysteryReveal event followed by the standard winInfoSpecial / setWin /
  setTotalWin / finalWin events.
- The optimiser is disabled; lookup weights are uniform (1 per book), so prize
  frequency == draw frequency. num_sims is 100,000 so every quota maps to an
  exact integer book count; reduce it only for a quick smoke test.

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
