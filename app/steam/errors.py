class SteamworksError(RuntimeError):
    """Raised when the local Steam client or Steamworks API cannot complete work."""


class SteamworksUnavailableError(SteamworksError):
    """Raised when Steamworks cannot be loaded or initialized."""
