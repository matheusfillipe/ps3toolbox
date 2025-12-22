"""PS2 ISO encryption to .BIN.ENC format."""

import os
import struct
import shutil
import tempfile
from pathlib import Path
from ps3toolbox.core.keys import (
    SEGMENT_SIZE, NUM_CHILD_SEGMENTS, META_ENTRY_SIZE,
    PS2_PLACEHOLDER_KLIC, PS2_PLACEHOLDER_CID, get_base_keys
)
from ps3toolbox.core.crypto import derive_keys, aes128_cbc_encrypt, calculate_sha1
from ps3toolbox.core.iso import validate_iso, pad_iso_to_boundary
from ps3toolbox.ps2.header import build_ps2_header
from ps3toolbox.ps2.limg import add_limg_header
from ps3toolbox.utils.progress import ProgressCallback


def encrypt_ps2_iso(
    iso_path: Path,
    output_path: Path,
    mode: str = 'cex',
    content_id: str | None = None,
    disc_num: int = 1,
    progress_callback: ProgressCallback | None = None
) -> None:
    """Encrypt PS2 ISO to .BIN.ENC format.

    Args:
        iso_path: Path to input PS2 ISO file
        output_path: Path to output encrypted .BIN.ENC file
        mode: Console mode ('cex' for retail, 'dex' for debug)
        content_id: Content ID string (uses placeholder if None)
        disc_num: Disc number for multi-disc games (1-9)
        progress_callback: Optional progress callback function
    """
    if not 1 <= disc_num <= 9:
        raise ValueError(f"Disc number must be 1-9, got {disc_num}")

    validate_iso(iso_path)

    temp_iso = None
    try:
        temp_fd, temp_iso_path = tempfile.mkstemp(suffix='.iso', prefix='ps2enc_')
        os.close(temp_fd)
        temp_iso = Path(temp_iso_path)

        shutil.copy2(iso_path, temp_iso)

        original_size = temp_iso.stat().st_size
        pad_iso_to_boundary(temp_iso)
        final_size = add_limg_header(temp_iso)

        base_data_key, base_meta_key = get_base_keys(mode)
        data_key, meta_key = derive_keys(base_data_key, base_meta_key, PS2_PLACEHOLDER_KLIC)

        zero_iv = bytes(16)
        cid = content_id or PS2_PLACEHOLDER_CID
        header = build_ps2_header(cid, "ISO.BIN.ENC", final_size)

        disc_num_encoded = (disc_num - 1) << 24

        with open(output_path, 'wb') as out_f, open(temp_iso, 'rb') as in_f:
            out_f.write(header)

            segment_number = 0
            bytes_processed = 0

            while True:
                data_chunk = in_f.read(SEGMENT_SIZE * NUM_CHILD_SEGMENTS)
                if not data_chunk:
                    break

                actual_segments = (len(data_chunk) + SEGMENT_SIZE - 1) // SEGMENT_SIZE
                if len(data_chunk) % SEGMENT_SIZE:
                    data_chunk += b'\x00' * (actual_segments * SEGMENT_SIZE - len(data_chunk))

                meta_buffer = bytearray(SEGMENT_SIZE)
                encrypted_data = bytearray()

                for i in range(actual_segments):
                    segment_start = i * SEGMENT_SIZE
                    segment_end = segment_start + SEGMENT_SIZE
                    segment_data = data_chunk[segment_start:segment_end]

                    encrypted_segment = aes128_cbc_encrypt(data_key, zero_iv, segment_data)
                    encrypted_data.extend(encrypted_segment)

                    hash_value = calculate_sha1(encrypted_segment)
                    meta_offset = i * META_ENTRY_SIZE
                    meta_buffer[meta_offset:meta_offset + 20] = hash_value
                    struct.pack_into('>I', meta_buffer, meta_offset + 0x14, disc_num_encoded | segment_number)
                    segment_number += 1

                encrypted_meta = aes128_cbc_encrypt(meta_key, zero_iv, bytes(meta_buffer))

                out_f.write(encrypted_meta)
                out_f.write(encrypted_data)

                bytes_processed += len(data_chunk)
                if progress_callback:
                    progress_callback(bytes_processed, final_size)

    finally:
        if temp_iso and temp_iso.exists():
            temp_iso.unlink()
