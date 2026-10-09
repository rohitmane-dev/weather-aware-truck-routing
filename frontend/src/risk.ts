import type { Level } from '@/api'

// `color` feeds map styles; `badge` is the matching Tailwind class (same hex) for HTML.
export const LEVELS: { name: string; color: string; badge: string }[] = [
  { name: 'Low', color: '#16a34a', badge: 'bg-green-600' },
  { name: 'Moderate', color: '#eab308', badge: 'bg-yellow-500' },
  { name: 'High', color: '#f97316', badge: 'bg-orange-500' },
  { name: 'Severe', color: '#dc2626', badge: 'bg-red-600' },
  { name: 'No Travel', color: '#6b21a8', badge: 'bg-purple-800' },
]

export const levelName = (level: Level) => LEVELS[level].name
export const levelBadge = (level: Level) => LEVELS[level].badge
export const routeName = (id: number) => `Route ${String.fromCharCode(65 + id)}`

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

const timeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})
export const formatTime = (iso: string | Date) => timeFormat.format(new Date(iso))
