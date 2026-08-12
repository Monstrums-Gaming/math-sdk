Chart Race (2_11_chart_race)
============================

WHAT THE GAME IS

Three fictional company chart lines race toward a fixed SETTLEMENT line; the player
picks a company and a market and is paid if the pick finishes where the market says.
Two pick-neutral markets, each its own cost-1.0 two-outcome mode:

    mode      wins when the pick finishes   pays    exact odds     RTP
    highest   1st of 3 (highest close)      3.00x   8/25 (32.00%)  96.0000%
    lowest    3rd of 3 (lowest close)       3.00x   8/25 (32.00%)  96.0000%

Cross-mode spread: 0. Payout std 1.3994 (>= the 0.60 ACP Base-Volatility floor).
Lineage: the 2_9_trading_roulette direct-probability skeleton (Stern-Brocot odds pin,
k-scaled book counts, per-mode seed offsets) carrying 3_0_boat_race's pick-neutral
certified finishing order. Web pair: monstrums-web-sdk apps/2-11-chart-race.

PICK-NEUTRAL BOOKS

The book addresses abstract racers r0..r2 where r0 is ALWAYS the player's picked
company; the client maps the pick onto r0 at render time, so all three companies have
identical odds by construction and one 5,000-book pool per market serves every pick.

PER-MODE PINNED ODDS, NOT A UNIFORM RACE

A fair 3-way race gives each company 1/3, and 3.00x at 1/3 returns 100% — so the quoted
3.00x rides on a certified win chance pinned below the fair third: 8/25 = 32%, the
smallest-denominator rational whose realised RTP lands in [96.00%, 96.70%]. The
finishing-order frequencies a player observes are the mixture of the conditional laws
below at that certified probability; the odds derive from the lookup table alone and
verify_books.py proves mechanically that the rendered order cannot move them.

THE CONDITIONAL PRESENTATION LAW

Verdict-first generation: the criteria fixes the payout, the payout fixes r0's place,
the order is manufactured to honestly produce it — never the reverse.

    highest  win -> r0 1st;  loss -> r0 uniform over {2nd, 3rd}
    lowest   win -> r0 3rd;  loss -> r0 uniform over {1st, 2nd}

Rivals r1/r2 are shuffled uniformly into the remaining places. verify_books.py audits
the loss-place balance within 4 sigma over every published book.

THE FRONTEND CONTRACT

Event order:  raceResult -> (wincap on every WIN — the win payout IS the 3.00x global
cap) -> finalWin.

    {"index":0,"type":"raceResult","result":"Win"|"Lose","isWin":bool,
     "playerPlace":1..3,
     "finishOrder":[<racer ids by place, e.g. [1,0,2]>],   // r0 = the pick
     "payoutMultiplier":300,          // INTEGER HUNDREDTHS, present win or lose
     "winChance":0.32}
    {"type":"finalWin","amount":<cents>}

There is NO rank timeline (contrast 3_0_boat_race): the chart is continuous, so the
book certifies the finishing ORDER only and the frontend draws seeded cosmetic paths
obliged to arrive at exactly that order at the settlement line (the 2_9 landRow
philosophy). playerPlace always equals finishOrder.index(0) + 1.

SEEDS / BOOK COUNTS

Per mode: N = k*b = 200*25 = 5,000 books, W = k*a = 1,600 winners
(Fraction(W,N) == 8/25 exactly). Per-mode seed offsets keyed off the MODE INDEX
(stride 1,000,003 > every N) because payout cents are identical across markets.

BUILD & VERIFY

    make run GAME=2_11_chart_race                          # dev (readable books)
    COMPRESSION=1 RUN_FORMAT_CHECKS=1 \
        env/bin/python games/2_11_chart_race/run.py        # production publish set

    # mandatory before upload — execute_all_tests only proves book<->LUT:
    env/bin/python games/2_11_chart_race/verify_books.py

    # frontend demo bundle (samples published finishing orders per outcome):
    env/bin/python games/2_11_chart_race/frontend_demo/build_demo_data.py [dest]

PUBLISH ARTIFACTS

library/publish_files/: index.json, books_highest.jsonl.zst, books_lowest.jsonl.zst,
lookUpTable_highest_0.csv, lookUpTable_lowest_0.csv.

provider_number in game_config.py is a placeholder (2) — confirm the ACP-assigned
value before a production upload.
