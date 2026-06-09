from __future__ import annotations

from .common import AuthError


class AuthManager:
    def __init__(self, token: str):
        self._token = token or ""

    def require_token(self, provided_token: str | None) -> None:
        if not self._token:
            raise AuthError("COLAB_MCP_TOKEN is not configured on the server")
        if not provided_token or provided_token != self._token:
            raise AuthError("Invalid or missing token")

