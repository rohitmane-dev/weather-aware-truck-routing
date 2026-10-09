import type { Feature, FeatureCollection, GeoJsonProperties } from 'geojson'
import { LngLatBounds, Map as MapLibreMap, NavigationControl, Popup, setWorkerUrl, type ExpressionSpecification, type GeoJSONSource } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import type { Checkpoint, Heatmap, Route, TripPlan } from '@/api'
import { LEVELS, formatDuration, formatTime, levelBadge, levelName, routeName } from '@/risk'
import type { TruckPosition } from '@/truck'

// MapLibre resolves its worker relative to its own module, which bundling breaks; ship it as an asset instead.
setWorkerUrl(workerUrl)

const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'
const FONT = ['Noto Sans Bold']
const BRAND = '#0b3d4a'
const LEVEL_COLOR: ExpressionSpecification = [
  'match', ['get', 'level'],
  0, LEVELS[0].color, 1, LEVELS[1].color, 2, LEVELS[2].color, 3, LEVELS[3].color,
  LEVELS[4].color,
]
const MAX_HOUR = 48

type Collection = FeatureCollection
const collection = (features: Feature[] = []): Collection => ({ type: 'FeatureCollection', features })
const point = (coordinates: number[], properties: GeoJsonProperties): Feature => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates },
  properties,
})

/** Heat weight at a fractional hour, blending the two neighbouring forecast hours for smooth playback. */
function heatWeight(hour: number): ExpressionSpecification {
  const i = Math.min(Math.floor(hour), MAX_HOUR - 1)
  const f = hour - i
  return ['/', ['+', ['*', 1 - f, ['get', `h${i}`]], ['*', f, ['get', `h${i + 1}`]]], 4]
}

/** Kernel radius ~2x the grid spacing at every zoom, so density ~= weight and colors track risk levels. */
function heatRadius({ step_deg, points }: Heatmap): ExpressionSpecification {
  const latMid = points.reduce((sum, p) => sum + p[1], 0) / (points.length || 1)
  const r0 = (2 * step_deg * 512) / 360 / Math.sqrt(Math.cos((latMid * Math.PI) / 180))
  return ['interpolate', ['exponential', 2], ['zoom'], 0, r0, 11, r0 * 2 ** 11]
}

function heatFeatures({ points, scores }: Heatmap): Collection {
  return collection(points.map((p, i) => point(p, Object.fromEntries(scores[i].map((s, h) => [`h${h}`, s])))))
}

function routeFeatures(routes: Route[]): Collection {
  return collection(
    routes.flatMap((r) =>
      r.segments.map((s) => ({
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: s.coords },
        properties: { routeId: r.id, level: s.level },
      })),
    ),
  )
}

function checkpointFeatures(routes: Route[]): Collection {
  return collection(routes.flatMap((r) => r.checkpoints.map((cp, idx) => point([cp.lon, cp.lat], { routeId: r.id, idx, level: cp.level }))))
}

function labelFeatures(plan: TripPlan): Collection {
  return collection(
    plan.routes.map((r) => {
      const cp = r.checkpoints[Math.floor(r.checkpoints.length * (0.3 + 0.2 * (r.id % 3)))]
      const m = r.summary.miles_by_level
      const label = [
        `${routeName(r.id)}${r.id === plan.recommended_id ? ' ★ Recommended' : ''}`,
        `${r.distance_mi.toFixed(0)} mi · ${formatDuration(r.duration_s)}`,
        `Severe+ ${(m[3] + m[4]).toFixed(0)} mi · High ${m[2].toFixed(0)} mi · avg ${r.summary.avg_risk.toFixed(2)}`,
      ].join('\n')
      return point([cp.lon, cp.lat], { routeId: r.id, label })
    }),
  )
}

function endpointFeatures(route: Route): Collection {
  const first = route.checkpoints[0]
  const last = route.checkpoints[route.checkpoints.length - 1]
  return collection([point([first.lon, first.lat], { name: 'Origin' }), point([last.lon, last.lat], { name: 'Destination' })])
}

function popupHtml(route: Route, cp: Checkpoint): string {
  const reasons = cp.reasons.map((r) => `<li>${r}</li>`).join('')
  return `<div class="min-w-52 space-y-1 text-xs text-slate-700">
    <div class="flex items-center justify-between gap-3">
      <strong class="text-sm text-slate-900">${routeName(route.id)} · mile ${cp.mile.toFixed(0)}</strong>
      <span class="rounded px-1.5 py-0.5 font-semibold text-white ${levelBadge(cp.level)}">${levelName(cp.level)}</span>
    </div>
    <div>ETA <strong>${formatTime(cp.eta)}</strong></div>
    <div>Wind ${cp.wind_mph.toFixed(0)} mph (gusts ${cp.gust_mph.toFixed(0)}) · Rain ${cp.rain_in.toFixed(2)} in/hr · Snow ${cp.snow_in.toFixed(2)} in/hr</div>
    ${reasons ? `<ul class="list-disc pl-4 text-slate-900">${reasons}</ul>` : ''}
  </div>`
}

