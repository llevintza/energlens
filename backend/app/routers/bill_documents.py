import hashlib
import io
import logging
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import settings
from app.db import get_async_session
from app.models import Bill, BillDocument, Place, User
from app.routers.deps import get_owned_place
from app.schemas.bill_document import BillDocumentRead
from app.services.documents import purge_objects
from app.storage import StorageBackend, StorageObjectNotFound, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/places/{place_id}/bill-documents", tags=["bill-documents"]
)

PDF_MEDIA_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 64 * 1024


async def get_owned_document(
    document_id: uuid.UUID,
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> BillDocument:
    """Chained off get_owned_place, so a foreign place is already 404.

    The second half matters as much as the first: without the place check a
    document id from another account would be readable through any place the
    caller does own.
    """
    document = await session.get(BillDocument, document_id)
    if document is None or document.place_id != place.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _safe_filename(raw: str | None) -> str:
    """Keep the name for display, strip everything that makes it a path.

    Two separate hazards. It is echoed into a Content-Disposition header, so a
    newline in it would let the caller inject headers into their own download
    response. And although storage_key is built from the digest and never from
    this, a filename that survives as "../../etc/passwd" is one refactor away
    from being a path traversal.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"')
    name = name.strip().strip(".")
    return name[:255] or "document.pdf"


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail=(
            "File is larger than the "
            f"{settings.upload_max_bytes // (1024 * 1024)} MB limit"
        ),
    )


async def _read_capped(file: UploadFile) -> tuple[bytes, str]:
    """Read the upload into memory, bounded, hashing as it goes.

    This is the *memory* bound, not the ingest bound, and the difference is
    worth being precise about. FastAPI has already parsed and spooled the whole
    body before this function is reached (see app/middleware.py), so refusing
    here does not stop the bytes arriving — MaxBodySizeMiddleware does that, on
    Content-Length, before routing. What this guarantees is that no more than
    upload_max_bytes plus one chunk is ever held in RAM, whatever the client
    declared or omitted.

    The bytes are accumulated rather than streamed onward because the storage
    key is `{place_id}/{sha256}.pdf` — the key is a function of the last byte,
    so there is nothing to stream to until the whole file has been read.
    """
    # Set by the multipart parser as it wrote the spool, so it is exact and
    # already known — no need to read 10 MB back off disk to learn it is too big.
    if file.size is not None and file.size > settings.upload_max_bytes:
        raise _too_large()

    digest = hashlib.sha256()
    buffer = bytearray()

    while chunk := await file.read(CHUNK_SIZE):
        if not buffer:
            # Content-Type is whatever the client claimed. This is the file
            # itself saying what it is, and it is the only check that catches a
            # .png renamed .pdf — a browser labels that application/pdf from the
            # extension alone.
            if not chunk.startswith(PDF_MAGIC):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Not a PDF: the file does not start with %PDF-",
                )
        buffer.extend(chunk)
        if len(buffer) > settings.upload_max_bytes:
            raise _too_large()
        digest.update(chunk)

    if not buffer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty file"
        )
    return bytes(buffer), digest.hexdigest()


def _count_pages(data: bytes) -> int | None:
    """None rather than an error: a PDF we cannot parse is still worth keeping.

    Storing and understanding are separate concerns — the extraction agent may
    well do better than pypdf does, and throwing the file away because a page
    count failed would be the wrong trade.
    """
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        logger.info("page count failed; storing with page_count=NULL", exc_info=True)
        return None


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((tomorrow - now).total_seconds()))


async def _enforce_rate_limit(session: AsyncSession, user: User) -> None:
    """A day's uploads per user, counted in UTC.

    UTC because the server does not know the caller's timezone, and a window
    that moves with a client-supplied one is not a limit.

    Known weakness, stated rather than hidden: this counts live rows, so
    deleting your own documents lowers it. The append-only alternative is a
    second table nobody reads. At this cap on a free-tier deployment that is the
    right trade — but #59 is about to hang a paid API off this endpoint and
    counts this as one of its spend controls, so it must not be mistaken for a
    hard ceiling.
    """
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    used = await session.scalar(
        select(func.count())
        .select_from(BillDocument)
        .where(
            BillDocument.uploaded_by == user.id,
            BillDocument.created_at >= midnight,
        )
    )
    if (used or 0) >= settings.upload_daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Upload limit of {settings.upload_daily_limit} per day reached. "
                "Try again tomorrow."
            ),
            headers={"Retry-After": str(_seconds_until_utc_midnight(now))},
        )


@router.post(
    "",
    response_model=BillDocumentRead,
    status_code=status.HTTP_201_CREATED,
    # Declared, or the generated client only ever knows about 201.
    responses={200: {"model": BillDocumentRead, "description": "Already uploaded"}},
)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
    storage: StorageBackend = Depends(get_storage),
) -> BillDocument:
    """Store a bill PDF. 201 for a new one, 200 when we already have it.

    Idempotent by content: uq_bill_documents_place_sha means the same file sent
    twice is one row and one object, so a re-upload costs nothing and — once #59
    lands — does not pay for a second extraction.
    """
    if file.content_type and file.content_type.split(";")[0].strip() != PDF_MEDIA_TYPE:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected {PDF_MEDIA_TYPE}, got {file.content_type}",
        )

    data, sha256 = await _read_capped(file)

    existing = await session.scalar(
        select(BillDocument).where(
            BillDocument.place_id == place.id, BillDocument.sha256 == sha256
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    # After the dedupe miss, deliberately: re-sending a file already stored
    # creates no row and costs nothing, so charging it against the day's
    # allowance would punish the idempotent path this endpoint is built around.
    await _enforce_rate_limit(session, user)

    key = f"{place.id}/{sha256}.pdf"
    page_count = await run_in_threadpool(_count_pages, data)

    # Object first, then row. The reverse would leave a row pointing at nothing,
    # which reads as corruption; this way a failed insert leaves an unreferenced
    # object under a key the next upload of the same file reuses.
    await storage.put(key, data, PDF_MEDIA_TYPE)

    document = BillDocument(
        place_id=place.id,
        sha256=sha256,
        filename=_safe_filename(file.filename),
        media_type=PDF_MEDIA_TYPE,
        byte_size=len(data),
        page_count=page_count,
        storage_key=key,
        uploaded_by=user.id,
    )
    session.add(document)
    try:
        await session.commit()
    except IntegrityError:
        # Two identical uploads racing. The object is content-addressed, so the
        # one already stored is byte-for-byte this one; return the winner.
        await session.rollback()
        winner = await session.scalar(
            select(BillDocument).where(
                BillDocument.place_id == place.id, BillDocument.sha256 == sha256
            )
        )
        if winner is None:
            raise
        response.status_code = status.HTTP_200_OK
        return winner
    await session.refresh(document)
    return document


@router.get("", response_model=list[BillDocumentRead])
async def list_documents(
    place: Place = Depends(get_owned_place),
    session: AsyncSession = Depends(get_async_session),
) -> list[BillDocument]:
    result = await session.execute(
        select(BillDocument)
        .where(BillDocument.place_id == place.id)
        .order_by(BillDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=BillDocumentRead)
async def get_document(
    document: BillDocument = Depends(get_owned_document),
) -> BillDocument:
    return document


@router.get("/{document_id}/content")
async def get_document_content(
    document: BillDocument = Depends(get_owned_document),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    """Redirect to a signed URL where the backend offers one, else stream it."""
    url = await storage.signed_url(document.storage_key, settings.signed_url_expires_in)
    if url is not None:
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    try:
        data = await storage.get(document.storage_key)
    except StorageObjectNotFound:
        # The row outlived its bytes. Real, and currently expected in
        # production: Render declares no disk, so local storage does not survive
        # a deploy. 410 says "this existed and is gone", which 404 does not.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The stored file is no longer available",
        )

    # filename is user-supplied and this is a response header, so it gets two
    # defences. The ASCII fallback is stripped to characters that cannot carry a
    # CR/LF or close the quoted string; the RFC 5987 form is percent-encoded, so
    # it is ASCII by construction and carries the real name. Starlette encodes
    # headers as latin-1, so an un-encoded name in a non-latin script would
    # otherwise be a 500 on download.
    ascii_name = (
        "".join(c for c in document.filename if 32 <= ord(c) < 127 and c != '"')
        or "document.pdf"
    )
    disposition = (
        f'inline; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(document.filename, safe='')}"
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=document.media_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(data)),
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document: BillDocument = Depends(get_owned_document),
    session: AsyncSession = Depends(get_async_session),
    storage: StorageBackend = Depends(get_storage),
) -> None:
    """Refuse while a bill still points at it, rather than nulling the link."""
    referenced = await session.scalar(
        select(Bill.id).where(Bill.document_id == document.id).limit(1)
    )
    if referenced is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A bill still references this document",
        )

    key = document.storage_key
    await session.delete(document)
    await session.commit()
    await purge_objects(storage, [key])
