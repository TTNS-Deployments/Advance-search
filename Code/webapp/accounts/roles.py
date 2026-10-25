"""Roles and what each may do. The demo sign-in stores the chosen role in the signed session."""

from __future__ import annotations

from dataclasses import dataclass

ADMIN, USER = "Admin", "User"
ALL_ROLES = (ADMIN, USER)
ROLE_DESCRIPTIONS = {
    ADMIN: "Upload and manage documents, change settings, and search",
    USER: "Search and open documents",
}

PERMISSIONS = {
    "search": {ADMIN, USER},
    "open_documents": {ADMIN, USER},
    "manage_documents": {ADMIN},
    "edit_settings": {ADMIN},
}


@dataclass
class User:
    role: str
    signed_in_at: str = ""
    is_authenticated: bool = True

    @property
    def name(self) -> str:
        return self.role

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN

    def can(self, permission: str) -> bool:
        return self.role in PERMISSIONS.get(permission, set())

    def to_session(self) -> dict:
        return {"role": self.role, "signed_in_at": self.signed_in_at}

    @classmethod
    def from_session(cls, data) -> "User | None":
        if not isinstance(data, dict) or data.get("role") not in ALL_ROLES:
            return None
        return cls(role=data["role"], signed_in_at=str(data.get("signed_in_at", "")))


class AnonymousUser:
    is_authenticated = False
    is_admin = False
    role = name = ""

    def can(self, permission: str) -> bool:
        return False
