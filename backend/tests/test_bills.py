from decimal import Decimal

from tests.conftest import PLACE_PAYLOAD, bill_payload


def invoice_payload(**overrides):
    """A bill carrying full invoice identity, in the shape the corpus prints.

    The figures are `data/bills/2024-11.pdf`: PPC Energie Muntenia, 41 kWh over
    November 2024, invoice 24MI 15990831. The PDFs are gitignored and must not be
    committed (AGENTS.md), so the shape is reproduced here rather than read.
    """
    payload = {
        "period_start": "2024-11-01",
        "period_end": "2024-11-30",
        "consumption": "41",
        "unit": "kWh",
        "total_amount": "27.88",
        "provider_name": "PPC Energie Muntenia S.A.",
        "provider_tax_id": "RO22000460",
        "customer_code": "C103441973",
        "provider_invoice_series": "24MI",
        "provider_invoice_number": "15990831",
        "issued_on": "2024-12-07",
        "due_on": "2024-12-22",
        "net_amount": "23.43",
        "vat_base": "23.43",
        "vat_rate": "0.19",
        "vat_amount": "4.45",
        "balance_brought_forward": "0.00",
        "total_due": "27.88",
        "read_method": "actual",
        "document_type": "invoice",
        "source": "ai",
    }
    payload.update(overrides)
    return payload


def credit_note_payload(corrects_bill_id, **overrides):
    """The Stornare of the above — same period, negated, its own invoice number."""
    return invoice_payload(
        provider_invoice_number="16104552",
        consumption="-41",
        total_amount="-27.88",
        net_amount="-23.43",
        vat_base="-23.43",
        vat_amount="-4.45",
        total_due="-27.88",
        document_type="credit_note",
        corrects_bill_id=corrects_bill_id,
        notes="Stornare a facturii seria 24MI nr. 15990831",
        **overrides,
    )


