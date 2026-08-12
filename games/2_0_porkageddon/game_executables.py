"""Orchestrating routines for Porkageddon (2_0) — the battle transcript generator.

The RGS has already drawn the outcome before this code runs: the criteria assigned
to a sim fixes the payout exactly. So this module's job is the reverse of a live
game engine — given a payout, manufacture a battle that honestly produces it:

  1. Draw a `(rounds, pool)` shape consistent with the criteria. Body-win criteria
     are keyed by payout cents, so only the pools that snap to that payout are
     eligible; golden wins and losses may come from any pool.
  2. Draw the Golden Pig tier (fixed by the criteria on a golden win, cosmetic on a
     body win or a loss).
  3. Draw a cost sequence of `2 x rounds` skill picks summing to that pool
     **exactly** — a uniform draw over the compositions with the required sum, via
     the DP in `pork_math.cost_sequence_counts`. Both sides commit every round
     including the last, which is the shipped engine's behaviour: both costs enter
     the pot before the round resolves and there are no refunds.
  4. Roll honest damage/heal amounts inside each slot's published range, then solve
     for the battle's absolute `hpMax` so the loser dies exactly in the final round
     and the winner survives.

Step 4 is the interesting one. Something has to give for the drawn round count to
come out exact, and the choice of *what* gives is a fairness decision:

  * Rubber-banding the damage numbers to fit was rejected — the roll ranges are wide
    (10-40 vs 60-70), so out-of-range numbers are trivially datamineable and would
    read as rigged.
  * Instead the free variable is `hpMax`, which the player never sees as a number
    (the client renders a bar). Every damage number stays inside its published
    range; only the size of the HP pool flexes, and it is held within +/-20% of the
    stance's nominal chassis whenever a natural fit exists.

Everything is seeded from `reset_seed(sim)`, so a book is reproducible, and none of
it can move the payout — the payout came from the criteria.
"""

import random

import pork_math as pm
from game_calculations import GameCalculations
from game_events import (
    ACT_ATTACK,
    ACT_HEAL,
    ACT_NONE,
    FIRST_OPPONENT,
    FIRST_PLAYER,
    pork_battle_event,
    pork_final_win_event,
    pork_result_event,
    pork_setup_event,
)

_ACT_CODE = {"attack": ACT_ATTACK, "heal": ACT_HEAL, "none": ACT_NONE}

# Composition-count DP tables, memoised per (cost tuple, number of picks).
_SEQ_DP = {}

# How far hpMax may drift from the stance's nominal chassis before we resample.
_HP_TOLERANCE = 0.20
# Draws allowed per battle before we settle for a feasible-but-off-chassis window.
# Past _FIT_ATTEMPTS we also stop letting the LOSER heal: a loser heal that walks
# its accumulated damage back below an earlier peak makes "dies exactly on the final
# swing" impossible for that plan, and it is the dominant cause of hard shapes.
_FIT_ATTEMPTS = 64
_MAX_DRAWS = 2048

# The shipped client's first-turn roll (GameVariables.FIRST_TURN_CHANCE).
_FIRST_TURN_CHANCE = 0.47


def _dp_table(costs: tuple, picks: int) -> dict:
    key = (costs, picks)
    if key not in _SEQ_DP:
        _SEQ_DP[key] = pm.cost_sequence_counts(costs, picks)
    return _SEQ_DP[key]


def _draw_weighted(entries: list) -> list:
    """Pick one `[..., weight]` row, weighted by its trailing element."""
    return random.choices(entries, weights=[row[-1] for row in entries], k=1)[0]


def _sample_cost_sequence(costs: tuple, picks: int, total: int) -> list:
    """Uniform draw among the `picks`-length cost sequences summing to `total`.

    Walks the composition-count DP backwards, weighting each candidate by how many
    completions it leaves — which makes every valid sequence equally likely.
    """
    table = _dp_table(costs, picks)
    assert table.get((picks, total), 0) > 0, f"pool {total} unreachable in {picks} picks"
    seq, remaining = [], total
    for n in range(picks, 0, -1):
        weights = [table.get((n - 1, remaining - c), 0) for c in costs]
        pick = random.choices(costs, weights=weights, k=1)[0]
        seq.append(pick)
        remaining -= pick
    assert remaining == 0, "cost sequence did not consume the pool"
    return seq


