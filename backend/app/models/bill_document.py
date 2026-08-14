import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BillDocument(Base):
    """The bytes a bill came from, content-addressed by SHA-256.

    ``(place_id, sha256)`` is unique, which is what makes re-uploading the same
    file idempotent: the second POST returns the existing row with 200 instead
    of creating a duplicate and paying for a second extraction. The digest is
    the same one ``ingest/energlens_ingest/claude_extractor.py`` already caches
    by — this is the server-side half of a cache that has proved itself.

    Uniqueness is **per place, not global**, deliberately. A global constraint
    would let one user learn that another has already uploaded a given file by
    watching for a 200 where they expected a 201.
    """

    __tablename__ = "bill_documents"
    __table_args__ = (
        UniqueConstraint("place_id", "sha256", name="uq_bill_documents_place_sha"),
        Index("ix_bill_documents_place_id", "place_id"),
        # The rate limit counts a user's uploads since UTC midnight.
        Index("ix_bill_documents_uploaded_by_created", "uploaded_by", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE")
    )
    sha256: Mapped[str] = mapped_column(String(64))
    # As uploaded, for display only. Never used to build a path — storage_key is
    # derived from the digest precisely so a hostile filename cannot escape it.
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    # NULL when the PDF could not be parsed. Storing it and understanding it are
    # separate concerns; the extraction agent can still try.
    page_count: Mapped[int | None] = mapped_column(Integer)
    # Opaque to everything but the storage backend: "{place_id}/{sha256}.pdf".
    storage_key: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    place: Mapped["Place"] = relationship(back_populates="documents")  # noqa: F821
