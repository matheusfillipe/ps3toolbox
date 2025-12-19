"""PS2 .BIN.ENC decryption to ISO format."""

import struct
from pathlib import Path
from ps3toolbox.core.keys import (
    SEGMENT_SIZE, NUM_CHILD_SEGMENTS,
    PS2_PLACEHOLDER_KLIC, get_base_keys
)
from ps3toolbox.core.crypto import derive_keys, aes128_cbc_decrypt
from ps3toolbox.ps2.header import parse_ps2_header, verify_header
from ps3toolbox.utils.errors import CorruptedFileError
from ps3toolbox.utils.progress import ProgressCallback


def decrypt_ps2_iso(
    encrypted_path: Path,
    output_path: Path,
    mode: str = 'cex',
    klicensee: bytes | None = None,
    progress_callback: ProgressCallback | None = None
) -> None:
    """Decrypt .BIN.ENC to ISO format."""
    with open(encrypted_path, 'rb') as f:
        header = f.read(0x100)

    if not verify_header(header):
        raise CorruptedFileError(f"Invalid or corrupted header in {encrypted_path}")

    metadata = parse_ps2_header(header)
    data_size = metadata['iso_size']

    klic = klicensee or PS2_PLACEHOLDER_KLIC
    base_data_key, base_meta_key = get_base_keys(mode)
    data_key, meta_key = derive_keys(base_data_key, base_meta_key, klic)

    zero_iv = bytes(16)

    with open(encrypted_path, 'rb') as in_f, open(output_path, 'wb') as out_f:
        in_f.seek(SEGMENT_SIZE)

        remaining = data_size
        bytes_processed = 0

        while remaining > 0:
            meta_buffer = in_f.read(SEGMENT_SIZE)
            if not meta_buffer:
                break

            data_buffer = in_f.read(SEGMENT_SIZE * NUM_CHILD_SEGMENTS)
            if not data_buffer:
                break

            decrypted_data = bytearray()
            for i in range(NUM_CHILD_SEGMENTS):
                segment_start = i * SEGMENT_SIZE
                segment_end = segment_start + SEGMENT_SIZE
                encrypted_segment = data_buffer[segment_start:segment_end]

                if not encrypted_segment or len(encrypted_segment) < SEGMENT_SIZE:
                    break

                decrypted_segment = aes128_cbc_decrypt(data_key, zero_iv, encrypted_segment)
                decrypted_data.extend(decrypted_segment)

            write_size = min(len(decrypted_data), remaining)
            out_f.write(decrypted_data[:write_size])

            bytes_processed += write_size
            remaining -= write_size

            if progress_callback:
                progress_callback(bytes_processed, data_size)


def extract_metadata(encrypted_path: Path) -> dict[str, int | str | bytes]:
    """Extract metadata from encrypted PS2 Classic file."""
    with open(encrypted_path, 'rb') as f:
        header = f.read(0x100)

    if not verify_header(header):
        raise CorruptedFileError(f"Invalid header in {encrypted_path}")

    return parse_ps2_header(header)
