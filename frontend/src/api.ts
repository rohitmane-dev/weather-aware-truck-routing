export type Level = 0 | 1 | 2 | 3 | 4
export type LonLat = [number, number]

export type Place = { label: string; lat: number; lon: number }

export type TripRequest = {
  origin: Place
  destination: Place
  departure: string
  load_lbs: number
  interval_miles: 10 | 25 | 50
}

export type Checkpoint = {
  mile: number
  lat: number
  lon: number
  eta: string
  wind_mph: number
  gust_mph: number
  rain_in: number
  snow_in: number
  level: Level
  reasons: string[]
}

export type Route = {
  id: number
  rank: number
  why: string
  distance_mi: number
  duration_s: number
  traffic_delay_s: number
  arrival: string
  segments: { level: Level; coords: LonLat[] }[]
  checkpoints: Checkpoint[]
  summary: { miles_by_level: number[]; avg_risk: number; max_level: Level }
}

export type Heatmap = { start: string; step_deg: number; points: LonLat[]; scores: number[][] }

export type TripPlan = {
  departure: string
  routes: Route[]
  recommended_id: number
  all_routes_unsafe: boolean
  heatmap: Heatmap
}

function firstMessage(body: unknown): string | undefined {
  if (typeof body === 'string') return body
  if (Array.isArray(body)) return body.map(firstMessage).find(Boolean)
  if (body && typeof body === 'object') return Object.values(body).map(firstMessage).find(Boolean)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new Error(firstMessage(body) ?? `Request failed (HTTP ${res.status})`)
  return body as T
}

export function geocode(query: string, signal: AbortSignal): Promise<Place[]> {
  return request(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
}

export function planTrip(trip: TripRequest): Promise<TripPlan> {
  return request('/api/trip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(trip),
  })
}
