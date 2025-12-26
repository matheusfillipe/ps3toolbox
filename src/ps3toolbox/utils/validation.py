"""File and input validation utilities."""

import os
from pathlib import Path

from ps3toolbox.utils.errors import InsufficientSpaceError


def validate_input_file(path: Path, extensions: list[str]) -> None:
    """Validate input file exists and has correct extension."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    if extensions and path.suffix.lower() not in [ext.lower() for ext in extensions]:
        raise ValueError(f"Invalid file extension. Expected one of: {extensions}")


def validate_output_path(path: Path, overwrite: bool = False) -> None:
    """Validate output path is writable."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {path}")

    if not path.parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {path.parent}")

    if not os.access(path.parent, os.W_OK):
        raise PermissionError(f"No write permission for directory: {path.parent}")


def check_disk_space(path: Path, required_bytes: int) -> bool:
    """Check if sufficient disk space is available."""
    stat = os.statvfs(path.parent)
    available_bytes = stat.f_bavail * stat.f_frsize

    if available_bytes < required_bytes:
        raise InsufficientSpaceError(
            f"Insufficient disk space. Required: {required_bytes}, Available: {available_bytes}"
        )

    return True
