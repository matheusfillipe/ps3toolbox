"""Basic usage examples for PS3 Toolbox."""

from pathlib import Path
from ps3toolbox import encrypt_ps2_iso, decrypt_ps2_iso, extract_metadata


def example_encrypt():
    """Example: Encrypt a PS2 ISO."""
    encrypt_ps2_iso(
        Path('game.iso'),
        Path('game.iso.enc'),
        mode='cex'
    )
    print("Encryption complete!")


def example_decrypt():
    """Example: Decrypt an encrypted PS2 Classic."""
    decrypt_ps2_iso(
        Path('game.iso.enc'),
        Path('game_decrypted.iso'),
        mode='cex'
    )
    print("Decryption complete!")


def example_with_progress():
    """Example: Encryption with progress callback."""
    def progress_callback(current: int, total: int) -> None:
        percent = (current / total) * 100
        print(f"Progress: {percent:.1f}%")

    encrypt_ps2_iso(
        Path('game.iso'),
        Path('game.iso.enc'),
        mode='cex',
        progress_callback=progress_callback
    )


def example_extract_info():
    """Example: Extract metadata from encrypted file."""
    metadata = extract_metadata(Path('game.iso.enc'))

    print(f"Content ID: {metadata['content_id']}")
    print(f"ISO Size: {metadata['iso_size']:,} bytes")
    print(f"Segment Size: 0x{metadata['segment_size']:X}")


if __name__ == '__main__':
    print("PS3 Toolbox Examples")
    print("=" * 50)
    print("\nSee function definitions for usage examples.")
