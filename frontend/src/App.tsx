import { useMemo, useState } from 'react'
import { planTrip, type TripPlan, type TripRequest } from '@/api'
import ForecastSlider from '@/components/ForecastSlider'
import Legend from '@/components/Legend'
import RouteCards from '@/components/RouteCards'
import TripForm from '@/components/TripForm'
import TripMap from '@/components/TripMap'
import { routeName } from '@/risk'
import { truckAt } from '@/truck'

export default function App() {
  const [plan, setPlan] = useState<TripPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [hour, setHour] = useState(0)

  async function submit(trip: TripRequest) {
    setLoading(true)
    setError(null)
    try {
      const result = await planTrip(trip)
      setPlan(result)
      setSelectedId(result.recommended_id)
      setHour(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null
  const truck = useMemo(
    () => (plan && selected ? truckAt(selected, Date.parse(plan.heatmap.start) + hour * 3_600_000) : null),
    [plan, selected, hour],
  )
  const caption = selected && truck
    ? truck.status === 'waiting'
      ? `Truck waiting at origin · ${routeName(selected.id)}`
      : truck.status === 'arrived'
        ? `Truck arrived · ${routeName(selected.id)}`
        : `Truck at mile ${truck.mile.toFixed(0)} · ${routeName(selected.id)}`
    : ''

  return (
    <div className="flex min-h-full flex-col md:h-full md:flex-row">
      <aside className="flex w-full flex-col gap-4 border-slate-200 bg-slate-50 p-4 md:w-[400px] md:shrink-0 md:overflow-y-auto md:border-r">
        <header className="flex items-center gap-2.5">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div>
            <h1 className="text-base leading-tight font-bold text-brand">Weather-Aware Truck Routing</h1>
            <p className="text-xs text-slate-500">Safest route by weather, load and travel time</p>
          </div>
        </header>

        <TripForm loading={loading} onSubmit={submit} />

        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {plan ? (
          <section className="space-y-3">
            {plan.all_routes_unsafe && (
              <div role="alert" className="rounded-md border border-purple-200 bg-purple-50 p-3 text-sm text-purple-900">
                Every route crosses <strong>No Travel</strong> conditions at this departure time. Consider delaying departure or
                reducing load.
              </div>
            )}
            <h2 className="text-sm font-semibold text-slate-700">
              {plan.routes.length} route option{plan.routes.length === 1 ? '' : 's'} · ranked by safety, then time
            </h2>
            <RouteCards
              routes={plan.routes}
              recommendedId={plan.recommended_id}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onHover={setHoveredId}
            />
          </section>
        ) : (
          <section className="space-y-2 text-xs text-slate-600">
            <h2 className="text-sm font-semibold text-slate-700">How it works</h2>
            <ol className="list-decimal space-y-1 pl-4">
              <li>Three truck routes from TomTom, using your load weight and departure time.</li>
              <li>Weather is sampled along each route at the truck's ETA for that checkpoint.</li>
              <li>Each checkpoint is rated Low → No Travel from wind, rain, snow and load rules.</li>
              <li>The recommendation prefers fewest No Travel / Severe / High miles, then lower average risk, then shorter time.</li>
            </ol>
          </section>
        )}
      </aside>

      <main className="relative h-[75vh] md:h-auto md:flex-1">
        <TripMap plan={plan} selectedId={selectedId} hoveredId={hoveredId} hour={hour} truck={truck} onSelect={setSelectedId} />
        <div className="pointer-events-none absolute top-3 right-3">
          <div className="pointer-events-auto">
            <Legend />
          </div>
        </div>
        {plan && (
          <div className="absolute inset-x-3 bottom-8 md:right-auto md:left-1/2 md:w-[560px] md:-translate-x-1/2">
            <ForecastSlider start={plan.heatmap.start} hour={hour} onChange={setHour} caption={caption} />
          </div>
        )}
        {loading && (
          <div className="absolute inset-0 grid place-items-center bg-white/40 backdrop-blur-[1px]">
            <div className="flex items-center gap-3 rounded-lg bg-white px-4 py-3 text-sm shadow-lg">
              <span className="size-4 animate-spin rounded-full border-2 border-brand border-t-transparent" />
              Routing and sampling weather at each checkpoint ETA…
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
