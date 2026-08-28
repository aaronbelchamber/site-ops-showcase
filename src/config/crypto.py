import json
import os
import struct
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class CredentialEncryptor:
    SALT_SIZE = 16
    # Marks the versioned format (below), which embeds its own iteration count
    # so PBKDF2_ITERATIONS can be raised in the future without breaking old
    # files. Chosen to never collide with a random 16-byte legacy salt.
    MAGIC = b"WPSMv2:"

    # Every file written before the versioned format existed used exactly this
    # iteration count, with no header -- see decrypt_credentials().
    LEGACY_PBKDF2_ITERATIONS = 100_000

    # OWASP-recommended minimum for PBKDF2-HMAC-SHA256 as of 2023 guidance.
    # Safe to raise (as this was, from the previous 100k) now that
    # src/config/loader.py caches decrypted credentials -- this runs ~once per
    # process, not per request. The iteration count used for a given file is
    # embedded in it at encrypt time, so raising this constant only affects
    # new writes; existing files keep decrypting at whatever count they were
    # written with (loader.py re-encrypts legacy files at the new count the
    # first time it successfully reads them).
    PBKDF2_ITERATIONS = 600_000

    @classmethod
    def derive_key(cls, passphrase: str, salt: bytes, iterations: int = None) -> bytes:
        """
        Derive a 32-byte key from a passphrase and salt using PBKDF2.
        """
        if not passphrase:
            raise ValueError("Encryption passphrase cannot be empty.")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations if iterations is not None else cls.PBKDF2_ITERATIONS,
        )
        key_bytes = kdf.derive(passphrase.encode("utf-8"))
        return base64.urlsafe_b64encode(key_bytes)

    @classmethod
    def encrypt_credentials(cls, data: dict, passphrase: str) -> bytes:
        """
        Encrypt a credentials dictionary to bytes using a derived Fernet key.

        Output layout: MAGIC + iterations (4-byte big-endian uint) + 16-byte
        salt + Fernet ciphertext. Embedding the iteration count lets future
        PBKDF2_ITERATIONS bumps decrypt files written under older values.
        """
        salt = os.urandom(cls.SALT_SIZE)
        key = cls.derive_key(passphrase, salt, cls.PBKDF2_ITERATIONS)
        fernet = Fernet(key)

        json_bytes = json.dumps(data).encode("utf-8")
        ciphertext = fernet.encrypt(json_bytes)

        header = cls.MAGIC + struct.pack(">I", cls.PBKDF2_ITERATIONS)
        return header + salt + ciphertext

    @classmethod
    def is_legacy_format(cls, encrypted_data: bytes) -> bool:
        """True if `encrypted_data` predates the versioned (iterations-embedded) format."""
        return not encrypted_data.startswith(cls.MAGIC)

    @classmethod
    def decrypt_credentials(cls, encrypted_data: bytes, passphrase: str) -> dict:
        """
        Decrypt credentials bytes using a derived Fernet key.

        Handles both the current versioned format (MAGIC + iterations + salt
        + ciphertext) and the legacy format written before it existed (bare
        salt + ciphertext, always at LEGACY_PBKDF2_ITERATIONS).
        """
        if cls.is_legacy_format(encrypted_data):
            if len(encrypted_data) < cls.SALT_SIZE:
                raise ValueError("Invalid encrypted data: too short.")
            iterations = cls.LEGACY_PBKDF2_ITERATIONS
            salt = encrypted_data[:cls.SALT_SIZE]
            ciphertext = encrypted_data[cls.SALT_SIZE:]
        else:
            header_size = len(cls.MAGIC) + 4
            if len(encrypted_data) < header_size + cls.SALT_SIZE:
                raise ValueError("Invalid encrypted data: too short.")
            iterations = struct.unpack(">I", encrypted_data[len(cls.MAGIC):header_size])[0]
            salt = encrypted_data[header_size:header_size + cls.SALT_SIZE]
            ciphertext = encrypted_data[header_size + cls.SALT_SIZE:]

        key = cls.derive_key(passphrase, salt, iterations)
        fernet = Fernet(key)

        decrypted_bytes = fernet.decrypt(ciphertext)
        return json.loads(decrypted_bytes.decode("utf-8"))
