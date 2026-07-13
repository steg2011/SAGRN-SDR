"""Session auth for the admin dashboard.

Signed-cookie sessions using stdlib HMAC only (no extra dependencies).
The password and signing secret come from ADMIN_PASSWORD / ADMIN_SECRET_KEY.
"""
import hashlib
import hmac
import os
import time
from typing import Dict, Tuple

from fastapi import Request

SESSION_COOKIE = "sagrn_admin_session"
SESSION_TTL_SECONDS = 12 * 3600

# Simple in-memory login rate limiting: ip -> (window_start, attempts)
MAX_ATTEMPTS = 10
ATTEMPT_WINDOW_SECONDS = 15 * 60
_login_attempts: Dict[str, Tuple[float, int]] = {}


def _secret() -> bytes:
    key = os.environ.get("ADMIN_SECRET_KEY", "")
    if not key:
        raise RuntimeError("ADMIN_SECRET_KEY is not set")
    return key.encode()


def check_password(candidate: str) -> bool:
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def create_session_token() -> str:
    expires = str(int(time.time()) + SESSION_TTL_SECONDS)
    sig = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def verify_session_token(token: str) -> bool:
    try:
        expires, sig = token.split(".", 1)
        expected = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return int(expires) > time.time()
    except (ValueError, RuntimeError):
        return False


def client_ip(request: Request) -> str:
    return (
        request.headers.get("cf-connecting-ip")
        or (request.client.host if request.client else "unknown")
    )


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    return bool(token) and verify_session_token(token)


def register_login_attempt(ip: str) -> bool:
    """Record a login attempt. Returns False if the IP is rate limited."""
    now = time.time()
    window_start, attempts = _login_attempts.get(ip, (now, 0))
    if now - window_start > ATTEMPT_WINDOW_SECONDS:
        window_start, attempts = now, 0
    attempts += 1
    _login_attempts[ip] = (window_start, attempts)
    return attempts <= MAX_ATTEMPTS


def clear_login_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)
