from __future__ import annotations

import json
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


class LocalUserStore:
    def __init__(self, path: Path):
        self.path = path
        self.hasher = PasswordHasher()

    def ensure_admin(self, email: str, password: str) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": "1.0",
            "users": [
                {
                    "email": email.strip().lower(),
                    "displayName": "MCI Demo Underwriter",
                    "role": "underwriter",
                    "passwordHash": self.hasher.hash(password),
                    "active": True,
                }
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def authenticate(self, email: str, password: str) -> dict | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        normalized = email.strip().lower()
        for user in payload.get("users", []):
            if user.get("email") != normalized or not user.get("active", False):
                continue
            try:
                if self.hasher.verify(user["passwordHash"], password):
                    return {
                        "email": user["email"],
                        "displayName": user.get("displayName", user["email"]),
                        "role": user.get("role", "underwriter"),
                    }
            except VerifyMismatchError:
                return None
        return None


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_minutes: int = 10):
        self.attempts = attempts
        self.window = timedelta(minutes=window_minutes)
        self._entries: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def allowed(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            entries = self._entries[key]
            while entries and now - entries[0] > self.window:
                entries.popleft()
            return len(entries) < self.attempts

    def failed(self, key: str) -> None:
        with self._lock:
            self._entries[key].append(datetime.now(timezone.utc))

    def clear(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


def csrf_token(session: dict) -> str:
    token = session.get("csrfToken")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrfToken"] = token
    return token


def valid_csrf(session: dict, supplied: str) -> bool:
    expected = session.get("csrfToken", "")
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))

