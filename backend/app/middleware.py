"""Refuse an oversized body before any of it is read.

This exists because of where FastAPI does its work. In `fastapi/routing.py` the
request body is parsed — `await request.form()` — *before* `solve_dependencies`
runs. So by the time the upload route sees an `UploadFile`, or even by the time
`get_owned_place` has decided the caller is allowed to be here, the whole body
has already been received and spooled. A size check inside the handler bounds
how much lands in memory; it cannot stop the bytes arriving, and neither can
authentication.

Starlette's own `max_part_size` does not help: `MultiPartParser` only applies it
to non-file parts, and file parts stream into a `SpooledTemporaryFile` with no
ceiling at all.

Outside the router is therefore the only place left that is genuinely early.
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

# Boundary lines, Content-Disposition and Content-Type around the file part —
# a few hundred bytes in practice. 8 KiB is generous, and keeps a legitimate
# upload of exactly upload_max_bytes from being refused on its framing.
MULTIPART_OVERHEAD = 8 * 1024


class MaxBodySizeMiddleware:
    """Reject on Content-Length, before the body is read.

    Deliberately global rather than scoped to the upload path: every other
    endpoint takes small JSON, so one ceiling hardens all of them and keeps
    route knowledge out of main.py.

    A declared length is not trustworthy and is not trusted — a chunked request
    carries none at all. This is the cheap outer bound; the authoritative check
    is the read loop in routers/bill_documents.py, which bounds memory whatever
    the client claimed.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            # Read per request, not captured in __init__: the tests monkeypatch
            # settings.upload_max_bytes, and capturing it at app-build time
            # would make that a silent no-op — the test would still pass, for
            # the wrong reason.
            limit = settings.upload_max_bytes + MULTIPART_OVERHEAD
            declared = Headers(scope=scope).get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                response = JSONResponse(
                    {
                        "detail": (
                            "File is larger than the "
                            f"{settings.upload_max_bytes // (1024 * 1024)} MB limit"
                        )
                    },
                    status_code=413,
                )
                # `receive` is never awaited, so the body is not drained.
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
