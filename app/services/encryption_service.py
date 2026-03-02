"""
Encryption service for securing sensitive data like cloud credentials.
Uses Fernet (symmetric encryption) with a key derived from environment or auto-generated.
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
ENCRYPTION_KEY_PATH = os.path.join(DB_DIR, ".encryption_key")


class EncryptionService:
    """Service for encrypting/decrypting sensitive data."""

    def __init__(self):
        self.fernet = self._initialize_fernet()

    def _initialize_fernet(self):
        """Initialize Fernet cipher with persistent key."""
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            logger.error("cryptography package not installed. Encryption disabled!")
            return None

        os.makedirs(DB_DIR, exist_ok=True)

        # Try to get key from environment first
        key = os.getenv("ENCRYPTION_KEY")
        
        if not key:
            # Check for persisted key
            if os.path.exists(ENCRYPTION_KEY_PATH):
                with open(ENCRYPTION_KEY_PATH, "rb") as f:
                    key = f.read().decode('utf-8')
                logger.info("Loaded encryption key from file")
            else:
                # Generate new key
                key = Fernet.generate_key().decode('utf-8')
                with open(ENCRYPTION_KEY_PATH, "wb") as f:
                    f.write(key.encode('utf-8'))
                os.chmod(ENCRYPTION_KEY_PATH, 0o600)  # Restrict permissions
                logger.warning(
                    "Generated new encryption key. Store this securely! "
                    "If lost, encrypted data cannot be recovered."
                )

        return Fernet(key.encode('utf-8'))

    def encrypt(self, plaintext: str) -> Optional[str]:
        """
        Encrypt a string.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64-encoded), or None if encryption fails
        """
        if not self.fernet:
            logger.warning("Encryption not available, storing plaintext (INSECURE!)")
            return plaintext

        try:
            encrypted_bytes = self.fernet.encrypt(plaintext.encode('utf-8'))
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return None

    def decrypt(self, ciphertext: str) -> Optional[str]:
        """
        Decrypt a string.
        
        Args:
            ciphertext: Encrypted string (base64-encoded)
            
        Returns:
            Decrypted string, or None if decryption fails
        """
        if not self.fernet:
            logger.warning("Encryption not available, returning ciphertext as-is")
            return ciphertext

        try:
            decrypted_bytes = self.fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            # Might be plaintext from before encryption was enabled
            logger.warning(f"Decryption failed, treating as plaintext: {e}")
            return ciphertext

    def is_available(self) -> bool:
        """Check if encryption is available."""
        return self.fernet is not None
