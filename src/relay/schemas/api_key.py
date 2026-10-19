import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rpm_limit: int = Field(default=30, ge=1, le=10_000)
    monthly_budget_usd: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str
    rpm_limit: int
    monthly_budget_usd: Decimal | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str