async def make_place(client, headers, **overrides):
    payload = {**PLACE_PAYLOAD, **overrides}
    r = await client.post("/places", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


class TestBillsCrud:
    async def test_create_snapshots_currency(self, client, auth_headers, place):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        bill = r.json()
        assert bill["currency_code"] == "EUR"
        assert bill["utility_type"] == "electricity"

    async def test_currency_snapshot_survives_place_change(
        self, client, auth_headers, place
    ):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        bill_id = r.json()["id"]

        r = await client.patch(
            f"/places/{place['id']}",
            json={"currency_code": "USD"},
            headers=auth_headers,
        )
        assert r.status_code == 200

        r = await client.get(
            f"/places/{place['id']}/bills/{bill_id}", headers=auth_headers
        )
        assert r.json()["currency_code"] == "EUR"

    async def test_invalid_period_rejected(self, client, auth_headers, place):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(period_start="2026-03-31", period_end="2026-03-01"),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_duplicate_period_conflict(self, client, auth_headers, place):
        """No invoice number, same period — still 409.

        The ingest CLI sends exactly this shape and README promises its re-runs
        skip already-uploaded periods. uq_bills_place_period is gone, so this is
        now the application-level fallback in routers/bills.py being exercised.
        """
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        assert r.status_code == 201
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        assert r.status_code == 409
        assert r.json()["detail"] == "A bill for this period already exists"

    async def test_update_and_delete(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        bill_id = r.json()["id"]

        r = await client.patch(
            f"{url}/{bill_id}",
            json={"total_amount": "99.99", "notes": "corrected"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["total_amount"] == "99.99"

        r = await client.patch(
            f"{url}/{bill_id}",
            json={"period_end": "2026-02-01"},
            headers=auth_headers,
        )
        assert r.status_code == 422

        r = await client.delete(f"{url}/{bill_id}", headers=auth_headers)
        assert r.status_code == 204
        r = await client.get(f"{url}/{bill_id}", headers=auth_headers)
        assert r.status_code == 404

    async def test_list_filters(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        await client.post(url, json=bill_payload(), headers=auth_headers)
        await client.post(
            url,
            json=bill_payload(period_start="2026-04-01", period_end="2026-04-30"),
            headers=auth_headers,
        )

        r = await client.get(url, headers=auth_headers)
        assert len(r.json()) == 2
        # newest first
        assert r.json()[0]["period_start"] == "2026-04-01"

        r = await client.get(
            url, params={"from": "2026-04-01"}, headers=auth_headers
        )
        assert len(r.json()) == 1


class TestInvoiceIdentity:
    """Uniqueness lives on the invoice number, not the billing period."""

    async def test_credit_note_shares_the_original_period(
        self, client, auth_headers, place
    ):
        """The defect this story exists to fix: 2024-11 and its Stornare.

        Both are real invoices from the provider, both print 01.11–30.11.2024,
        and under uq_bills_place_period the second was a 409.
        """
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=invoice_payload(), headers=auth_headers)
        assert r.status_code == 201, r.text
        original = r.json()

        r = await client.post(
            url, json=credit_note_payload(original["id"]), headers=auth_headers
        )
        assert r.status_code == 201, r.text
        storno = r.json()

        assert storno["period_start"] == original["period_start"]
        assert storno["period_end"] == original["period_end"]
        assert storno["corrects_bill_id"] == original["id"]
        assert storno["document_type"] == "credit_note"
        assert Decimal(storno["consumption"]) == Decimal("-41")
        assert Decimal(storno["total_amount"]) == Decimal("-27.88")

        r = await client.get(url, headers=auth_headers)
        assert len(r.json()) == 2

    async def test_regularisation_chain_coexists(self, client, auth_headers, place):
        """2024-10, the Stornare that reverses it, and the corrected re-bill.

        The re-bill's window (28.09–22.12) contains the reversed one, so all
        three overlap; nothing in the schema may object to that.
        """
        url = f"/places/{place['id']}/bills"
        original = invoice_payload(
            period_start="2024-09-28",
            period_end="2024-10-31",
            consumption="133",
            provider_invoice_number="15612044",
            total_amount="88.40",
        )
        r = await client.post(url, json=original, headers=auth_headers)
        assert r.status_code == 201, r.text
        original_id = r.json()["id"]

        reversal = invoice_payload(
            period_start="2024-09-28",
            period_end="2024-10-31",
            consumption="-133",
            provider_invoice_number="16104553",
            total_amount="-88.40",
            document_type="credit_note",
            corrects_bill_id=original_id,
        )
        assert (
            await client.post(url, json=reversal, headers=auth_headers)
        ).status_code == 201

        rebill = invoice_payload(
            period_start="2024-09-28",
            period_end="2024-12-22",
            consumption="550",
            provider_invoice_number="16104554",
            total_amount="365.50",
            read_method="regularisation",
        )
        assert (
            await client.post(url, json=rebill, headers=auth_headers)
        ).status_code == 201

        r = await client.get(url, headers=auth_headers)
        assert len(r.json()) == 3

    async def test_negative_amounts_accepted(self, client, auth_headers, place):
        """BillBase.consumption used to carry ge=0. -41 kWh is a correct value."""
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(consumption="-41", total_amount="-27.88"),
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert Decimal(r.json()["consumption"]) == Decimal("-41")
        assert Decimal(r.json()["total_amount"]) == Decimal("-27.88")

    async def test_negative_unit_price_still_rejected(
        self, client, auth_headers, place
    ):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(unit_price="-0.18"),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_duplicate_invoice_number_conflicts(
        self, client, auth_headers, place
    ):
        url = f"/places/{place['id']}/bills"
        assert (
            await client.post(url, json=invoice_payload(), headers=auth_headers)
        ).status_code == 201
        # A different period, so only the invoice number can be the objection.
        r = await client.post(
            url,
            json=invoice_payload(
                period_start="2024-12-01", period_end="2024-12-31"
            ),
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "A bill with this invoice number already exists"

    async def test_same_invoice_number_on_another_place_is_fine(
        self, client, auth_headers, place
    ):
        """The constraint is per place — two homes can hold unrelated invoices
        that happen to share a number."""
        other = await make_place(client, auth_headers, name="Second Home")
        for target in (place, other):
            r = await client.post(
                f"/places/{target['id']}/bills",
                json=invoice_payload(),
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text

    async def test_numbered_bill_may_reuse_a_numberless_period(
        self, client, auth_headers, place
    ):
        """The period fallback applies to the incoming bill, not the stored one.

        A hand-entered bill claims no invoice identity, so it cannot block the
        provider's own invoice for the same period from being imported.
        """
        url = f"/places/{place['id']}/bills"
        assert (
            await client.post(
                url,
                json=bill_payload(
                    period_start="2024-11-01", period_end="2024-11-30"
                ),
                headers=auth_headers,
            )
        ).status_code == 201
        r = await client.post(url, json=invoice_payload(), headers=auth_headers)
        assert r.status_code == 201, r.text

    async def test_patch_into_a_duplicate_invoice_number_conflicts(
        self, client, auth_headers, place
    ):
        url = f"/places/{place['id']}/bills"
        await client.post(url, json=invoice_payload(), headers=auth_headers)
        r = await client.post(
            url,
            json=invoice_payload(
                provider_invoice_number="16104999",
                period_start="2024-12-01",
                period_end="2024-12-31",
            ),
            headers=auth_headers,
        )
        second_id = r.json()["id"]

        r = await client.patch(
            f"{url}/{second_id}",
            json={"provider_invoice_number": "15990831"},
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "A bill with this invoice number already exists"

    async def test_patch_leaves_its_own_row_alone(self, client, auth_headers, place):
        """The duplicate check must exclude the bill being edited, or every
        PATCH that does not move the period would collide with itself."""
        url = f"/places/{place['id']}/bills"
        bill_id = (
            await client.post(url, json=invoice_payload(), headers=auth_headers)
        ).json()["id"]
        r = await client.patch(
            f"{url}/{bill_id}", json={"notes": "checked"}, headers=auth_headers
        )
        assert r.status_code == 200, r.text

    async def test_vat_rate_round_trips(self, client, auth_headers, place):
        """19% through 2026-06, 21% on 2026-07. Never a constant."""
        url = f"/places/{place['id']}/bills"
        for number, rate in (("15990831", "0.19"), ("18004411", "0.21")):
            r = await client.post(
                url,
                json=invoice_payload(provider_invoice_number=number, vat_rate=rate),
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text
            assert Decimal(r.json()["vat_rate"]) == Decimal(rate)

    async def test_vat_rate_as_percentage_rejected(self, client, auth_headers, place):
        """21 instead of 0.21 overflows Numeric(5, 4) — 422, not a 500."""
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=invoice_payload(vat_rate="21"),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_unknown_enum_values_rejected(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        for field, value in (
            ("document_type", "receipt"),
            ("read_method", "guessed"),
        ):
            r = await client.post(
                url, json=invoice_payload(**{field: value}), headers=auth_headers
            )
            assert r.status_code == 422, f"{field}={value} was accepted"

    async def test_document_type_defaults_to_invoice(
        self, client, auth_headers, place
    ):
        r = await client.post(
            f"/places/{place['id']}/bills",
            json=bill_payload(),
            headers=auth_headers,
        )
        assert r.json()["document_type"] == "invoice"


class TestCorrections:
    async def test_corrects_bill_must_be_on_the_same_place(
        self, client, auth_headers, second_auth_headers, place
    ):
        """The foreign key names bills.id globally; only this check is between a
        signed-in user and a stranger's bill id."""
        stranger_place = await make_place(client, second_auth_headers)
        stranger_bill = (
            await client.post(
                f"/places/{stranger_place['id']}/bills",
                json=bill_payload(),
                headers=second_auth_headers,
            )
        ).json()["id"]

        r = await client.post(
            f"/places/{place['id']}/bills",
            json=credit_note_payload(stranger_bill),
            headers=auth_headers,
        )
        assert r.status_code == 422
        assert "does not refer to a bill on this place" in r.json()["detail"]

    async def test_corrects_bill_on_another_own_place_rejected(
        self, client, auth_headers, place
    ):
        other = await make_place(client, auth_headers, name="Second Home")
        other_bill = (
            await client.post(
                f"/places/{other['id']}/bills",
                json=bill_payload(),
                headers=auth_headers,
            )
        ).json()["id"]

        r = await client.post(
            f"/places/{place['id']}/bills",
            json=credit_note_payload(other_bill),
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_bill_cannot_correct_itself(self, client, auth_headers, place):
        url = f"/places/{place['id']}/bills"
        bill_id = (
            await client.post(url, json=invoice_payload(), headers=auth_headers)
        ).json()["id"]
        r = await client.patch(
            f"{url}/{bill_id}",
            json={"corrects_bill_id": bill_id},
            headers=auth_headers,
        )
        assert r.status_code == 422

    async def test_deleting_the_original_keeps_the_credit_note(
        self, client, auth_headers, place
    ):
        """ON DELETE SET NULL, not CASCADE: the record of a reversal must not
        vanish with the thing it reversed."""
        url = f"/places/{place['id']}/bills"
        original = (
            await client.post(url, json=invoice_payload(), headers=auth_headers)
        ).json()
        storno = (
            await client.post(
                url, json=credit_note_payload(original["id"]), headers=auth_headers
            )
        ).json()

        r = await client.delete(f"{url}/{original['id']}", headers=auth_headers)
        assert r.status_code == 204

        r = await client.get(f"{url}/{storno['id']}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["corrects_bill_id"] is None


class TestBillIsolation:
    async def test_foreign_place_bills_are_404(
        self, client, auth_headers, second_auth_headers, place
    ):
        url = f"/places/{place['id']}/bills"
        r = await client.post(url, json=bill_payload(), headers=auth_headers)
        bill_id = r.json()["id"]

        r = await client.get(url, headers=second_auth_headers)
        assert r.status_code == 404
        r = await client.get(f"{url}/{bill_id}", headers=second_auth_headers)
        assert r.status_code == 404
