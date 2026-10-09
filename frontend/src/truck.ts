import type { LonLat, Route } from '@/api'

export type TruckPosition = { lonLat: LonLat; mile: number; status: 'waiting' | 'driving' | 'arrived' }

function lerp(xs: number[], ys: number[], x: number): number {
  if (x <= xs[0]) return ys[0]
  for (let i = 1; i < xs.length; i++) {
    if (x <= xs[i]) return ys[i - 1] + ((ys[i] - ys[i - 1]) * (x - xs[i - 1])) / (xs[i] - xs[i - 1] || 1)
  }
  return ys[ys.length - 1]
}

function haversineMi([lon1, lat1]: LonLat, [lon2, lat2]: LonLat): number {
  const rad = Math.PI / 180
  const h = Math.sin(((lat2 - lat1) * rad) / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2
  return 2 * 3958.8 * Math.asin(Math.sqrt(h))
}

/** Where the truck is at `time` on `route`: ETA -> mile from checkpoints, then mile -> point along the geometry. */
export function truckAt(route: Route, time: number): TruckPosition {
  const cps = route.checkpoints
  const etas = cps.map((cp) => Date.parse(cp.eta))
  const mile = lerp(etas, cps.map((cp) => cp.mile), time)

  const line = route.segments.flatMap((s, i) => (i === 0 ? s.coords : s.coords.slice(1)))
  const cum = [0]
  for (let i = 1; i < line.length; i++) cum.push(cum[i - 1] + haversineMi(line[i - 1], line[i]))
  const scale = route.distance_mi / (cum[cum.length - 1] || 1)
  const miles = cum.map((c) => c * scale)
  const lonLat: LonLat = [lerp(miles, line.map((p) => p[0]), mile), lerp(miles, line.map((p) => p[1]), mile)]

  const status = time < etas[0] ? 'waiting' : time >= etas[etas.length - 1] ? 'arrived' : 'driving'
  return { lonLat, mile, status }
}
