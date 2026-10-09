from __future__ import annotations

import hashlib
import ipaddress
import secrets
import socket
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AppError


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise AppError(503, "ENCRYPTION_NOT_CONFIGURED", "Local encryption key is not configured.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise AppError(503, "ENCRYPTION_NOT_CONFIGURED", "Local encryption key is invalid.") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise AppError(503, "SECRET_DECRYPTION_FAILED", "Stored API key could not be decrypted.") from exc


def new_confirmation_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_external_https_url(url: str) -> str:
    """Reject local/private destinations before backend-initiated AI requests."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AppError(422, "INVALID_PROVIDER_URL", "AI base URL must be a public HTTPS URL.")
    if parsed.port not in (None, 443):
        raise AppError(422, "INVALID_PROVIDER_URL", "AI base URL must use the standard HTTPS port.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AppError(422, "INVALID_PROVIDER_URL", "AI provider hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise AppError(422, "INVALID_PROVIDER_URL", "AI provider must resolve to a public address.")
    return url.rstrip("/")
