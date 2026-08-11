import json
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class CredentialEncryptor:
    SALT_SIZE = 16
    PBKDF2_ITERATIONS = 100_000

    @classmethod
    def derive_key(cls, passphrase: str, salt: bytes) -> bytes:
        """
        Derive a 32-byte key from a passphrase and salt using PBKDF2.
        """
        if not passphrase:
            raise ValueError("Encryption passphrase cannot be empty.")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=cls.PBKDF2_ITERATIONS,
        )
        key_bytes = kdf.derive(passphrase.encode("utf-8"))
        return base64.urlsafe_b64encode(key_bytes)

    @classmethod
    def encrypt_credentials(cls, data: dict, passphrase: str) -> bytes:
        """
        Encrypt a credentials dictionary to bytes using a derived Fernet key.
        Prepend a random 16-byte salt to the ciphertext.
        """
        salt = os.urandom(cls.SALT_SIZE)
        key = cls.derive_key(passphrase, salt)
        fernet = Fernet(key)
        
        json_bytes = json.dumps(data).encode("utf-8")
        ciphertext = fernet.encrypt(json_bytes)
        
        return salt + ciphertext

    @classmethod
    def decrypt_credentials(cls, encrypted_data: bytes, passphrase: str) -> dict:
        """
        Decrypt credentials bytes using a derived Fernet key.
        Extract the salt from the first 16 bytes.
        """
        if len(encrypted_data) < cls.SALT_SIZE:
            raise ValueError("Invalid encrypted data: too short.")
            
        salt = encrypted_data[:cls.SALT_SIZE]
        ciphertext = encrypted_data[cls.SALT_SIZE:]
        
        key = cls.derive_key(passphrase, salt)
        fernet = Fernet(key)
        
        decrypted_bytes = fernet.decrypt(ciphertext)
        return json.loads(decrypted_bytes.decode("utf-8"))
