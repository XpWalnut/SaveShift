import base64
import ctypes
from ctypes import wintypes
import os


class SecretProtectionError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


class SecretProtector:
    """Protect secrets for the current Windows user with DPAPI."""

    _UI_FORBIDDEN = 0x01

    @staticmethod
    def protect(value: str) -> str:
        if not value:
            return ""

        protected = SecretProtector._crypt_protect(value.encode("utf-8"))
        return base64.urlsafe_b64encode(protected).decode("ascii")

    @staticmethod
    def unprotect(value: str) -> str:
        if not value:
            return ""

        try:
            protected = base64.urlsafe_b64decode(value.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise SecretProtectionError("Stored credential is invalid.") from error

        try:
            return SecretProtector._crypt_unprotect(protected).decode("utf-8")
        except UnicodeDecodeError as error:
            raise SecretProtectionError("Stored credential is invalid.") from error

    @staticmethod
    def _crypt_protect(value: bytes) -> bytes:
        crypt32, kernel32 = SecretProtector._windows_libraries()
        input_blob, input_buffer = SecretProtector._blob(value)
        output_blob = _DataBlob()

        succeeded = crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "Save Shift coordination credential",
            None,
            None,
            None,
            SecretProtector._UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        _ = input_buffer

        if not succeeded:
            raise SecretProtectionError(
                "Windows could not protect the coordination credential."
            ) from ctypes.WinError()

        return SecretProtector._copy_and_free(output_blob, kernel32)

    @staticmethod
    def _crypt_unprotect(value: bytes) -> bytes:
        crypt32, kernel32 = SecretProtector._windows_libraries()
        input_blob, input_buffer = SecretProtector._blob(value)
        output_blob = _DataBlob()

        succeeded = crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            None,
            None,
            None,
            None,
            SecretProtector._UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        _ = input_buffer

        if not succeeded:
            raise SecretProtectionError(
                "Windows could not unlock the coordination credential."
            ) from ctypes.WinError()

        return SecretProtector._copy_and_free(output_blob, kernel32)

    @staticmethod
    def _windows_libraries():
        if os.name != "nt":
            raise SecretProtectionError(
                "Coordination credentials require Windows Data Protection API."
            )

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        return crypt32, kernel32

    @staticmethod
    def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
        buffer = ctypes.create_string_buffer(value, len(value))
        blob = _DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        return blob, buffer

    @staticmethod
    def _copy_and_free(blob: _DataBlob, kernel32) -> bytes:
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            if blob.pbData:
                kernel32.LocalFree(ctypes.cast(blob.pbData, wintypes.HLOCAL))
