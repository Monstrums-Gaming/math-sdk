"""Event emitters for Porkageddon (2_0).

Per-round event order (the book contract with the frontend):

    porkSetup -> porkBattle -> porkResult -> [wincap] -> finalWin

`wincap` is the SDK's standard event (`src/events/events.py::wincap_event`) and
fires only on a mode's maximum-win books, because each `BetMode.max_win` is that
mode's true top payout (10.0x skirmish, 2000.0x brawl/bloodbath). Treat it as a
no-op if the client has nothing to show for it.

## Conventions

* `costMultiplier` is always `1.0` — one battle is one wager. The v1.0.5
  pay-per-move debits are gone; skill costs now only build the displayed pot.
* Skills are addressed by **slot index**, never by fighter. `porkSetup.slots`
  carries the stance's canonical slot table (cost + roll range) and the client
  renders slot `k` with the chosen fighter's name, art, rig and SFX. Books are
  fighter-neutral, which is exactly what makes every fighter's odds identical.
* `hpMax` is per-battle and **book-authoritative**. Damage rolls are honest (every
  `amount` sits inside its slot's published range), and the battle's absolute HP
  pool is the free variable that makes the drawn round count come out exact — so
  render the HP bar from `hpMax` and the per-round `hp` values, not from the
  fighter's stat block.
* `roll` is the raw uniform draw in integer ten-thousandths, kept so a client can
  re-derive `amount` for any fighter's slot-`k` skill
  (`trunc(lerp(dmgMin, dmgMax, roll/10000) * attackMod * scale)`) and so the
  transcript is reproducible for a PAR sheet.
* `action` is `"attack"`, `"heal"`, or `"none"` — `"none"` means the move was
  committed (its cost is already in the pot) but never resolved because the
  opponent's killing blow landed first. That is the shipped engine's behaviour:
  both costs enter the pot before a round resolves, and there are no refunds.
* Money: `payoutMultiplier` / `poolMultiplier` / `maxWin` are raw multiplier
  floats on the 0.1x grid; `finalWin.amount` is the integer cents scale
  (`multiplier * 100`) the client uses for wallet display.
* The book PREDETERMINES everything. No player action after `/wallet/play` can
  move `payoutMultiplier`; the skill "pick" is a commit reveal.
"""

from src.events.events import *  # noqa: F401,F403  (parity with the sibling games)


def pork_setup_event(
    gamestate,
    stance: str,
    label: str,
    hp_max: int,
    rounds: int,
    slots: list,
    golden_tier: str,
    golden_multiplier: int,
    max_win: float,
) -> None:
    """Announce the matchmaking state: stance, chassis, slot table, Golden Pig badge.

    The Golden Pig is revealed HERE, before the fight — a pre-revealed tail creates
    tension across the whole battle, and the badge on the existing pool ticker does
    all the work with no new UI. It is drawn independently of win/lose, so a golden
    battle must still be won to pay.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "porkSetup",
        "stance": stance,
        "stanceLabel": label,
        "costMultiplier": 1.0,
        "hpMax": hp_max,
        "rounds": rounds,
        "slots": list(slots),
        "goldenTier": golden_tier,              # none | bronze | silver | gold | diamond
        "goldenMultiplier": golden_multiplier,  # 1 when goldenTier == "none"
        "maxWin": max_win,
        "productMode": "base",
    }
    gamestate.book.add_event(event)


# `porkBattle.rounds[i]` layout. Fixed-order integer arrays, not objects: a
# skirmish battle runs 6-8 rounds and at 200k books/mode the repeated key strings
# were the single largest contributor to the compressed book size (~2x). The layout
# is frozen — append new fields at the end only.
ROUND_FIELDS = (
    "first",   # 0 = player moves first, 1 = opponent (the 47% first-turn roll)
    "pSlot",   # player's skill slot index into porkSetup.slots
    "pAct",    # 0 = attack, 1 = heal, 2 = committed but never resolved
    "pRoll",   # raw uniform draw, ten-thousandths
    "pAmt",    # damage dealt (attack) or HP restored (heal)
    "pHp",     # player HP after the round
    "oSlot",
    "oAct",
    "oRoll",
    "oAmt",
    "oHp",     # opponent HP after the round
)
ACT_ATTACK, ACT_HEAL, ACT_NONE = 0, 1, 2
FIRST_PLAYER, FIRST_OPPONENT = 0, 1


def pork_battle_event(gamestate, rounds: list) -> None:
    """The whole transcript in one event — one compact array per round.

    Deliberately not one event per tween: at 3 modes x 200k sims a per-tween stream
    balloons the compressed books for no gain. See `ROUND_FIELDS` for the array
    layout; `fieldOrder` is echoed into the event so a client can bind by name
    instead of hard-coding indices.

    Skill cost is NOT repeated per round — it is a property of the slot and lives in
    `porkSetup.slots`. The pot is `sum` of both sides' slot costs over every round
    (both sides commit even on the round they are killed), and `porkResult.poolUnits`
    carries the authoritative total.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "porkBattle",
        "numRounds": len(rounds),
        "fieldOrder": list(ROUND_FIELDS),
        "rounds": list(rounds),
    }
    gamestate.book.add_event(event)


def pork_result_event(
    gamestate,
    stance: str,
    is_win: bool,
    rounds: int,
    pool_units: float,
    pool_multiplier: float,
    golden_tier: str,
    golden_multiplier: int,
    payout_multiplier: float,
) -> None:
    """Report the predetermined outcome.

    `poolUnits` is the raw sum of both sides' skill costs (what the pot ticker
    counts up to) and `poolMultiplier` is that pot expressed as a stake multiple.
    On an ordinary win they are the payout; on a Golden Pig win the badge pays a
    fixed canonical pot times the tier instead, so `payoutMultiplier` is the
    authority and `poolMultiplier` is presentation only.
    """
    event = {
        "index": len(gamestate.book.events),
        "type": "porkResult",
        "stance": stance,
        "isWin": is_win,
        "rounds": rounds,
        "poolUnits": pool_units,
        "poolMultiplier": pool_multiplier,
        "goldenTier": golden_tier,
        "goldenMultiplier": golden_multiplier,
        "payoutMultiplier": payout_multiplier,
    }
    gamestate.book.add_event(event)


def pork_final_win_event(gamestate, amount: int, multiplier: float) -> None:
    """Close the round with the total win (integer cents) and its raw multiplier."""
    event = {
        "index": len(gamestate.book.events),
        "type": "finalWin",
        "amount": amount,
        "multiplier": multiplier,
    }
    gamestate.book.add_event(event)