function addLayers(map: MapLibreMap) {
  for (const id of ['heat', 'routes', 'checkpoints', 'labels', 'endpoints', 'truck']) {
    map.addSource(id, { type: 'geojson', data: collection() })
  }
  const firstLabel = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
  map.addLayer(
    {
      id: 'heat',
      type: 'heatmap',
      source: 'heat',
      maxzoom: 11,
      paint: {
        'heatmap-weight': heatWeight(0),
        'heatmap-intensity': 0.9,
        'heatmap-color': [
          'interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(22,163,74,0)',
          0.05, 'rgba(22,163,74,0.22)',
          0.25, 'rgba(234,179,8,0.5)',
          0.5, 'rgba(249,115,22,0.6)',
          0.75, 'rgba(220,38,38,0.65)',
          1, 'rgba(107,33,168,0.75)',
        ],
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.9, 11, 0],
      },
    },
    firstLabel,
  )
  const round = { 'line-join': 'round', 'line-cap': 'round' } as const
  map.addLayer({ id: 'routes-alt', type: 'line', source: 'routes', layout: round, paint: { 'line-color': '#64748b', 'line-width': 4, 'line-opacity': 0.55 } })
  map.addLayer({ id: 'routes-hit', type: 'line', source: 'routes', paint: { 'line-width': 18, 'line-opacity': 0 } })
  map.addLayer({ id: 'routes-casing', type: 'line', source: 'routes', layout: round, paint: { 'line-color': '#0f172a', 'line-width': 9, 'line-opacity': 0.85 } })
  map.addLayer({ id: 'routes-selected', type: 'line', source: 'routes', layout: round, paint: { 'line-color': LEVEL_COLOR, 'line-width': 5.5 } })
  map.addLayer({
    id: 'checkpoints-alt',
    type: 'circle',
    source: 'checkpoints',
    paint: { 'circle-color': LEVEL_COLOR, 'circle-radius': 3, 'circle-opacity': 0.75, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1 },
  })
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-color': LEVEL_COLOR,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4, 10, 8],
      'circle-stroke-color': '#fff',
      'circle-stroke-width': 2,
    },
  })
  map.addLayer({
    id: 'endpoints',
    type: 'circle',
    source: 'endpoints',
    paint: { 'circle-color': '#0f172a', 'circle-radius': 7, 'circle-stroke-color': '#fff', 'circle-stroke-width': 3 },
  })
  map.addLayer({
    id: 'endpoint-labels',
    type: 'symbol',
    source: 'endpoints',
    layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 12, 'text-offset': [0, 1.3], 'text-anchor': 'top' },
    paint: { 'text-color': '#0f172a', 'text-halo-color': '#fff', 'text-halo-width': 2 },
  })
  map.addLayer({
    id: 'route-labels',
    type: 'symbol',
    source: 'labels',
    layout: {
      'text-field': ['get', 'label'],
      'text-font': FONT,
      'text-size': 11.5,
      'text-line-height': 1.3,
      'text-variable-anchor': ['left', 'right', 'top', 'bottom'],
      'text-radial-offset': 1.2,
      'text-justify': 'auto',
      'text-max-width': 30,
    },
    paint: { 'text-color': '#0f172a', 'text-halo-color': 'rgba(255,255,255,0.95)', 'text-halo-width': 2 },
  })
  map.addLayer({ id: 'truck-halo', type: 'circle', source: 'truck', paint: { 'circle-color': BRAND, 'circle-radius': 16, 'circle-opacity': 0.2 } })
  map.addLayer({
    id: 'truck',
    type: 'circle',
    source: 'truck',
    paint: { 'circle-color': BRAND, 'circle-radius': 8, 'circle-stroke-color': '#fff', 'circle-stroke-width': 3 },
  })
}

/** MapLibre throws on construction without WebGL2 (GPU acceleration off, blocked by an extension, ...). */
function supportsWebGL2(): boolean {
  const gl = document.createElement('canvas').getContext('webgl2')
  gl?.getExtension('WEBGL_lose_context')?.loseContext()
  return gl !== null
}

function NoWebGL() {
  return (
    <div className="grid h-full place-items-center bg-slate-200 p-6">
      <div role="alert" className="max-w-md space-y-2 rounded-lg bg-white p-5 text-sm text-slate-700 shadow">
        <h2 className="text-base font-semibold text-slate-900">The map needs WebGL2</h2>
        <p>
          This browser isn't providing WebGL2, so the map and weather heatmap can't be drawn. Route options, risk levels and
          the recommendation still work in the side panel.
        </p>
        <p>
          To fix it, turn on hardware acceleration (Chrome: Settings → System → “Use graphics acceleration when available”),
          disable extensions that block WebGL, and restart the browser. <code>chrome://gpu</code> shows the WebGL2 status.
        </p>
      </div>
    </div>
  )
}

