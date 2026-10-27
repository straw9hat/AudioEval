"""Password hashing, user store, and login rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time

ITERATIONS = 600_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"pbkdf2_sha256${iterations}${b64(salt)}${b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt, digest = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), pad(salt), int(iters))
        return hmac.compare_digest(candidate, pad(digest))
    except (ValueError, TypeError):
        return False


def load_users() -> dict[str, str]:
    """AUDIOEVAL_USERS='user1:<hash>,user2:<hash>' with hashes from `audioeval hash-password`."""
    users = {}
    for entry in os.environ.get("AUDIOEVAL_USERS", "").split(","):
        entry = entry.strip()
        if ":" in entry:
            name, encoded = entry.split(":", 1)
            users[name.strip()] = encoded.strip()
    return users


# Verified against when the username is unknown so response time does not reveal valid users.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16), iterations=ITERATIONS)


class LoginLimiter:
    def __init__(self, max_failures: int = 5, window_s: int = 900):
        self.max_failures = max_failures
        self.window_s = window_s
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = time.time() - self.window_s
        hits = [t for t in self._failures.get(key, []) if t > cutoff]
        self._failures[key] = hits
        return hits

    def blocked(self, *keys: str) -> bool:
        with self._lock:
            return any(len(self._recent(k)) >= self.max_failures for k in keys)

    def fail(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._recent(k).append(time.time())

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


def authenticate(users: dict[str, str], username: str, password: str) -> bool:
    encoded = users.get(username)
    if encoded is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, encoded)
