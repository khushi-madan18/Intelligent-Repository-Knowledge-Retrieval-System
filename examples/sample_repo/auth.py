"""Small sample auth module."""

import hashlib


class User:
    """Application user."""

    def __init__(self, email: str, password_hash: str) -> None:
        self.email = email
        self.password_hash = password_hash


def hash_password(password: str) -> str:
    """Hash a plain text password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


async def authenticate(email: str, password: str) -> bool:
    """Validate user credentials."""
    return bool(email and password)
