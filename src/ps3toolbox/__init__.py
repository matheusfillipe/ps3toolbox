"""PS3 Toolbox - Tools for PS3 homebrew operations."""

__version__ = "0.1.0"
__author__ = "Matheus"
__license__ = "GPL-3.0-or-later"

from ps3toolbox.ps2.decrypt import decrypt_ps2_iso
from ps3toolbox.ps2.decrypt import extract_metadata
from ps3toolbox.ps2.encrypt import encrypt_ps2_iso


__all__ = [
    "encrypt_ps2_iso",
    "decrypt_ps2_iso",
    "extract_metadata",
    "__version__",
]
