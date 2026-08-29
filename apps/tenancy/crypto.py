"""Symmetric encryption for tenant secrets.

The key comes from settings, which each environment sources as it sees fit --
dev has a throwaway default, production requires it from the environment and
refuses to boot without one. Never in the database, never in the repo.

Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = getattr(settings, "SECRETS_KEY", None)
    if not key:
        raise RuntimeError(
            "SECRETS_KEY is not configured. Tenant secrets cannot be read or "
            "written without it."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # A rotated or wrong key must not look like an empty credential --
        # that would silently send unauthenticated requests to Meta.
        raise RuntimeError("Could not decrypt a tenant secret. Wrong SECRETS_KEY?")


def mask(value: str) -> str:
    """What the portal is allowed to show. Never the secret itself."""
    if not value:
        return ""
    return "\u2022" * 8 + value[-4:]
