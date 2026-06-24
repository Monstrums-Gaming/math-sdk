"""Orchestrating routines for Cash Paradise (3_2)."""

from game_calculations import GameCalculations
from game_events import mystery_reveal_event
from src.events.events import win_info_special_event, set_win_event, set_total_event


class GameExecutables(GameCalculations):
    """Resolve a single mystery-box purchase and emit its client events."""

    def evaluate_mystery_box(self) -> None:
        """Draw one prize, pay it, and emit the reveal/win event sequence."""
        symbol, payout = self.draw_prize()

        # Record only the rare prizes so they are searchable in the force files.
        # Recording every book would make state.imprint_wins O(n^2).
        if symbol in self.config.record_prizes:
            self.record({"prize": symbol, "criteria": self.criteria})

        prize_name = self.config.prize_names[symbol]
        mystery_reveal_event(self, symbol, prize_name, payout)

        self.win_manager.update_spinwin(payout)

        if payout > 0:
            self.evaluate_wincap()
            win_info_special_event(self, payout, meta={"prize": symbol, "prizeName": prize_name})

        set_win_event(self)
        set_total_event(self)
