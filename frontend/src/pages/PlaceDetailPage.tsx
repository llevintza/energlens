import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  useBills,
  useCreateBill,
  useDeleteBill,
  useDeletePlace,
  usePlace,
  useUpdateBill,
  useUpdatePlace,
} from '../api/hooks'
import type { Bill, Granularity } from '../api/types'
import { BillForm } from '../components/BillForm'
import { PlaceForm } from '../components/PlaceForm'
import { PlaceCharts, SummaryTiles } from '../components/charts/PlaceCharts'
import { fmtCurrency, fmtDate, fmtNumber } from '../lib/format'

export function PlaceDetailPage() {
  const { placeId } = useParams()
  const navigate = useNavigate()
  const { data: place, isLoading } = usePlace(placeId)
  const { data: bills } = useBills(placeId)
  const updatePlace = useUpdatePlace(placeId!)
  const deletePlace = useDeletePlace()
  const createBill = useCreateBill(placeId!)
  const updateBill = useUpdateBill(placeId!)
  const deleteBill = useDeleteBill(placeId!)

  const [editingPlace, setEditingPlace] = useState(false)
  const [billFormOpen, setBillFormOpen] = useState(false)
  const [editingBill, setEditingBill] = useState<Bill | null>(null)
  const [granularity, setGranularity] = useState<Granularity>('month')

  if (isLoading) return <div className="empty">Loading…</div>
  if (!place) return <div className="empty">Place not found</div>

  const closeBillForm = () => {
    setBillFormOpen(false)
    setEditingBill(null)
  }

  return (
    <>
      <div className="page-title">
        <h1>{place.name}</h1>
        <span className="sub">
          {place.address_line1}, {place.city} · billed in {place.currency_code}
        </span>
        <span style={{ flex: 1 }} />
        <button className="btn small" onClick={() => setEditingPlace((v) => !v)}>
          {editingPlace ? 'Close' : 'Edit place'}
        </button>
        <button
          className="btn small danger"
          onClick={() => {
            if (
              window.confirm(
                `Delete "${place.name}" and all of its bills? This cannot be undone.`,
              )
            ) {
              deletePlace.mutate(place.id, { onSuccess: () => navigate('/places') })
            }
          }}
        >
          Delete
        </button>
      </div>

      {editingPlace && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Edit place</h2>
          {place.currency_code && (
            <p className="note">
              Changing the currency only affects future bills — existing bills
              keep the currency they were charged in.
            </p>
          )}
          <PlaceForm
            initial={place}
            onSubmit={async (data) => {
              await updatePlace.mutateAsync(data)
              setEditingPlace(false)
            }}
            onCancel={() => setEditingPlace(false)}
            submitLabel="Save changes"
          />
        </div>
      )}

      <SummaryTiles place={place} />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="page-title" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Bills</h2>
          <span style={{ flex: 1 }} />
          {!billFormOpen && (
            <button
              className="btn small primary"
              onClick={() => setBillFormOpen(true)}
            >
              Add bill
            </button>
          )}
        </div>

        {(billFormOpen || editingBill) && (
          <div style={{ marginBottom: 14 }}>
            <BillForm
              currency={place.currency_code}
              initial={editingBill ?? undefined}
              onSubmit={async (data) => {
                if (editingBill) {
                  await updateBill.mutateAsync({
                    billId: editingBill.id,
                    data,
                  })
                } else {
                  await createBill.mutateAsync(data)
                }
                closeBillForm()
              }}
              onCancel={closeBillForm}
            />
          </div>
        )}

        {!bills || bills.length === 0 ? (
          <div className="empty">
            No bills yet — add one manually or import with the ingest CLI.
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Period</th>
                  <th className="num">kWh</th>
                  <th className="num">Unit price</th>
                  <th className="num">Fixed</th>
                  <th className="num">Taxes</th>
                  <th className="num">Total</th>
                  <th>Provider</th>
                  <th>Source</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {bills.map((bill) => (
                  <tr key={bill.id}>
                    <td>
                      {fmtDate(bill.period_start)} – {fmtDate(bill.period_end)}
                    </td>
                    <td className="num">{fmtNumber(bill.consumption)}</td>
                    <td className="num">
                      {bill.unit_price
                        ? fmtCurrency(bill.unit_price, bill.currency_code, 4)
                        : '—'}
                    </td>
                    <td className="num">
                      {fmtCurrency(bill.fixed_charges, bill.currency_code)}
                    </td>
                    <td className="num">
                      {fmtCurrency(bill.taxes, bill.currency_code)}
                    </td>
                    <td className="num">
                      <strong>
                        {fmtCurrency(bill.total_amount, bill.currency_code)}
                      </strong>
                    </td>
                    <td>{bill.provider_name ?? '—'}</td>
                    <td>{bill.source}</td>
                    <td>
                      <button
                        className="btn small"
                        onClick={() => {
                          setEditingBill(bill)
                          setBillFormOpen(false)
                        }}
                      >
                        Edit
                      </button>{' '}
                      <button
                        className="btn small danger"
                        onClick={() => {
                          if (window.confirm('Delete this bill?')) {
                            deleteBill.mutate(bill.id)
                          }
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="filter-row">
        <span className="filter-label">Chart granularity</span>
        <div className="seg">
          {(['month', 'bill'] as const).map((g) => (
            <button
              key={g}
              className={granularity === g ? 'on' : ''}
              onClick={() => setGranularity(g)}
            >
              {g === 'month' ? 'Monthly' : 'Per bill'}
            </button>
          ))}
        </div>
      </div>
      <PlaceCharts place={place} granularity={granularity} />
    </>
  )
}
