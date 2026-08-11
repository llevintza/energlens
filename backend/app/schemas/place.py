import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlaceBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address_line1: str = Field(min_length=1, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(min_length=2, max_length=2)
    currency_code: str = Field(min_length=3, max_length=3)

    @field_validator("country_code", "currency_code")
    @classmethod
    def uppercase_alpha(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.isalpha():
            raise ValueError("must contain only letters")
        return v


class PlaceCreate(PlaceBase):
    pass


class PlaceUpdate(PlaceBase):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    address_line1: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("country_code", "currency_code")
    @classmethod
    def uppercase_alpha_optional(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if not v.isalpha():
            raise ValueError("must contain only letters")
        return v


class PlaceRead(PlaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
