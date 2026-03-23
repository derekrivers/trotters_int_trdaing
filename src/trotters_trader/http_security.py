from __future__ import annotations

import base64
import hmac
from http.cookies import SimpleCookie
import secrets


def is_bearer_authorized(environ: dict[str, object], auth_token: str) -> bool:
    header = str(environ.get("HTTP_AUTHORIZATION", "") or "").strip()
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False
    candidate = header.removeprefix(prefix).strip()
    if not candidate or not auth_token:
        return False
    return hmac.compare_digest(candidate, auth_token)


def is_basic_authorized(environ: dict[str, object], username: str, password: str) -> bool:
    header = str(environ.get("HTTP_AUTHORIZATION", "") or "").strip()
    prefix = "Basic "
    if not header.startswith(prefix):
        return False
    try:
        decoded = base64.b64decode(header.removeprefix(prefix).strip()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    provided_username, separator, provided_password = decoded.partition(":")
    if separator != ":":
        return False
    if not username or not password:
        return False
    return hmac.compare_digest(provided_username, username) and hmac.compare_digest(provided_password, password)


def request_actor(environ: dict[str, object]) -> str | None:
    actor = str(environ.get("HTTP_X_TROTTERS_ACTOR", "") or environ.get("HTTP_X_ACTOR", "") or "").strip()
    return actor or None


def actor_label(actor: str | None) -> str:
    return actor or "unknown"


def parse_cookies(environ: dict[str, object]) -> dict[str, str]:
    header = str(environ.get("HTTP_COOKIE", "") or "").strip()
    if not header:
        return {}
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except Exception:
        return {}
    return {key: morsel.value for key, morsel in cookie.items()}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)
