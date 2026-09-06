"""Password Policy Service.
Validates password strength and rejects weak/common passwords.
"""

import re
from typing import Tuple


class PasswordPolicyService:
    """Service enforcing password security policy and complexity rules."""

    MIN_LENGTH = 8
    COMMON_PASSWORDS = {
        '12345678', '123456789', 'password', 'password123', 'admin123',
        'qwerty123', 'haslo123', 'zaq1@WSX', 'administrator', 'root1234'
    }

    @classmethod
    def validate_password(cls, password: str) -> Tuple[bool, str]:
        """Validate password against security rules.
        
        Rules:
        - Minimum 8 characters.
        - Must contain at least one letter and at least one digit.
        - Must not be a commonly known weak password.
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not password or not isinstance(password, str):
            return False, "Hasło nie może być puste."

        if len(password) < cls.MIN_LENGTH:
            return False, f"Hasło musi mieć co najmniej {cls.MIN_LENGTH} znaków."

        if password.lower() in cls.COMMON_PASSWORDS:
            return False, "Hasło jest zbyt proste i powszechne. Wybierz bezpieczniejsze hasło."

        if not re.search(r'[a-zA-Z]', password):
            return False, "Hasło musi zawierać co najmniej jedną literę."

        if not re.search(r'\d', password):
            return False, "Hasło musi zawierać co najmniej jedną cyfrę."

        return True, ""


# Singleton instance
password_policy_service = PasswordPolicyService()
