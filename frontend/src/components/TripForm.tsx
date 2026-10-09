import { useState, type FormEvent } from 'react'
import type { Place, TripRequest } from '@/api'
import PlaceInput from '@/components/PlaceInput'

const INTERVALS = [10, 25, 50] as const

function toLocalInput(date: Date): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

function nextQuarterHour(): Date {
  const d = new Date()
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15, 0, 0)
  return d
}

type Props = { loading: boolean; onSubmit: (trip: TripRequest) => void }

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(() => toLocalInput(nextQuarterHour()))
  const [load, setLoad] = useState('35000')
  const [interval, setIntervalMiles] = useState<TripRequest['interval_miles']>(25)
  const [now] = useState(() => Date.now())

  const ready = origin && destination && departure && load !== ''

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!origin || !destination) return
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_lbs: Math.round(Number(load)),
      interval_miles: interval,
    })
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <PlaceInput label="Origin" placeholder="e.g. Chicago, IL" value={origin} onChange={setOrigin} />
      <PlaceInput label="Destination" placeholder="e.g. Denver, CO" value={destination} onChange={setDestination} />
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-600">Departure</span>
          <input
            type="datetime-local"
            required
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-sm"
            value={departure}
            min={toLocalInput(new Date(now))}
            max={toLocalInput(new Date(now + 7 * 86_400_000))}
            onChange={(e) => setDeparture(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-600">Load weight (lb)</span>
          <input
            type="number"
            required
            min={0}
            max={80000}
            step={500}
            inputMode="numeric"
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
            value={load}
            onChange={(e) => setLoad(e.target.value)}
          />
        </label>
      </div>
      <fieldset>
        <legend className="mb-1 text-xs font-medium text-slate-600">Weather checkpoint every</legend>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-slate-300 text-sm">
          {INTERVALS.map((miles) => (
            <label
              key={miles}
              className={`cursor-pointer py-1.5 text-center has-[:focus-visible]:ring-2 ${
                interval === miles ? 'bg-brand font-medium text-white' : 'bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <input type="radio" name="interval" className="sr-only" checked={interval === miles} onChange={() => setIntervalMiles(miles)} />
              {miles} mi
            </label>
          ))}
        </div>
      </fieldset>
      <button
        type="submit"
        disabled={!ready || loading}
        className="w-full rounded-md bg-brand py-2.5 text-sm font-semibold text-white transition hover:bg-brand-light disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? 'Planning routes…' : 'Find safest route'}
      </button>
    </form>
  )
}
