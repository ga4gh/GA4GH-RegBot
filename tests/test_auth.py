"""Authentication token and configuration tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi import HTTPException
from src.api.auth import (
    AuthUser,
    auth_settings,
    create_session_token,
    guest_viewer,
    parse_session_token,
)

AUTH_ENV = {
    "REGBOT_SESSION_SECRET": "test-session-secret-at-least-32-characters-long",
    "REGBOT_ADMIN_USERNAME": "admin-user",
    "REGBOT_ADMIN_PASSWORD": "admin-password-long",
    "REGBOT_VIEWER_USERNAME": "viewer-user",
    "REGBOT_VIEWER_PASSWORD": "viewer-password-long",
    "REGBOT_ALLOW_GUEST_VIEWER": "1",
}


class TestAuthConfiguration(unittest.TestCase):
    def test_missing_secret_uses_a_stable_per_process_secret(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            first = auth_settings()
            second = auth_settings()
            token = create_session_token(AuthUser(username="guest", role="viewer"))
            parsed = parse_session_token(token)
        self.assertGreaterEqual(len(first.secret), 32)
        self.assertEqual(first.secret, second.secret)
        self.assertEqual(parsed, AuthUser(username="guest", role="viewer"))

    def test_explicit_short_secret_fails_closed(self) -> None:
        env = {"REGBOT_SESSION_SECRET": "short"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(HTTPException) as raised:
                auth_settings()
        self.assertEqual(raised.exception.status_code, 503)

    def test_short_password_fails_closed(self) -> None:
        env = dict(AUTH_ENV, REGBOT_ADMIN_PASSWORD="short")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(HTTPException) as raised:
                auth_settings()
        self.assertEqual(raised.exception.status_code, 503)

    def test_guest_viewer_needs_only_a_session_secret(self) -> None:
        env = {"REGBOT_SESSION_SECRET": AUTH_ENV["REGBOT_SESSION_SECRET"]}
        with mock.patch.dict(os.environ, env, clear=True):
            settings = auth_settings()
            user = guest_viewer()
        self.assertTrue(settings.allow_guest_viewer)
        self.assertEqual(settings.users, {})
        self.assertEqual(user, AuthUser(username="guest", role="viewer"))

    def test_disabled_guest_access_without_accounts_fails_closed(self) -> None:
        env = {
            "REGBOT_SESSION_SECRET": AUTH_ENV["REGBOT_SESSION_SECRET"],
            "REGBOT_ALLOW_GUEST_VIEWER": "0",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(HTTPException) as raised:
                auth_settings()
        self.assertEqual(raised.exception.status_code, 503)

    def test_disabled_guest_access_rejects_guest_entry(self) -> None:
        env = dict(AUTH_ENV, REGBOT_ALLOW_GUEST_VIEWER="0")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(HTTPException) as raised:
                guest_viewer()
        self.assertEqual(raised.exception.status_code, 403)


class TestSessionTokens(unittest.TestCase):
    def test_valid_signed_token_round_trips(self) -> None:
        with mock.patch.dict(os.environ, AUTH_ENV, clear=True):
            token = create_session_token(AuthUser(username="viewer-user", role="viewer"))
            parsed = parse_session_token(token)
        self.assertEqual(parsed, AuthUser(username="viewer-user", role="viewer"))

    def test_tampered_token_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, AUTH_ENV, clear=True):
            token = create_session_token(AuthUser(username="admin-user", role="admin"))
            payload, signature = token.split(".", 1)
            replacement = "A" if signature[-1] != "A" else "B"
            self.assertIsNone(parse_session_token(f"{payload}.{signature[:-1]}{replacement}"))

    def test_expired_token_is_rejected(self) -> None:
        with (
            mock.patch.dict(os.environ, AUTH_ENV, clear=True),
            mock.patch("src.api.auth.time.time", return_value=1_000),
        ):
            token = create_session_token(AuthUser(username="viewer-user", role="viewer"))
        with (
            mock.patch.dict(os.environ, AUTH_ENV, clear=True),
            mock.patch("src.api.auth.time.time", return_value=1_000 + 8 * 60 * 60 + 1),
        ):
            self.assertIsNone(parse_session_token(token))

    def test_guest_token_is_rejected_after_guest_access_is_disabled(self) -> None:
        with mock.patch.dict(os.environ, AUTH_ENV, clear=True):
            token = create_session_token(AuthUser(username="guest", role="viewer"))
        disabled_env = dict(AUTH_ENV, REGBOT_ALLOW_GUEST_VIEWER="0")
        with mock.patch.dict(os.environ, disabled_env, clear=True):
            self.assertIsNone(parse_session_token(token))


if __name__ == "__main__":
    unittest.main()
