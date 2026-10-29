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
MAX_TRACKED_KEYS = 10_000


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt, digest = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64decode(salt), int(iters))
        return hmac.compare_digest(candidate, _b64decode(digest))
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
            if len(self._failures) > MAX_TRACKED_KEYS:
                # Many distinct usernames/IPs would otherwise grow this dict without bound.
                for key in list(self._failures):
                    if not self._recent(key):
                        del self._failures[key]
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
