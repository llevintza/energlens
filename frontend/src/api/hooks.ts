import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import { api } from './client'
import type {
  Bill,
  BillInput,
  CompareResponse,
  Granularity,
  Metric,
  Place,
  PlaceInput,
  PlaceSummary,
  SeriesResponse,
} from './types'

export function usePlaces() {
  return useQuery({
    queryKey: ['places'],
    queryFn: () => api<Place[]>('/places'),
  })
}

export function usePlace(placeId: string | undefined) {
  return useQuery({
    queryKey: ['places', placeId],
    queryFn: () => api<Place>(`/places/${placeId}`),
    enabled: !!placeId,
  })
}

export function useCreatePlace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PlaceInput) => api<Place>('/places', { body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['places'] }),
  })
}

export function useUpdatePlace(placeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<PlaceInput>) =>
      api<Place>(`/places/${placeId}`, { method: 'PATCH', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['places'] }),
  })
}

export function useDeletePlace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (placeId: string) =>
      api<void>(`/places/${placeId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useBills(placeId: string | undefined) {
  return useQuery({
    queryKey: ['bills', placeId],
    queryFn: () => api<Bill[]>(`/places/${placeId}/bills`),
    enabled: !!placeId,
  })
}

function invalidatePlaceData(qc: ReturnType<typeof useQueryClient>, placeId: string) {
  qc.invalidateQueries({ queryKey: ['bills', placeId] })
  qc.invalidateQueries({ queryKey: ['series', placeId] })
  qc.invalidateQueries({ queryKey: ['summary', placeId] })
  qc.invalidateQueries({ queryKey: ['compare'] })
}

export function useCreateBill(placeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BillInput) =>
      api<Bill>(`/places/${placeId}/bills`, { body: data }),
    onSuccess: () => invalidatePlaceData(qc, placeId),
  })
}

export function useUpdateBill(placeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ billId, data }: { billId: string; data: Partial<BillInput> }) =>
      api<Bill>(`/places/${placeId}/bills/${billId}`, {
        method: 'PATCH',
        body: data,
      }),
    onSuccess: () => invalidatePlaceData(qc, placeId),
  })
}

export function useDeleteBill(placeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (billId: string) =>
      api<void>(`/places/${placeId}/bills/${billId}`, { method: 'DELETE' }),
    onSuccess: () => invalidatePlaceData(qc, placeId),
  })
}

export interface SeriesParams {
  metric: Metric
  granularity?: Granularity
  from?: string
  to?: string
}

export function useSeries(placeId: string | undefined, params: SeriesParams) {
  return useQuery({
    queryKey: ['series', placeId, params],
    queryFn: () =>
      api<SeriesResponse>(`/places/${placeId}/series`, {
        params: {
          metric: params.metric,
          granularity: params.granularity,
          from: params.from,
          to: params.to,
        },
      }),
    enabled: !!placeId,
  })
}

export function useCompare(params: SeriesParams) {
  return useQuery({
    queryKey: ['compare', params],
    queryFn: () =>
      api<CompareResponse>('/series/compare', {
        params: {
          metric: params.metric,
          granularity: params.granularity,
          from: params.from,
          to: params.to,
        },
      }),
  })
}

export function useSummary(placeId: string | undefined) {
  return useQuery({
    queryKey: ['summary', placeId],
    queryFn: () => api<PlaceSummary>(`/places/${placeId}/stats/summary`),
    enabled: !!placeId,
  })
}