def _roll_amount(low: int, high: int, scale_num: int, scale_den: int) -> tuple:
    """Honest uniform draw inside a published range -> (roll in ten-thousandths, amount).

    Mirrors the shipped client's `trunc(uniform(min, max) * attackMod * rtp)`, kept
    in integer arithmetic so a replay is bit-stable. The reference chassis has
    attackMod 1.00, so only the 0.97 / 1.00 side scalar applies.
    """
    roll_bp = random.randrange(0, 10_001)
    scaled = (low * 10_000 + (high - low) * roll_bp) * scale_num
    return roll_bp, max(1, scaled // (10_000 * scale_den))


class GameExecutables(GameCalculations):
    """Resolve one Porkageddon battle and emit its client events."""

    # ------------------------------------------------------------------ shape
    def _draw_shape(self, params: dict, meta: dict) -> tuple:
        """Draw (rounds, pool_hundredths, golden_tier, golden_multiplier)."""
        if meta["kind"] == "body":
            sources = params["body_sources"][str(meta["cents"])]
        else:
            sources = params["pool_sources"]
        rounds, pool_h, _weight = _draw_weighted(sources)

        if meta["kind"] == "golden":
            return rounds, pool_h, meta["tier"], meta["tierMultiplier"]
        if meta["kind"] == "body":
            # A golden battle pays its badge rather than the pot and has its own
            # criteria, so an ordinary win is by construction not golden.
            return rounds, pool_h, "none", 1
        tier, mult, _w = _draw_weighted(params["golden_sources"])  # loss: cosmetic reveal
        return rounds, pool_h, tier, mult

    # -------------------------------------------------------------- transcript
    def _build_transcript(self, params: dict, rounds: int, costs: list, player_wins: bool) -> tuple:
        """Turn a cost sequence into a transcript. Returns (hp_max, round entries)."""
        cost_to_slot = {s["costHundredths"]: s["index"] for s in params["slots"]}
        nominal_hp = params["hp"]
        lo_hp = int(nominal_hp * (1 - _HP_TOLERANCE))
        hi_hp = int(nominal_hp * (1 + _HP_TOLERANCE))
        winner, loser = ("p", "o") if player_wins else ("o", "p")

        # An infeasible plan costs nothing but a redraw, so keep drawing rather than
        # ever rewriting a damage number: an out-of-range `amount` is trivially
        # datamineable and desyncs any client that re-derives it from `roll`.
        best = None
        for attempt in range(_MAX_DRAWS):
            heal_sides = ("p", "o") if attempt < _FIT_ATTEMPTS else (winner,)
            plan = self._draw_plan(params, rounds, costs, cost_to_slot, winner, heal_sides)
            fit = self._solve_hp(plan, rounds, winner, loser)
            if fit is None:
                continue
            low, high, kill_index = fit
            if low <= hi_hp and high >= lo_hp:
                # Draw uniformly inside the window rather than pinning to an edge —
                # hpMax affects nothing but the HP bar's scale, and clamping to the
                # tolerance bound would make most battles share one chassis value.
                hp_max = random.randint(max(low, lo_hp), min(high, hi_hp))
                return hp_max, self._render(plan, rounds, hp_max, winner, loser, kill_index)
            if best is None:
                best = fit + (plan,)  # feasible, but the chassis would look wrong

        # No in-tolerance chassis in _MAX_DRAWS draws: take the closest feasible one.
        # Still an honest transcript — only hpMax is off-nominal.
        assert best is not None, (
            f"no feasible hpMax window in {_MAX_DRAWS} draws for {params['stance']} "
            f"rounds={rounds} pool={sum(costs)}"
        )
        low, high, kill_index, plan = best
        hp_max = low if abs(low - nominal_hp) <= abs(high - nominal_hp) else high
        return hp_max, self._render(plan, rounds, hp_max, winner, loser, kill_index)

    def _draw_plan(self, params, rounds, costs, cost_to_slot, winner, heal_sides=("p", "o")) -> list:
        """Per-round move plan: turn order, slot, action and honest rolls for both sides.

        `heal_sides` restricts which sides may render a heal. Suppressing the loser's
        heals is presentation-only (it cannot touch the pot or the payout) and is how
        hard shapes are made feasible — see `_build_transcript`.
        """
        heal_cost_h = params["heal_cost_hundredths"]
        heal_slot = params["heal_slot"]
        heals = {"p": 0, "o": 0}
        plan = []
        for r in range(rounds):
            entry = {
                "r": r,
                "first": "player" if random.random() <= _FIRST_TURN_CHANCE else "opponent",
            }
            for side in ("p", "o"):
                cost_h = costs[2 * r + (0 if side == "p" else 1)]
                slot = cost_to_slot[cost_h]
                # Penicillin shares one of the stance's slot costs, so choosing it
                # never perturbs the pot. The winner must swing on the last round.
                heal = (
                    side in heal_sides
                    and cost_h == heal_cost_h
                    and heals[side] < pm.HEAL_LIMIT
                    and not (side == winner and r == rounds - 1)
                    and random.random() < pm.HEAL_RENDER_CHANCE
                )
                if heal:
                    heals[side] += 1
                    slot = heal_slot
                    low, high = pm.HEAL_MIN, pm.HEAL_MAX
                else:
                    low = params["slots"][slot]["dmgMin"]
                    high = params["slots"][slot]["dmgMax"]
                scale = pm.PLAYER_ROLL_SCALE if side == "p" else pm.OPPONENT_ROLL_SCALE
                roll_bp, amount = _roll_amount(low, high, scale.numerator, scale.denominator)
                entry[side] = {
                    "slot": slot,
                    "cost": cost_h,
                    "action": "heal" if heal else "attack",
                    "roll": roll_bp,
                    "amount": amount,
                }
            plan.append(entry)
        return plan

    @staticmethod
    def _walk(plan, rounds) -> list:
        """Replay the plan tracking cumulative damage taken by each side.

        Returns one row per resolved move: (round, side, action, amount, taken-snapshot).
        Heals cap at the damage taken so far, which reproduces the client's
        `min(hpMax, hp + heal)` without needing to know hpMax yet.
        """
        taken = {"p": 0, "o": 0}
        trail = []
        for r, entry in enumerate(plan):
            order = ("p", "o") if entry["first"] == "player" else ("o", "p")
            for side in order:
                move = entry[side]
                target = "o" if side == "p" else "p"
                if move["action"] == "heal":
                    applied = min(move["amount"], taken[side])
                    taken[side] -= applied
                    trail.append((r, side, "heal", applied, dict(taken)))
                else:
                    taken[target] += move["amount"]
                    trail.append((r, side, "attack", move["amount"], dict(taken)))
        return trail

    def _solve_hp(self, plan, rounds, winner, loser):
        """Feasible hpMax window for 'the loser dies on the winner's last swing'."""
        trail = self._walk(plan, rounds)
        kill_index = self._kill_index(trail, rounds, winner)
        if kill_index is None:
            return None
        loser_final = trail[kill_index][4][loser]
        loser_before = max([0] + [row[4][loser] for row in trail[:kill_index]])
        # Only moves up to and including the kill are ever applied — `_render` emits
        # anything after it as "committed but unresolved" — so a later move must not
        # constrain the chassis. Including them rejected ~21% of renderable plans.
        winner_peak = max([0] + [row[4][winner] for row in trail[: kill_index + 1]])
        low = max(loser_before, winner_peak) + 1
        if low > loser_final:
            # Either the winner absorbed more than the loser, or a loser heal walked
            # its damage back below an earlier peak so it cannot die on the final
            # swing. Both are fixed by redrawing, never by editing a damage number.
            return None
        return low, loser_final, kill_index

    @staticmethod
    def _kill_index(trail, rounds, winner):
        for i in range(len(trail) - 1, -1, -1):
            r, side, action, _amount, _taken = trail[i]
            if r == rounds - 1 and side == winner and action == "attack":
                return i
        return None

    def _render(self, plan, rounds, hp_max, winner, loser, kill_index) -> list:
        """Emit-ready round entries with HP after each round and the killing blow applied.

        Every `amount` here is the honestly rolled value — overkill on the killing
        blow is absorbed by the HP bar (it stops at 0), exactly as any fighting game
        does. Nothing rewrites a damage number to make the arithmetic work.
        """
        taken = {"p": 0, "o": 0}
        shown_rounds = []
        dead = False
        step = 0
        for r, entry in enumerate(plan):
            order = ("p", "o") if entry["first"] == "player" else ("o", "p")
            shown = {}
            for side in order:
                move = entry[side]
                target = "o" if side == "p" else "p"
                if dead:
                    # Committed (its cost is already in the pot) but never resolved.
                    shown[side] = dict(move, action="none", amount=0)
                    step += 1
                    continue
                amount = move["amount"]
                if move["action"] == "heal":
                    amount = min(amount, taken[side])
                    taken[side] -= amount
                else:
                    if step == kill_index:
                        taken[target] = hp_max
                        dead = True
                    else:
                        taken[target] += amount
                        if taken[target] >= hp_max:
                            taken[target] = hp_max
                            dead = True
                shown[side] = dict(move, amount=amount)
                step += 1
            # Fixed-order array, see game_events.ROUND_FIELDS.
            shown_rounds.append(
                [
                    FIRST_PLAYER if entry["first"] == "player" else FIRST_OPPONENT,
                    shown["p"]["slot"],
                    _ACT_CODE[shown["p"]["action"]],
                    shown["p"]["roll"],
                    shown["p"]["amount"],
                    hp_max - taken["p"],
                    shown["o"]["slot"],
                    _ACT_CODE[shown["o"]["action"]],
                    shown["o"]["roll"],
                    shown["o"]["amount"],
                    hp_max - taken["o"],
                ]
            )
        assert taken[loser] == hp_max, "loser did not reach 0 HP"
        assert taken[winner] < hp_max, "winner did not survive"
        return shown_rounds

    # -------------------------------------------------------------------- round
    def evaluate_battle(self) -> None:
        """Resolve the battle for the active criteria and emit the reveal events."""
        params = self.get_mode_params()
        meta = params["criteria_meta"][self.criteria]
        payout = params["criteria_payout"][self.criteria]
        is_win = meta["kind"] != "loss"

        rounds, pool_h, tier, tier_mult = self._draw_shape(params, meta)
        costs = _sample_cost_sequence(tuple(params["costs"]), 2 * rounds, pool_h)
        hp_max, transcript = self._build_transcript(params, rounds, costs, is_win)

        pool_multiplier = pm.body_cents(pool_h, params["pool_norm_thousandths"]) / 100.0
        if meta["kind"] == "body":
            assert abs(pool_multiplier - payout) < 1e-9, (
                f"{self.criteria}: pot {pool_multiplier} != payout {payout}"
            )

        pork_setup_event(
            self,
            stance=params["stance"],
            label=params["label"],
            hp_max=hp_max,
            rounds=rounds,
            slots=params["slots"],
            golden_tier=tier,
            golden_multiplier=tier_mult,
            max_win=params["max_win"],
        )
        pork_battle_event(self, rounds=transcript)
        pork_result_event(
            self,
            stance=params["stance"],
            is_win=is_win,
            rounds=rounds,
            pool_units=pool_h / 100.0,
            pool_multiplier=pool_multiplier,
            golden_tier=tier,
            golden_multiplier=tier_mult,
            payout_multiplier=payout,
        )

        self.win_manager.update_spinwin(payout)
        if payout > 0:
            self.evaluate_wincap()

    def evaluate_battle_finalwin(self) -> None:
        """Finalise the payout and emit the reference-shaped finalWin event."""
        self.update_final_win()
        pork_final_win_event(
            self,
            amount=int(round(self.final_win * 100, 0)),
            multiplier=self.final_win,
        )
