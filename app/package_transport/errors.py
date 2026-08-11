"""Errors raised at the remote package transport boundary."""


class PackageTransportError(RuntimeError):
    """Base error for package publication and retrieval failures."""


class PackageTransportMismatchError(PackageTransportError):
    """Raised when an artifact is used with the wrong transport provider."""


class PackageTransferIntegrityError(PackageTransportError):
    """Raised when transferred package bytes do not match their descriptor."""


class PackageEncryptionError(PackageTransportError):
    """Raised when a package cannot be securely encrypted or authenticated."""
