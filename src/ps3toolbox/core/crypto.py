"""Low-level cryptographic operations."""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from hashlib import sha1


def aes128_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """Encrypt data using AES-128-CBC."""
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def aes128_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """Decrypt data using AES-128-CBC."""
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


def derive_keys(base_data_key: bytes, base_meta_key: bytes, klicensee: bytes) -> tuple[bytes, bytes]:
    """Derive actual encryption keys from base keys and klicensee."""
    zero_iv = bytes(16)

    derived_data_key = aes128_cbc_encrypt(base_data_key, zero_iv, klicensee)
    derived_meta_key = aes128_cbc_encrypt(base_meta_key, zero_iv, klicensee)

    return derived_data_key, derived_meta_key


def calculate_sha1(data: bytes) -> bytes:
    """Calculate SHA-1 hash of data."""
    return sha1(data).digest()


def calculate_omac(data: bytes, key: bytes) -> bytes:
    """Calculate OMAC (CMAC) for NPD authentication."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    running = bytearray(16)

    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    worthless = bytearray(encryptor.update(bytes(running)) + encryptor.finalize())
    _rol1(worthless)

    offset = 0
    if len(data) > 16:
        for offset in range(0, len(data) - 16, 16):
            hash_block = bytearray(16)
            for j in range(16):
                hash_block[j] = running[j] ^ data[offset + j]

            cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
            encryptor = cipher.encryptor()
            running = bytearray(encryptor.update(bytes(hash_block)) + encryptor.finalize())

    overrun = len(data) % 16
    if overrun == 0:
        overrun = 16

    hash_block = bytearray(16)
    hash_block[:overrun] = data[offset:offset + overrun]

    if overrun != 16:
        hash_block[overrun] = 0x80
        _rol1(worthless)

    for j in range(16):
        hash_block[j] ^= running[j] ^ worthless[j]

    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(bytes(hash_block)) + encryptor.finalize()


def _rol1(data: bytearray) -> None:
    """Rotate left by 1 bit with Galois field XOR (in-place)."""
    xor_value = 0x87 if (data[0] & 0x80) else 0

    for i in range(15):
        data[i] = ((data[i] << 1) | (data[i + 1] >> 7)) & 0xFF

    data[15] = ((data[15] << 1) ^ xor_value) & 0xFF
