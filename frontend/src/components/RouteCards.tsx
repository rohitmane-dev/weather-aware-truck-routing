import type { Route } from '@/api'
import { LEVELS, formatDuration, formatTime, levelBadge, levelName, routeName } from '@/risk'

type Props = {
  routes: Route[]
  recommendedId: number
  selectedId: number | null
  onSelect: (id: number) => void
  onHover: (id: number | null) => void
}

export default function RouteCards({ routes, recommendedId, selectedId, onSelect, onHover }: Props) {
  return (
    <ul className="space-y-3">
      {routes.map((r) => {
        const recommended = r.id === recommendedId
        const total = r.distance_mi || 1
        return (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => onSelect(r.id)}
              onMouseEnter={() => onHover(r.id)}
              onMouseLeave={() => onHover(null)}
              aria-pressed={r.id === selectedId}
              className={`w-full rounded-lg border bg-white p-3 text-left transition hover:shadow-md ${
                r.id === selectedId ? 'border-brand ring-2 ring-brand/30' : 'border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-400">#{r.rank}</span>
                  <span className="font-semibold">{routeName(r.id)}</span>
                  {recommended && <span className="rounded-full bg-brand px-2 py-0.5 text-[11px] font-semibold text-white">Recommended</span>}
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold text-white ${levelBadge(r.summary.max_level)}`}>
                  max {levelName(r.summary.max_level)}
                </span>
              </div>

              <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <dt className="text-slate-500">Distance</dt>
                  <dd className="font-medium">{r.distance_mi.toFixed(0)} mi</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Drive time</dt>
                  <dd className="font-medium">{formatDuration(r.duration_s)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Avg risk</dt>
                  <dd className="font-medium">{r.summary.avg_risk.toFixed(2)} / 4</dd>
                </div>
                <div className="col-span-3">
                  <dt className="sr-only">Arrival</dt>
                  <dd className="text-slate-600">
                    Arrives {formatTime(r.arrival)}
                    {r.traffic_delay_s > 60 && ` · ${formatDuration(r.traffic_delay_s)} traffic`}
                  </dd>
                </div>
              </dl>

              <div className="mt-2 flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-label="Miles by risk level">
                {r.summary.miles_by_level.map((miles, level) =>
                  miles > 0 ? (
                    <div
                      key={level}
                      className={LEVELS[level].badge}
                      style={{ width: `${(miles / total) * 100}%` }}
                      title={`${LEVELS[level].name}: ${miles.toFixed(1)} mi`}
                    />
                  ) : null,
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-slate-500">
                {r.summary.miles_by_level.map((miles, level) =>
                  miles > 0 ? (
                    <span key={level}>
                      {LEVELS[level].name} {miles.toFixed(0)} mi
                    </span>
                  ) : null,
                )}
              </div>
              <p className={`mt-2 text-xs ${recommended ? 'text-brand' : 'text-slate-500'}`}>{r.why}</p>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
