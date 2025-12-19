"""PS2 ISO encryption to .BIN.ENC format."""

import struct
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
    progress_callback: ProgressCallback | None = None
) -> None:
    """Encrypt PS2 ISO to .BIN.ENC format."""
    validate_iso(iso_path)

    original_size = iso_path.stat().st_size
    pad_iso_to_boundary(iso_path)
    final_size = add_limg_header(iso_path)

    base_data_key, base_meta_key = get_base_keys(mode)
    data_key, meta_key = derive_keys(base_data_key, base_meta_key, PS2_PLACEHOLDER_KLIC)

    zero_iv = bytes(16)
    cid = content_id or PS2_PLACEHOLDER_CID
    header = build_ps2_header(cid, "ISO.BIN.ENC", final_size)

    with open(output_path, 'wb') as out_f, open(iso_path, 'rb') as in_f:
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
                struct.pack_into('>I', meta_buffer, meta_offset + 0x14, segment_number)
                segment_number += 1

            encrypted_meta = aes128_cbc_encrypt(meta_key, zero_iv, bytes(meta_buffer))

            out_f.write(encrypted_meta)
            out_f.write(encrypted_data)

            bytes_processed += len(data_chunk)
            if progress_callback:
                progress_callback(bytes_processed, final_size)

    iso_path.chmod(iso_path.stat().st_mode)
    with open(iso_path, 'r+b') as f:
        f.truncate(original_size)
