import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

# No Create or Update model: the request body is a file, and every field below
# is derived from the bytes or from who sent them. Nothing here is client-set,
# which is the point — filename is the only thing the caller controls and it is
# display-only.


class BillDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    place_id: uuid.UUID
    sha256: str
    filename: str
    media_type: str
    byte_size: int
    page_count: int | None
    uploaded_by: uuid.UUID
    created_at: datetime
