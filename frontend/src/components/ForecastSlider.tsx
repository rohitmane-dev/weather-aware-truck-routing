import { useEffect, useRef, useState } from 'react'
import { formatTime } from '@/risk'

const MAX_HOUR = 48
const HOURS_PER_SECOND = 3

type Props = { start: string; hour: number; onChange: (hour: number) => void; caption: string }

export default function ForecastSlider({ start, hour, onChange, caption }: Props) {
  const [playing, setPlaying] = useState(false)
  const hourRef = useRef(hour)

  useEffect(() => {
    hourRef.current = hour
  }, [hour])

  useEffect(() => {
    if (!playing) return
    let frame = 0
    let last = performance.now()
    let current = hourRef.current >= MAX_HOUR ? 0 : hourRef.current
    const tick = (now: number) => {
      current = Math.min(MAX_HOUR, current + ((now - last) / 1000) * HOURS_PER_SECOND)
      last = now
      onChange(current)
      if (current < MAX_HOUR) frame = requestAnimationFrame(tick)
      else setPlaying(false)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, onChange])

  const time = new Date(Date.parse(start) + hour * 3_600_000)
  return (
    <div className="rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          className="grid size-9 shrink-0 place-items-center rounded-full bg-brand text-white hover:bg-brand-light"
          aria-label={playing ? 'Pause forecast playback' : 'Play forecast'}
        >
          {playing ? (
            <svg viewBox="0 0 24 24" className="size-4 fill-current"><path d="M6 5h4v14H6zM14 5h4v14h-4z" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" className="size-4 fill-current"><path d="M7 5v14l12-7z" /></svg>
          )}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-semibold text-slate-900">
              Forecast +{Math.floor(hour)}h · {formatTime(time)}
            </span>
            <span className="truncate text-slate-500">{caption}</span>
          </div>
          <input
            type="range"
            min={0}
            max={MAX_HOUR}
            step={0.25}
            value={hour}
            onChange={(e) => {
              setPlaying(false)
              onChange(Number(e.target.value))
            }}
            className="mt-1 w-full accent-brand"
            aria-label="Forecast hour"
          />
          <div className="flex justify-between text-[10px] text-slate-400">
            <span>0h</span><span>12h</span><span>24h</span><span>36h</span><span>48h</span>
          </div>
        </div>
      </div>
    </div>
  )
}
