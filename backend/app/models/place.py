import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Place(Base):
    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    address_line1: Mapped[str] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str] = mapped_column(String(20))
    country_code: Mapped[str] = mapped_column(String(2))
    currency_code: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="places")  # noqa: F821
    bills: Mapped[list["Bill"]] = relationship(  # noqa: F821
        back_populates="place", cascade="all, delete-orphan"
    )
    documents: Mapped[list["BillDocument"]] = relationship(  # noqa: F821
        back_populates="place", cascade="all, delete-orphan"
    )
