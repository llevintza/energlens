"""invoice identity, vat and corrections on bills

Moves a bill's identity off the billing period and onto the provider's own
invoice number, and adds the rest of what an invoice prints: VAT, issue and due
dates, the carried balance, how the meter index was arrived at, and which bill a
credit note reverses.

The period constraint had to go: a Stornare reverses an invoice and reprints its
period, so `uq_bills_place_period` made the correction unstorable — two of the
thirty bills in the corpus could not be inserted at all. `uq_bills_place_invoice`
replaces it. PostgreSQL exempts NULLs from a UNIQUE tuple, which is what leaves
manually-entered bills (no invoice number) unconstrained; the period rule they
still need now lives in app/routers/bills.py, where it is tested.

This runs at boot on Render (backend/start.sh), so a failure here is an outage
rather than a failed deploy step — see docs/adr/0011.

Revision ID: 4c3dd9fa0449
Revises: d7c413da8d84
Create Date: 2026-08-13 23:30:34.901050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4c3dd9fa0449'
down_revision: Union[str, None] = 'd7c413da8d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bills', sa.Column('provider_invoice_series', sa.String(length=20), nullable=True))
    op.add_column('bills', sa.Column('provider_invoice_number', sa.String(length=50), nullable=True))
    op.add_column('bills', sa.Column('issued_on', sa.Date(), nullable=True))
    op.add_column('bills', sa.Column('due_on', sa.Date(), nullable=True))
    op.add_column('bills', sa.Column('net_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('bills', sa.Column('vat_base', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('bills', sa.Column('vat_rate', sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column('bills', sa.Column('vat_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('bills', sa.Column('balance_brought_forward', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('bills', sa.Column('total_due', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('bills', sa.Column('read_method', sa.String(length=20), nullable=True))
    # NOT NULL with a server default, so existing rows are filled by the same
    # statement — every bill written before this migration is an invoice.
    op.add_column('bills', sa.Column('document_type', sa.String(length=20), server_default='invoice', nullable=False))
    op.add_column('bills', sa.Column('corrects_bill_id', sa.Uuid(), nullable=True))
    op.add_column('bills', sa.Column('customer_code', sa.String(length=50), nullable=True))
    op.add_column('bills', sa.Column('provider_tax_id', sa.String(length=30), nullable=True))

    # Existing bills carry no balance forward, so what was payable is what the
    # invoice was worth. Leaving these NULL would make total_due unreadable
    # without knowing when the row was written.
    op.execute('UPDATE bills SET total_due = total_amount WHERE total_due IS NULL')

    op.drop_constraint('uq_bills_place_period', 'bills', type_='unique')
    op.create_unique_constraint('uq_bills_place_invoice', 'bills', ['place_id', 'provider_invoice_series', 'provider_invoice_number'])
    # SET NULL, not CASCADE: deleting an original must not silently delete the
    # credit note that documents its reversal.
    op.create_foreign_key('fk_bills_corrects_bill_id', 'bills', 'bills', ['corrects_bill_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint('ck_bills_document_type', 'bills', "document_type IN ('invoice', 'credit_note')")
    op.create_check_constraint('ck_bills_read_method', 'bills', "read_method IN ('actual', 'self_read', 'estimated', 'regularisation', 'mixed')")


def downgrade() -> None:
    """Reverse all of it.

    Recreating uq_bills_place_period fails if any place holds two bills for one
    period — a credit note and the invoice it reverses, which is exactly the
    data this migration exists to allow. That failure is deliberate: the
    alternative is deleting one of the two rows to make room for the constraint.
    """
    op.drop_constraint('ck_bills_read_method', 'bills', type_='check')
    op.drop_constraint('ck_bills_document_type', 'bills', type_='check')
    op.drop_constraint('fk_bills_corrects_bill_id', 'bills', type_='foreignkey')
    op.drop_constraint('uq_bills_place_invoice', 'bills', type_='unique')
    op.create_unique_constraint('uq_bills_place_period', 'bills', ['place_id', 'utility_type', 'period_start', 'period_end'])
    op.drop_column('bills', 'provider_tax_id')
    op.drop_column('bills', 'customer_code')
    op.drop_column('bills', 'corrects_bill_id')
    op.drop_column('bills', 'document_type')
    op.drop_column('bills', 'read_method')
    op.drop_column('bills', 'total_due')
    op.drop_column('bills', 'balance_brought_forward')
    op.drop_column('bills', 'vat_amount')
    op.drop_column('bills', 'vat_rate')
    op.drop_column('bills', 'vat_base')
    op.drop_column('bills', 'net_amount')
    op.drop_column('bills', 'due_on')
    op.drop_column('bills', 'issued_on')
    op.drop_column('bills', 'provider_invoice_number')
    op.drop_column('bills', 'provider_invoice_series')
