from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True)
class SteamIdentity:
    steam_id: str
    persona_name: str


@dataclass(frozen=True)
class SteamFriend:
    steam_id: str
    persona_name: str


@dataclass(frozen=True)
class SteamLobby:
    lobby_id: str


class SteamSocialClient(Protocol):
    """Steam identity and temporary-lobby operations used by group setup."""

    def current_identity(self) -> SteamIdentity:
        ...

    def list_friends(self) -> list[SteamFriend]:
        ...

    def create_private_lobby(
        self,
        *,
        maximum_members: int = 16,
        metadata: Mapping[str, str] | None = None,
    ) -> SteamLobby:
        ...

    def join_lobby(self, lobby_id: str) -> SteamLobby:
        ...

    def leave_lobby(self, lobby_id: str) -> None:
        ...

    def invite_friend(self, lobby_id: str, friend_steam_id: str) -> None:
        ...

    def open_invite_overlay(self, lobby_id: str) -> None:
        ...

    def lobby_members(self, lobby_id: str) -> list[str]:
        ...

    def lobby_data(self, lobby_id: str, key: str) -> str:
        ...

    def set_lobby_data(self, lobby_id: str, key: str, value: str) -> None:
        ...
