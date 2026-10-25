import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bill import ReadMethodLiteral


class BillMeterReadingBase(BaseModel):
    pod_code: str | None = Field(default=None, max_length=40)
    meter_serial: str | None = Field(default=None, max_length=50)
    grid_operator_code: str | None = Field(default=None, max_length=40)
    register: str | None = Field(default=None, max_length=20)
    index_previous: Decimal | None = None
    index_current: Decimal | None = None
    multiplier: Decimal | None = None
    read_method: ReadMethodLiteral
    read_on: date | None = None
    quantity: Decimal


class BillMeterReadingCreate(BillMeterReadingBase):
    pass


class BillMeterReadingRead(BillMeterReadingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