type Props = {
  plan: TripPlan | null
  selectedId: number | null
  hoveredId: number | null
  hour: number
  truck: TruckPosition | null
  onSelect: (routeId: number) => void
}

export default function TripMap({ plan, selectedId, hoveredId, hour, truck, onSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  const [webgl2] = useState(supportsWebGL2)
  const latest = useRef({ plan, onSelect })

  useEffect(() => {
    latest.current = { plan, onSelect }
  }, [plan, onSelect])

  useEffect(() => {
    if (!webgl2) return
    const m = new MapLibreMap({
      container: containerRef.current!,
      style: STYLE_URL,
      center: [-96, 38.5],
      zoom: 3.6,
      attributionControl: { compact: true },
    })
    m.addControl(new NavigationControl({ showCompass: false }), 'top-left')
    const popup = new Popup({ maxWidth: '320px' })
    m.on('load', () => {
      addLayers(m)
      setMap(m)
      // One handler, topmost feature wins: selected checkpoint, then alternative checkpoint, then route line.
      m.on('click', (e) => {
        const [hit] = m.queryRenderedFeatures(e.point, { layers: ['checkpoints', 'checkpoints-alt', 'routes-selected', 'routes-hit'] })
        const route = latest.current.plan?.routes.find((r) => r.id === hit?.properties.routeId)
        if (!hit || !route) return
        if (hit.layer.id === 'routes-hit') {
          latest.current.onSelect(route.id)
        } else if (hit.layer.id.startsWith('checkpoints')) {
          const cp = route.checkpoints[hit.properties.idx as number]
          popup.setLngLat([cp.lon, cp.lat]).setHTML(popupHtml(route, cp)).addTo(m)
        }
      })
    })
    for (const layer of ['checkpoints', 'checkpoints-alt', 'routes-hit']) {
      m.on('mouseenter', layer, () => (m.getCanvas().style.cursor = 'pointer'))
      m.on('mouseleave', layer, () => (m.getCanvas().style.cursor = ''))
    }
    return () => m.remove()
  }, [webgl2])

  useEffect(() => {
    if (!map) return
    const source = (id: string) => map.getSource(id) as GeoJSONSource
    source('heat').setData(plan ? heatFeatures(plan.heatmap) : collection())
    source('routes').setData(plan ? routeFeatures(plan.routes) : collection())
    source('checkpoints').setData(plan ? checkpointFeatures(plan.routes) : collection())
    source('labels').setData(plan ? labelFeatures(plan) : collection())
    source('endpoints').setData(plan ? endpointFeatures(plan.routes[0]) : collection())
    if (!plan) return
    map.setPaintProperty('heat', 'heatmap-radius', heatRadius(plan.heatmap))
    const bounds = new LngLatBounds()
    for (const r of plan.routes) for (const s of r.segments) for (const c of s.coords) bounds.extend(c)
    map.fitBounds(bounds, { padding: { top: 60, left: 60, right: 60, bottom: 150 }, duration: 800 })
  }, [map, plan])

  useEffect(() => {
    if (!map) return
    const isSelected: ExpressionSpecification = ['==', ['get', 'routeId'], selectedId ?? -1]
    for (const id of ['routes-casing', 'routes-selected', 'checkpoints']) map.setFilter(id, isSelected)
    for (const id of ['routes-alt', 'routes-hit', 'checkpoints-alt']) map.setFilter(id, ['!', isSelected])
  }, [map, selectedId])

  useEffect(() => {
    if (!map) return
    const isHovered: ExpressionSpecification = ['==', ['get', 'routeId'], hoveredId ?? -1]
    map.setPaintProperty('routes-alt', 'line-width', ['case', isHovered, 6, 4])
    map.setPaintProperty('routes-alt', 'line-opacity', ['case', isHovered, 0.95, 0.55])
    map.setPaintProperty('routes-alt', 'line-color', ['case', isHovered, '#334155', '#64748b'])
  }, [map, hoveredId])

  useEffect(() => {
    map?.setPaintProperty('heat', 'heatmap-weight', heatWeight(hour))
  }, [map, hour])

  useEffect(() => {
    if (!map) return
    ;(map.getSource('truck') as GeoJSONSource).setData(truck ? collection([point(truck.lonLat, {})]) : collection())
  }, [map, truck])

  if (!webgl2) return <NoWebGL />
  return <div ref={containerRef} className="h-full w-full" aria-label="Route map" role="region" />
}
