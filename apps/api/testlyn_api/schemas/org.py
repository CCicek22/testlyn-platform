from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class OrgCreate(BaseModel):
    name: str


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "member"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in {"owner", "admin", "member"}:
            raise ValueError("role must be owner, admin, or member")
        return v


class InviteOut(BaseModel):
    org_id: uuid.UUID
    email: str
    role: str
    message: str = "Invite recorded (email delivery stubbed for Phase 1)"
