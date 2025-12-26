"""Tests for cryptographic operations."""

from ps3toolbox.core.crypto import aes128_cbc_decrypt
from ps3toolbox.core.crypto import aes128_cbc_encrypt
from ps3toolbox.core.crypto import calculate_omac
from ps3toolbox.core.crypto import calculate_sha1
from ps3toolbox.core.crypto import derive_keys
from ps3toolbox.core.keys import PS2_KEY_CEX_DATA
from ps3toolbox.core.keys import PS2_KEY_CEX_META
from ps3toolbox.core.keys import PS2_PLACEHOLDER_KLIC


def test_aes_encryption_decryption_roundtrip():
    """Test AES encryption and decryption produce original data."""
    key = bytes(16)
    iv = bytes(16)
    original_data = b"Test data here!!" * 16

    encrypted = aes128_cbc_encrypt(key, iv, original_data)
    decrypted = aes128_cbc_decrypt(key, iv, encrypted)

    assert decrypted == original_data
    assert encrypted != original_data


def test_derive_keys():
    """Test key derivation produces deterministic results."""
    data_key, meta_key = derive_keys(PS2_KEY_CEX_DATA, PS2_KEY_CEX_META, PS2_PLACEHOLDER_KLIC)

    assert len(data_key) == 16
    assert len(meta_key) == 16
    assert data_key != PS2_KEY_CEX_DATA
    assert meta_key != PS2_KEY_CEX_META


def test_derive_keys_deterministic():
    """Test key derivation is deterministic."""
    data_key1, meta_key1 = derive_keys(PS2_KEY_CEX_DATA, PS2_KEY_CEX_META, PS2_PLACEHOLDER_KLIC)

    data_key2, meta_key2 = derive_keys(PS2_KEY_CEX_DATA, PS2_KEY_CEX_META, PS2_PLACEHOLDER_KLIC)

    assert data_key1 == data_key2
    assert meta_key1 == meta_key2


def test_calculate_sha1():
    """Test SHA-1 calculation."""
    data = b"test data"
    hash_result = calculate_sha1(data)

    assert len(hash_result) == 20
    assert isinstance(hash_result, bytes)


def test_calculate_omac():
    """Test OMAC calculation."""
    data = b"test data for omac"
    key = bytes(16)

    omac = calculate_omac(data, key)

    assert len(omac) == 16
    assert isinstance(omac, bytes)


def test_calculate_omac_deterministic():
    """Test OMAC is deterministic."""
    data = b"test data"
    key = bytes(16)

    omac1 = calculate_omac(data, key)
    omac2 = calculate_omac(data, key)

    assert omac1 == omac2
