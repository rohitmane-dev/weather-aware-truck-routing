import { useEffect, useId, useState, type KeyboardEvent } from 'react'
import { geocode, type Place } from '@/api'

type Props = {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
}

export default function PlaceInput({ label, placeholder, value, onChange }: Props) {
  const [text, setText] = useState(value?.label ?? '')
  const [results, setResults] = useState<{ query: string; places: Place[] }>({ query: '', places: [] })
  const [active, setActive] = useState(0)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const id = useId()

  const options = results.query === text ? results.places : []

  useEffect(() => {
    if (text.trim().length < 3 || text === value?.label) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const places = await geocode(text.trim(), controller.signal)
        setResults({ query: text, places })
        setActive(0)
        setOpen(true)
        setError(null)
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Search failed')
      }
    }, 300)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [text, value])

  function choose(place: Place) {
    onChange(place)
    setText(place.label)
    setOpen(false)
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || options.length === 0) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((i) => (i + step + options.length) % options.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(options[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const listId = `${id}-list`
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">
        {label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        autoComplete="off"
        className={`w-full rounded-md border bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-brand-light/40 ${
          value ? 'border-emerald-500' : 'border-slate-300'
        }`}
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          if (value) onChange(null)
        }}
        onFocus={() => options.length > 0 && setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      {open && options.length > 0 && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg">
          {options.map((place, i) => (
            <li
              key={`${place.lat},${place.lon},${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-slate-100' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(place)
              }}
              onMouseEnter={() => setActive(i)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
