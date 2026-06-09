from __future__ import annotations

from enum import IntEnum

from .common import ConfirmationRequiredError, PermissionError


class PermissionProfile(IntEnum):
    READ_ONLY = 1
    DEVELOPER = 2
    FULL_CONTROL = 3

    @classmethod
    def parse(cls, value: str) -> "PermissionProfile":
        normalized = value.strip().upper()
        try:
            return cls[normalized]
        except KeyError as exc:
            raise PermissionError(f"Unsupported permission profile: {value}") from exc


class PermissionManager:
    def __init__(self, current_profile: str):
        self.profile = PermissionProfile.parse(current_profile)

    def require(self, minimum: PermissionProfile) -> None:
        if self.profile < minimum:
            raise PermissionError(
                f"Operation requires {minimum.name}; current profile is {self.profile.name}",
                {"required": minimum.name, "current": self.profile.name},
            )

    def require_confirm(self, confirm: bool, *, reason: str | None = None) -> None:
        if not confirm:
            raise ConfirmationRequiredError(reason or "This operation requires confirm=true")

