"""Small, dependency-free authentication and role checks for the local web app."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Literal, cast

from fastapi import Cookie, Depends, HTTPException, status

Role = Literal["admin", "viewer"]
SESSION_COOKIE = "regbot_session"
GUEST_VIEWER_USERNAME = "guest"
_EPHEMERAL_SESSION_SECRET = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class AuthUser:
    username: str
    role: Role


@dataclass(frozen=True)
class AuthSettings:
    secret: str
    users: Dict[str, tuple[str, Role]]
    session_seconds: int
    cookie_secure: bool
    allow_guest_viewer: bool


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _session_seconds() -> int:
    try:
        hours = int(os.getenv("REGBOT_SESSION_HOURS", "8"))
    except ValueError:
        hours = 8
    return max(1, min(hours, 168)) * 60 * 60


def auth_settings() -> AuthSettings:
    """Read credentials at request time so tests and deployments can inject env safely."""
    secret = os.getenv("REGBOT_SESSION_SECRET", "")
    if secret and len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured: REGBOT_SESSION_SECRET needs 32+ characters.",
        )
    if not secret:
        # A cryptographically random per-process secret keeps local/single-process installs
        # safe and usable without setup. Operators should configure a stable secret for
        # multi-worker deployments or sessions that must survive a server restart.
        secret = _EPHEMERAL_SESSION_SECRET

    allow_guest_viewer = _truthy(os.getenv("REGBOT_ALLOW_GUEST_VIEWER", "1"))
    users: Dict[str, tuple[str, Role]] = {}
    for role in ("admin", "viewer"):
        prefix = f"REGBOT_{role.upper()}"
        username = os.getenv(f"{prefix}_USERNAME", role).strip()
        password = os.getenv(f"{prefix}_PASSWORD", "")
        if not password:
            continue
        if len(password) < 12:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Authentication is not configured: {prefix}_PASSWORD needs 12+ characters.",
            )
        if (
            not username
            or username in users
            or (allow_guest_viewer and username == GUEST_VIEWER_USERNAME)
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Authentication usernames must be non-empty and distinct; "
                    f"'{GUEST_VIEWER_USERNAME}' is reserved while guest viewer access is enabled."
                ),
            )
        users[username] = (password, cast(Role, role))

    if not users and not allow_guest_viewer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Authentication is not configured: enable guest viewer access or set at least "
                "one RegBot account password."
            ),
        )
    return AuthSettings(
        secret=secret,
        users=users,
        session_seconds=_session_seconds(),
        cookie_secure=_truthy(os.getenv("REGBOT_COOKIE_SECURE", "0")),
        allow_guest_viewer=allow_guest_viewer,
    )


def authenticate(username: str, password: str) -> AuthUser | None:
    """Constant-time credential comparison with a generic failure result."""
    settings = auth_settings()
    matched: AuthUser | None = None
    for candidate, (expected_password, role) in settings.users.items():
        username_ok = hmac.compare_digest(username.encode(), candidate.encode())
        password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
        if username_ok and password_ok:
            matched = AuthUser(username=candidate, role=role)
    return matched


def guest_viewer() -> AuthUser:
    """Return the public read-only identity when the operator permits guest access."""
    if not auth_settings().allow_guest_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest viewer access is disabled.",
        )
    return AuthUser(username=GUEST_VIEWER_USERNAME, role="viewer")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def create_session_token(user: AuthUser) -> str:
    settings = auth_settings()
    now = int(time.time())
    payload = _b64encode(
        json.dumps(
            {
                "sub": user.username,
                "role": user.role,
                "iat": now,
                "exp": now + settings.session_seconds,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    signature = _b64encode(
        hmac.new(settings.secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}"


def parse_session_token(token: str) -> AuthUser | None:
    """Verify signature, expiry, configured account, and role on every request."""
    try:
        payload, signature = token.split(".", 1)
        settings = auth_settings()
        expected = _b64encode(
            hmac.new(settings.secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_b64decode(payload))
        username = str(data["sub"])
        role = str(data["role"])
        if int(data["exp"]) <= int(time.time()):
            return None
        if username == GUEST_VIEWER_USERNAME and role == "viewer" and settings.allow_guest_viewer:
            return AuthUser(username=username, role="viewer")
        account = settings.users.get(username)
        if not account or role not in {"admin", "viewer"} or account[1] != role:
            return None
        return AuthUser(username=username, role=cast(Role, role))
    except (
        binascii.Error,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None


def require_user(regbot_session: str | None = Cookie(default=None)) -> AuthUser:
    user = parse_session_token(regbot_session) if regbot_session else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def require_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator permission required.",
        )
    return user
