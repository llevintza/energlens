"""A recorded transport for the extraction agent: no network, no API key, no cost.

The agent talks to a real ``AsyncAnthropic`` client whose HTTP layer is an
``httpx2.MockTransport`` replaying hand-built responses from
``tests/fixtures/agent/*.json`` (see the README there). Everything above the
transport — request building, response parsing, the beta tool runner itself —
is the SDK's own code, so a fixture that does not match the real response shape
fails here the way it would in production.
"""

import json
from pathlib import Path

import httpx2
from anthropic import AsyncAnthropic

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent"


def load_case(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(pages: list[list[str]]) -> bytes:
    """A valid PDF whose text layer is exactly ``pages`` — one string per line.

    Helvetica's standard encoding, so keep the text ASCII. Built in memory:
    nothing PDF-shaped is ever committed (AGENTS.md, and .gitignore has *.pdf).
    """
    n = len(pages)
    font_id = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
    ]
    for i, lines in enumerate(pages):
        body = "BT /F1 9 Tf 12 TL 20 800 Td " + " ".join(f"({_escape(line)}) Tj T*" for line in lines) + " ET"
        stream = body.encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


class RecordedTransport:
    """Replays a case's Messages responses in order and keeps every request.

    ``upload_status`` other than 200 makes the Files API upload fail, to drive
    the inline-base64 fallback.
    """

    FILE_ID = "file_01SYNTHETIC0000000000"

    def __init__(self, case: dict, *, upload_status: int = 200) -> None:
        self._responses = list(case["responses"])
        self.upload_status = upload_status
        self.message_requests: list[dict] = []
        self.message_headers: list[httpx2.Headers] = []
        self.uploads = 0
        self.deleted: list[str] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/files":
            self.uploads += 1
            if self.upload_status != 200:
                return httpx2.Response(
                    self.upload_status,
                    json={"type": "error", "error": {"type": "api_error", "message": "synthetic"}},
                )
            return httpx2.Response(
                200,
                json={
                    "id": self.FILE_ID,
                    "type": "file",
                    "filename": "bill.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 2048,
                    "created_at": "2026-10-25T00:00:00Z",
                    "downloadable": False,
                },
            )
        if request.method == "DELETE" and path.startswith("/v1/files/"):
            file_id = path.rsplit("/", 1)[1]
            self.deleted.append(file_id)
            return httpx2.Response(200, json={"id": file_id, "type": "file_deleted"})
        if request.method == "POST" and path == "/v1/messages":
            self.message_requests.append(json.loads(request.content))
            self.message_headers.append(request.headers)
            if not self._responses:
                raise AssertionError("the agent made more Messages calls than the fixture holds")
            return httpx2.Response(200, json=self._responses.pop(0))
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    @property
    def unused(self) -> int:
        return len(self._responses)

    def client(self) -> AsyncAnthropic:
        return AsyncAnthropic(
            api_key="test-key-not-real",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.handler)),
        )
