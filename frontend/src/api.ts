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

async function parse<T>(res: Response): Promise<T> {
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) throw new Error(firstMessage(body) ?? `Request failed (HTTP ${res.status})`)
  return body as T
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  return parse<T>(await fetch(url, init))
}

export function geocode(query: string, signal: AbortSignal): Promise<Place[]> {
  return request(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
}

type WeatherRequest = { url: string; params: Record<string, string>; points: [number, number][] }
type BrowserWeather = { lat: number; lon: number; hourly: unknown }[]

/** Open-Meteo limits free use per IP and cloud hosts share IPs, so when the server is rate-limited it
 *  sends back the exact query and the browser fetches the forecasts on its own quota. */
async function fetchWeather({ url, params, points }: WeatherRequest): Promise<BrowserWeather> {
  const batches: [number, number][][] = []
  for (let i = 0; i < points.length; i += 100) batches.push(points.slice(i, i + 100))
  const results = await Promise.all(
    batches.map(async (batch) => {
      const query = new URLSearchParams({
        ...params,
        latitude: batch.map((p) => p[0]).join(','),
        longitude: batch.map((p) => p[1]).join(','),
      })
      const data = await request<{ hourly: unknown } | { hourly: unknown }[]>(`${url}?${query}`)
      return (Array.isArray(data) ? data : [data]).map((d, i) => ({ lat: batch[i][0], lon: batch[i][1], hourly: d.hourly }))
    }),
  )
  return results.flat()
}

export async function planTrip(trip: TripRequest): Promise<TripPlan> {
  const post = (body: object) =>
    fetch('/api/trip', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  let res = await post(trip)
  if (res.status === 503) {
    const body = (await res.clone().json().catch(() => null)) as { weather_request?: WeatherRequest } | null
    if (body?.weather_request) res = await post({ ...trip, weather: await fetchWeather(body.weather_request) })
  }
  return parse<TripPlan>(res)
}
