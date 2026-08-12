# Chicken Crossing — Known Limitations

A plain-language summary of what the current Chicken Crossing build **can** and **cannot** do, for
discussion with the client. The game math is built and verified; these are the honest constraints to
agree on before launch.

**One-line summary:** The math is done and verified, but the game is currently an *honest
"predetermined reveal"* rather than a *live cash-out* game; it needs a small RTP retune to be
certifiable, its maximum wins are capped by Stake's risk rules, and true player-controlled cash-out
would require a larger rebuild that depends on Stake Engine support.

---

## 1. No genuine cash-out (predetermined settlement) — the main one

**What it is.** The moment the player presses **Bet**, the game server decides and **locks the entire
round** — the safe path, the exact lane where it ends, and the payout. The player **cannot choose
when to cash out**. The "Cross Next Lane" button is an honest, paced *reveal* of a pre-decided
result, not a real decision. (We deliberately removed any "Cash Out" button so the UI doesn't imply a
choice the player doesn't have.)

**Why.** Stake Engine is a certified **replay** system: each round is a pre-generated, hash-frozen
"book," and the payout cannot change after the bet. Our math publishes one fixed outcome per round.

**Path to resolve.** The real Chicken Road (and Stake's Mines / Dragon Tower) let players decide when
to stop. That needs a **stateful / live round** where only the danger positions are frozen and the
cash-out settles live. This is a **larger rebuild** of the math + integration, and it depends on
**Stake Engine confirming they support live multi-action cash-out for third-party games**.

## 2. RTP is above Stake's published ceiling (compliance)

**What it is.** The current build runs at **97% RTP**, but Stake caps published RTP at **96.70%**. As
built, it **cannot be uploaded** for certification.

**Why.** The game was authored to the requested 97%; the certification limit is 96.70%.

**Path to resolve.** A **one-setting retune** (`RTP_TARGET = 0.965`) rebuilds a compliant version.
The client should know the shipped numbers will be the ~96.5% ones, not 97%.

## 3. Maximum wins are capped (can't match the "real" game)

**What it is.** Top payouts are limited to roughly:

| Difficulty | Max win |
|---|---|
| Easy | ~24× |
| Medium | ~558× |
| Hard | ~920× |
| Daredevil | ~1,056× |

(A global 2,000× cap is applied.)

**Why.** The real Chicken Road advertises multipliers in the **millions×**. Those **fail Stake's risk
/ volatility validators** and cannot be published for a third-party game.

**Path to resolve.** This is a hard platform limit — the game's ceiling is intentionally much lower
than the original. Higher caps would need Stake to approve the higher-volatility profile.

## 4. Live integration not yet tested end-to-end

**What it is.** The **live wallet connection** (`/wallet/authenticate → play → end-round`) is built to
Stake's standard pattern but has **not been run against a real RGS** yet (no credentials) — it's only
been structurally verified.

**Refresh / reconnect** is **money-safe** — if the player refreshes mid-round, the server keeps the
result, nothing is lost and nothing is double-charged, and the round is restored and settled. The
*visual* "resume where you left off" is currently basic.

**Path to resolve.** Test against a real Stake Engine session once credentials are available; polish
the resume replay if desired.

## 5. It's a demo, not the production frontend

**What it is.** The browser page is a **local mockup** with play-money that **resets on refresh**.
It's for demonstrating the mechanic and validating the math — not the final shippable game client.

**Path to resolve.** Build/skin the production frontend (or integrate the mechanic into the real
client) when moving beyond the demo.

---

## What would change with a live cash-out rebuild

If the client wants players to genuinely decide when to cash out (like the real game):

- The **math model changes** — each round would freeze only the car/danger positions, not the whole
  payout.
- Settlement becomes **live** (the player's stop point determines the payout), which requires Stake
  Engine's **stateful round / cash-out support** — to be confirmed before committing.
- This is a **new, larger piece of work**, not a tweak to the current build.

Until then, the current build is the honest, certified-compatible option: a paced, predetermined
reveal with correct odds and no misleading cash-out promise.
