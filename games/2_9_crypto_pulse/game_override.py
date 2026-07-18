"""State overrides for Crypto Pulse (2_9)."""

from game_executables import GameExecutables


class GameStateOverride(GameExecutables):
    """Override universal state hooks for the Crypto Pulse flow."""

    def reset_book(self) -> None:
        super().reset_book()
        # Crypto Pulse has no board mechanic; nothing extra to reset.

    def assign_special_sym_function(self) -> None:
        # No special symbols (wild/scatter/multiplier) participate in this game.
        self.special_symbol_functions = {}
