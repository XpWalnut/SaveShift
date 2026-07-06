from app.games.abiotic_factor.discovery import AbioticFactorDiscovery
from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId


class AbioticFactorGame(SupportedGame):
    game_id = GameId.ABIOTIC_FACTOR
    display_name = "Abiotic Factor"
    process_names = ["AbioticFactor-Win64-Shipping.exe", "AbioticFactor.exe"]

    def discovery(self) -> GameDiscovery:
        return AbioticFactorDiscovery()