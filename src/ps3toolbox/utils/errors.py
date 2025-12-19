"""Custom exceptions for PS3 Toolbox."""


class PS3ToolboxError(Exception):
    """Base exception for PS3 Toolbox errors."""
    pass


class PS2EncryptionError(PS3ToolboxError):
    """Base exception for PS2 encryption errors."""
    pass


class InvalidISOError(PS2EncryptionError):
    """ISO validation failed."""
    pass


class InvalidKeyError(PS2EncryptionError):
    """Invalid or missing encryption key."""
    pass


class CorruptedFileError(PS2EncryptionError):
    """File appears corrupted or incomplete."""
    pass


class InsufficientSpaceError(PS3ToolboxError):
    """Insufficient disk space available."""
    pass
