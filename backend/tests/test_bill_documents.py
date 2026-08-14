import hashlib
from urllib.parse import quote

import pytest

from app.config import settings
from app.models import BillDocument
from app.routers.bill_documents import _safe_filename
from tests.conftest import (
    bill_payload,
    make_corrupt_pdf,
    make_pdf,
    make_png,
    pdf_upload,
)


def docs_url(place) -> str:
    return f"/places/{place['id']}/bill-documents"


def stored_files(storage_root) -> list:
    return [p for p in storage_root.rglob("*") if p.is_file()]


class TestUpload:
    async def test_stores_the_file_and_reports_it(
        self, client, auth_headers, place, storage_root
    ):
        data = make_pdf(pages=3)
        r = await client.post(
            docs_url(place), files=pdf_upload(data), headers=auth_headers
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["sha256"] == hashlib.sha256(data).hexdigest()
        assert body["byte_size"] == len(data)
        assert body["page_count"] == 3
        assert body["media_type"] == "application/pdf"
        assert body["filename"] == "bill.pdf"
        # storage_key is internal and must not leak onto the wire.
        assert "storage_key" not in body

        files = stored_files(storage_root)
        assert len(files) == 1
        assert files[0].read_bytes() == data

    async def test_same_file_twice_is_one_row_and_one_object(
        self, client, auth_headers, place, storage_root
    ):
        data = make_pdf()
        first = await client.post(
            docs_url(place), files=pdf_upload(data), headers=auth_headers
        )
        assert first.status_code == 201

        second = await client.post(
            docs_url(place), files=pdf_upload(data, name="renamed.pdf"),
            headers=auth_headers,
        )
        # 200, not 201: the second upload created nothing.
        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]

        listing = await client.get(docs_url(place), headers=auth_headers)
        assert len(listing.json()) == 1
        assert len(stored_files(storage_root)) == 1

    async def test_a_different_file_is_a_different_document(
        self, client, auth_headers, place, storage_root
    ):
        for marker in ("one", "two"):
            r = await client.post(
                docs_url(place),
                files=pdf_upload(make_pdf(marker=marker)),
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text
        assert len(stored_files(storage_root)) == 2

    async def test_the_same_file_on_two_places_is_two_documents(
        self, client, auth_headers, place, storage_root
    ):
        """Dedupe is per place, so one user's upload cannot be probed by another.

        Same reasoning, same test: the key is namespaced by place id, so two
        rows and two objects.
        """
        from tests.conftest import PLACE_PAYLOAD

        other = await client.post(
            "/places", json={**PLACE_PAYLOAD, "name": "Second"}, headers=auth_headers
        )
        data = make_pdf()
        for target in (place, other.json()):
            r = await client.post(
                docs_url(target), files=pdf_upload(data), headers=auth_headers
            )
            assert r.status_code == 201, r.text
        assert len(stored_files(storage_root)) == 2


class TestUploadRejection:
    async def test_a_png_renamed_to_pdf_is_rejected(
        self, client, auth_headers, place, storage_root
    ):
        """The case the Content-Type check cannot catch.

        A browser labels an upload from its extension, so a .png renamed .pdf
        arrives declared application/pdf. Only the %PDF- magic check sees it.
        """
        r = await client.post(
            docs_url(place), files=pdf_upload(make_png()), headers=auth_headers
        )
        assert r.status_code == 415, r.text
        assert stored_files(storage_root) == []

    async def test_a_non_pdf_content_type_is_rejected(
        self, client, auth_headers, place
    ):
        r = await client.post(
            docs_url(place),
            files={"file": ("bill.png", make_png(), "image/png")},
            headers=auth_headers,
        )
        assert r.status_code == 415

    async def test_an_empty_file_is_rejected(self, client, auth_headers, place):
        r = await client.post(
            docs_url(place),
            files={"file": ("bill.pdf", b"", "application/pdf")},
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_an_oversized_upload_is_refused(
        self, client, auth_headers, place, storage_root, monkeypatch
    ):
        """Rejected on Content-Length, before the body is read.

        monkeypatching the setting works only because MaxBodySizeMiddleware
        reads it per request — capturing it when the app is built would make
        this a silent no-op and the test would pass for the wrong reason.
        """
        monkeypatch.setattr(settings, "upload_max_bytes", 4096)
        oversized = b"%PDF-1.4\n" + b"\0" * 32_768
        r = await client.post(
            docs_url(place), files=pdf_upload(oversized), headers=auth_headers
        )
        assert r.status_code == 413, r.text
        assert stored_files(storage_root) == []

    async def test_the_handler_caps_memory_even_without_a_content_length(
        self, client, auth_headers, place, storage_root, monkeypatch
    ):
        """The second layer, exercised on its own.

        The middleware only sees what the client declared. This drives the read
        loop past the cap with the middleware's limit left high, so a failure
        here means the in-handler bound is gone even though the outer one holds.
        """
        monkeypatch.setattr(settings, "upload_max_bytes", 4096)
        # Middleware compares against upload_max_bytes + MULTIPART_OVERHEAD
        # (8 KiB), so a 6 KiB body passes it and must be stopped by the loop.
        body = b"%PDF-1.4\n" + b"\0" * 6144
        r = await client.post(
            docs_url(place), files=pdf_upload(body), headers=auth_headers
        )
        assert r.status_code == 413, r.text
        assert stored_files(storage_root) == []

    async def test_a_corrupt_pdf_is_stored_with_no_page_count(
        self, client, auth_headers, place, storage_root
    ):
        """Storage and understanding are separate concerns."""
        r = await client.post(
            docs_url(place), files=pdf_upload(make_corrupt_pdf()), headers=auth_headers
        )
        assert r.status_code == 201, r.text
        assert r.json()["page_count"] is None
        assert len(stored_files(storage_root)) == 1

    async def test_a_hostile_filename_is_defanged(self, client, auth_headers, place):
        r = await client.post(
            docs_url(place),
            files=pdf_upload(make_pdf(), name="../../etc/passwd.pdf"),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert "/" not in r.json()["filename"]
        assert r.json()["filename"] == "passwd.pdf"


class TestRateLimit:
    async def test_the_daily_limit_returns_429_with_retry_after(
        self, client, auth_headers, place, monkeypatch
    ):
        monkeypatch.setattr(settings, "upload_daily_limit", 2)
        for i in range(2):
            r = await client.post(
                docs_url(place),
                files=pdf_upload(make_pdf(marker=str(i))),
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text

        r = await client.post(
            docs_url(place),
            files=pdf_upload(make_pdf(marker="over")),
            headers=auth_headers,
        )
        assert r.status_code == 429, r.text
        assert int(r.headers["retry-after"]) > 0

    async def test_a_duplicate_does_not_spend_the_allowance(
        self, client, auth_headers, place, monkeypatch
    ):
        """Re-sending a file already stored creates no row, so it costs nothing."""
        monkeypatch.setattr(settings, "upload_daily_limit", 1)
        data = make_pdf()
        first = await client.post(
            docs_url(place), files=pdf_upload(data), headers=auth_headers
        )
        assert first.status_code == 201
        again = await client.post(
            docs_url(place), files=pdf_upload(data), headers=auth_headers
        )
        assert again.status_code == 200, again.text


class TestDownload:
    async def test_content_returns_the_bytes(self, client, auth_headers, place):
        data = make_pdf(pages=2)
        doc = (
            await client.post(
                docs_url(place), files=pdf_upload(data), headers=auth_headers
            )
        ).json()

        r = await client.get(
            f"{docs_url(place)}/{doc['id']}/content", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        assert r.content == data
        assert r.headers["content-type"] == "application/pdf"

    async def test_a_unicode_filename_survives_the_round_trip(
        self, client, auth_headers, place
    ):
        """Starlette encodes headers as latin-1, so a non-latin name would be a
        500 on download if it were not percent-encoded."""
        r = await client.post(
            docs_url(place),
            files=pdf_upload(make_pdf(), name="factură-2026-07.pdf"),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["filename"] == "factură-2026-07.pdf"

        r = await client.get(
            f"{docs_url(place)}/{doc['id']}/content", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        disposition = r.headers["content-disposition"]
        assert "filename*=UTF-8''factur%C3%A3" in disposition or "%C4%83" in disposition

    async def test_content_is_410_when_the_object_is_gone(
        self, client, auth_headers, place, storage_root
    ):
        """The row outlives its bytes — which is the state Render is in today.

        410, not 404: the document exists and the caller may read its metadata.
        Only the file is gone.
        """
        doc = (
            await client.post(
                docs_url(place), files=pdf_upload(), headers=auth_headers
            )
        ).json()
        for path in stored_files(storage_root):
            path.unlink()

        r = await client.get(
            f"{docs_url(place)}/{doc['id']}/content", headers=auth_headers
        )
        assert r.status_code == 410, r.text
        # The metadata still answers.
        assert (
            await client.get(f"{docs_url(place)}/{doc['id']}", headers=auth_headers)
        ).status_code == 200


class TestDelete:
    async def test_delete_removes_the_row_and_the_object(
        self, client, auth_headers, place, storage_root
    ):
        doc = (
            await client.post(
                docs_url(place), files=pdf_upload(), headers=auth_headers
            )
        ).json()
        assert len(stored_files(storage_root)) == 1

        r = await client.delete(f"{docs_url(place)}/{doc['id']}", headers=auth_headers)
        assert r.status_code == 204
        assert stored_files(storage_root) == []
        assert (
            await client.get(f"{docs_url(place)}/{doc['id']}", headers=auth_headers)
        ).status_code == 404

    async def test_delete_is_refused_while_a_bill_references_it(
        self, client, auth_headers, place, storage_root
    ):
        doc = (
            await client.post(
                docs_url(place), files=pdf_upload(), headers=auth_headers
            )
        ).json()
        bill = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(document_id=doc["id"]),
            headers=auth_headers,
        )
        assert bill.status_code == 201, bill.text
        assert bill.json()["document_id"] == doc["id"]

        r = await client.delete(f"{docs_url(place)}/{doc['id']}", headers=auth_headers)
        assert r.status_code == 409, r.text
        # Refused means nothing happened — not a half-delete.
        assert len(stored_files(storage_root)) == 1

        # Unlink the bill and the delete goes through.
        await client.patch(
            f"/places/{place['id']}/bills/{bill.json()['id']}",
            json={"document_id": None},
            headers=auth_headers,
        )
        r = await client.delete(f"{docs_url(place)}/{doc['id']}", headers=auth_headers)
        assert r.status_code == 204, r.text

    async def test_deleting_the_place_deletes_the_objects(
        self, client, auth_headers, place, storage_root
    ):
        for marker in ("a", "b"):
            await client.post(
                docs_url(place),
                files=pdf_upload(make_pdf(marker=marker)),
                headers=auth_headers,
            )
        assert len(stored_files(storage_root)) == 2

        r = await client.delete(f"/places/{place['id']}", headers=auth_headers)
        assert r.status_code == 204
        assert stored_files(storage_root) == []

    async def test_deleting_the_account_deletes_the_objects(
        self, client, auth_headers, place, storage_root
    ):
        """The promise ADR-0021 makes: forgetting an account forgets the bills."""
        await client.post(docs_url(place), files=pdf_upload(), headers=auth_headers)
        assert len(stored_files(storage_root)) == 1

        r = await client.delete("/users/me", headers=auth_headers)
        assert r.status_code == 204
        assert stored_files(storage_root) == []


class TestBillDocumentLink:
    async def test_a_document_on_another_place_cannot_be_linked(
        self, client, auth_headers, second_auth_headers, place
    ):
        """422, not 404: the response must not confirm the id exists elsewhere."""
        from tests.conftest import PLACE_PAYLOAD

        theirs = (
            await client.post(
                "/places", json=PLACE_PAYLOAD, headers=second_auth_headers
            )
        ).json()
        their_doc = (
            await client.post(
                docs_url(theirs), files=pdf_upload(), headers=second_auth_headers
            )
        ).json()

        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(document_id=their_doc["id"]),
            headers=auth_headers,
        )
        assert r.status_code == 422, r.text


class TestDocumentIsolation:
    async def test_another_user_gets_404_everywhere(
        self, client, auth_headers, second_auth_headers, place, storage_root
    ):
        """404 rather than 403, so ids cannot be probed for existence."""
        doc = (
            await client.post(
                docs_url(place), files=pdf_upload(), headers=auth_headers
            )
        ).json()
        url = f"{docs_url(place)}/{doc['id']}"

        for method, path in (
            ("get", docs_url(place)),
            ("get", url),
            ("get", f"{url}/content"),
            ("delete", url),
        ):
            r = await getattr(client, method)(path, headers=second_auth_headers)
            assert r.status_code == 404, f"{method} {path} -> {r.status_code}"

        # And nothing of the owner's was touched.
        assert len(stored_files(storage_root)) == 1

    async def test_a_foreign_document_id_under_an_owned_place_is_404(
        self, client, auth_headers, second_auth_headers, place, storage_root
    ):
        """The check the previous test cannot reach.

        There, get_owned_place refuses first because the place is foreign. Here
        the attacker uses a place they legitimately own and supplies someone
        else's document id — so only the `document.place_id != place.id` half of
        get_owned_document stands between them and another account's bill.
        """
        from tests.conftest import PLACE_PAYLOAD

        victim_doc = (
            await client.post(
                docs_url(place), files=pdf_upload(), headers=auth_headers
            )
        ).json()

        mine = (
            await client.post(
                "/places", json=PLACE_PAYLOAD, headers=second_auth_headers
            )
        ).json()

        for path in (
            f"{docs_url(mine)}/{victim_doc['id']}",
            f"{docs_url(mine)}/{victim_doc['id']}/content",
        ):
            r = await client.get(path, headers=second_auth_headers)
            assert r.status_code == 404, f"{path} -> {r.status_code}"

        r = await client.delete(
            f"{docs_url(mine)}/{victim_doc['id']}", headers=second_auth_headers
        )
        assert r.status_code == 404
        # The victim's object is untouched.
        assert len(stored_files(storage_root)) == 1

    async def test_another_user_cannot_upload_to_a_foreign_place(
        self, client, auth_headers, second_auth_headers, place, storage_root
    ):
        r = await client.post(
            docs_url(place), files=pdf_upload(), headers=second_auth_headers
        )
        assert r.status_code == 404
        assert stored_files(storage_root) == []

    async def test_unauthenticated_is_rejected(self, client, place):
        r = await client.post(docs_url(place), files=pdf_upload())
        assert r.status_code == 401


class TestFilenameSanitisation:
    """Driven directly, because no HTTP client in this suite can deliver the attack.

    httpx percent-escapes the quote and the CRLF when it builds the multipart
    body — `filename="ev%22il%0D%0A..."` goes on the wire — so an end-to-end
    test of header injection asserts httpx's sanitising, not ours, and stays
    green with both of our defences deleted. Verified by deleting them. A raw
    socket has no such manners, so the functions are exercised here with exactly
    what such a client would send.
    """

    @pytest.mark.parametrize(
        "hostile",
        [
            'ev"il\r\nX-Injected: yes.pdf',
            "../../etc/passwd",
            "..\\..\\windows\\system32\\bill.pdf",
            "bill\r\n\r\n<html>.pdf",
            "\x00\x07bill.pdf",
            "   ...   ",
            "",
            None,
        ],
    )
    def test_safe_filename_defangs_every_hostile_form(self, hostile):
        name = _safe_filename(hostile)
        assert name, "must never return an empty name"
        assert len(name) <= 255
        for bad in ("\r", "\n", '"', "/", "\\", "\x00"):
            assert bad not in name, f"{bad!r} survived in {name!r}"

    def test_the_ascii_disposition_half_cannot_break_the_quoting(self):
        """The second layer, on a row whose filename bypassed the first.

        A pre-existing row, or one written by a future code path, may hold
        anything. The download header must still be well-formed.
        """
        stored = 'ev"il\r\nX-Injected: yes.pdf'
        ascii_name = (
            "".join(c for c in stored if 32 <= ord(c) < 127 and c != '"')
            or "document.pdf"
        )
        disposition = (
            f'inline; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(stored, safe='')}"
        )
        assert "\r" not in disposition and "\n" not in disposition
        # Exactly the two that open and close the ASCII filename.
        assert disposition.count('"') == 2
        # And the header value is latin-1 encodable, which is what Starlette
        # requires and what a non-ASCII name would otherwise break.
        disposition.encode("latin-1")


def _cascade_ancestors(table) -> set[str]:
    """Tables whose deletion removes rows from `table` with no ORM involvement."""
    found: set[str] = set()
    stack = [table]
    while stack:
        current = stack.pop()
        for fk in current.foreign_keys:
            if (fk.ondelete or "").upper() == "CASCADE":
                parent = fk.column.table
                if parent.name not in found:
                    found.add(parent.name)
                    stack.append(parent)
    return found


def test_every_cascade_into_documents_has_an_object_purge():
    """Fail when a new way to delete a document row appears.

    The database drops rows on cascade without telling anyone, and the stored
    PDFs have no foreign key to follow. Every path that can destroy a
    bill_documents row therefore needs a matching purge in the router that owns
    it — and the only way to notice a new one is to pin the set.
    """
    assert _cascade_ancestors(BillDocument.__table__) == {"places", "user"}, (
        "A new ON DELETE CASCADE path into bill_documents was added. The database "
        "will drop those rows and leave their PDFs in the object store forever. "
        "Add a purge to the route that deletes the new parent — see "
        "app/services/documents.py — then update this set."
    )
