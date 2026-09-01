import threading
from datetime import datetime, timedelta, timezone

import jwt
import requests

DEFAULT_REFRESH_MARGIN_SECONDS = 60


class TokenProvider:

    def __init__(self, base_url, username, password,
                 refresh_margin_seconds=DEFAULT_REFRESH_MARGIN_SECONDS, timeout=10):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._margin = timedelta(seconds=refresh_margin_seconds)
        self._timeout = timeout
        self._lock = threading.Lock()
        self._token = None
        self._expires_at = None

    def token(self, force_refresh=False):
        with self._lock:
            if force_refresh or self._token is None or self._is_stale():
                self._token, self._expires_at = self._login()
            return self._token

    def authorization_header(self, force_refresh=False):
        return {"Authorization": f"Bearer {self.token(force_refresh)}"}

    def invalidate(self):
        with self._lock:
            self._token = None
            self._expires_at = None

    def _is_stale(self):
        if self._expires_at is None:
            return False
        return datetime.now(timezone.utc) >= self._expires_at - self._margin

    def _login(self):
        response = requests.post(
            f"{self._base_url}/api/auth/login",
            json={"username": self._username, "password": self._password},
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()

        token = data.get("token") or data.get("accessToken")
        if not token:
            raise RuntimeError(f"Login-i u be por s'u gjet token ne pergjigje: {data}")

        return token, _expiry_of(token, data)


def _expiry_of(token, data):
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
        exp = claims.get("exp")
        if exp:
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except (jwt.PyJWTError, TypeError, ValueError):
        pass

    seconds = data.get("expiresInSeconds")
    if seconds:
        return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))

    return None
