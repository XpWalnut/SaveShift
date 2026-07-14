class CoordinationError(RuntimeError):
    """Base error for provider-neutral coordination failures."""


class CoordinationConfigurationError(CoordinationError):
    """The configured coordination endpoint or credentials are invalid."""


class CoordinationUnavailableError(CoordinationError):
    """The coordination provider could not be reached or returned invalid data."""


class LockConflictError(CoordinationError):
    """Another device currently owns the requested project lock."""

    def __init__(self, message: str, lock=None) -> None:
        super().__init__(message)
        self.lock = lock


class LockOwnershipError(CoordinationError):
    """The current device does not own the requested lease."""
