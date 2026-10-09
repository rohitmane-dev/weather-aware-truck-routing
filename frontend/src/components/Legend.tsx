import { LEVELS } from '@/risk'

export default function Legend() {
  return (
    <div className="rounded-lg bg-white/95 p-2.5 text-[11px] shadow-md backdrop-blur">
      <div className="mb-1 font-semibold text-slate-700">Weather risk</div>
      <ul className="space-y-0.5">
        {LEVELS.map((l) => (
          <li key={l.name} className="flex items-center gap-1.5">
            <span className={`inline-block size-2.5 rounded-full ${l.badge}`} />
            {l.name}
          </li>
        ))}
      </ul>
      <div className="mt-1.5 hidden border-t border-slate-200 pt-1.5 text-slate-500 md:block">
        Heatmap: corridor risk at slider time
        <br />
        Gray lines: alternative routes
      </div>
    </div>
  )
}
