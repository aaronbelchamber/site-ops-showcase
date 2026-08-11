import unittest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.crypto import CredentialEncryptor

class TestCrypto(unittest.TestCase):
    def setUp(self):
        self.passphrase = "my-super-secret-key-123!"
        self.test_data = {
            "site-one": {
                "ssh_password": "ssh_password_value",
                "db_password": "db_password_value"
            },
            "site-two": {
                "ssh_private_key": "some-private-key-data",
                "db_password": "another-db-password"
            }
        }

    def test_key_derivation_is_consistent(self):
        salt = os.urandom(16)
        key1 = CredentialEncryptor.derive_key(self.passphrase, salt)
        key2 = CredentialEncryptor.derive_key(self.passphrase, salt)
        self.assertEqual(key1, key2)

    def test_key_derivation_varies_with_salt(self):
        salt1 = os.urandom(16)
        salt2 = os.urandom(16)
        key1 = CredentialEncryptor.derive_key(self.passphrase, salt1)
        key2 = CredentialEncryptor.derive_key(self.passphrase, salt2)
        self.assertNotEqual(key1, key2)

    def test_encrypt_decrypt_cycle(self):
        encrypted = CredentialEncryptor.encrypt_credentials(self.test_data, self.passphrase)
        # Ensure it's not plaintext
        self.assertNotIn(b"ssh_password_value", encrypted)
        
        # Decrypt and compare
        decrypted = CredentialEncryptor.decrypt_credentials(encrypted, self.passphrase)
        self.assertEqual(decrypted, self.test_data)

    def test_decrypt_fails_with_wrong_passphrase(self):
        encrypted = CredentialEncryptor.encrypt_credentials(self.test_data, self.passphrase)
        with self.assertRaises(Exception):
            CredentialEncryptor.decrypt_credentials(encrypted, "wrong-passphrase")

if __name__ == "__main__":
    unittest.main()
