from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class OrgMembershipOut(BaseModel):
    org_id: uuid.UUID
    role: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    avatar_url: str | None
    created_at: datetime
    memberships: list[OrgMembershipOut] = []

    model_config = {"from_attributes": True}
