import Link from 'next/link'
import type { Affair } from '../../../lib/api'
import { timeAgo, themeColor } from '../../../lib/formatters'

export function AffairTimeline({ affairs }: { affairs: Affair[] }) {
  const sorted = [...affairs]
    .filter(a => a.created_at)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 12)

  if (sorted.length === 0) {
    return <div className="text-center py-6 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire</div>
  }

  const now = Date.now()
  const oldest = new Date(sorted[sorted.length - 1].created_at).getTime()
  const range = Math.max(now - oldest, 86400000)

  const priorityColor = (p: string) =>
    p === 'hot' ? '#f87171' : p === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      <div className="h-px w-full mb-1" style={{ background: 'rgba(255,255,255,0.06)' }} />

      <div className="flex justify-between mb-4">
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>
          {new Date(oldest).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
        </span>
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>Aujourd'hui</span>
      </div>

      <div className="space-y-2">
        {sorted.map((affair) => {
          const created = new Date(affair.created_at).getTime()
          const lastAct = affair.last_activity ? new Date(affair.last_activity).getTime() : created
          const startPct = ((created - oldest) / range) * 100
          const endPct = Math.min(((lastAct - oldest) / range) * 100, 100)
          const widthPct = Math.max(endPct - startPct, 2)
          const color = priorityColor(affair.priority || 'minor')
          const tc = themeColor(affair.theme)

          return (
            <Link key={affair._id} href={`/affairs/${affair._id}`}>
              <div className="group flex items-center gap-2 cursor-pointer hover:bg-white/[0.02] rounded-lg px-2 py-1.5 transition-all">
                <div className="w-32 lg:w-40 flex-shrink-0">
                  <p className="text-[11px] truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.45)' }}>
                    {affair.title || affair.primary_entity || '—'}
                  </p>
                  <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.12)' }}>
                    {timeAgo(affair.created_at)}
                  </p>
                </div>

                <div className="flex-1 h-5 relative rounded-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div className="absolute h-full rounded-sm transition-all duration-500 group-hover:brightness-125 flex items-center"
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                      minWidth: 8,
                      background: `linear-gradient(90deg, ${color}60, ${color})`,
                      boxShadow: `0 0 6px ${color}20`,
                    }}>
                    {widthPct > 15 && (
                      <span className="text-[8px] font-bold px-1 truncate" style={{ color: 'white' }}>
                        {affair.item_count || 0}
                      </span>
                    )}
                  </div>
                </div>

                <div className="w-10 text-right flex-shrink-0">
                  <span className="text-[10px] font-bold" style={{ color }}>
                    {Math.round((affair.bmg || 0) * 100)}
                  </span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>

      <div className="flex items-center gap-3 mt-3 justify-center">
        {[
          { label: 'Urgente', color: '#f87171' },
          { label: 'Suivi', color: '#fbbf24' },
          { label: 'Mineure', color: '#34d399' },
        ].map(l => (
          <div key={l.label} className="flex items-center gap-1">
            <div className="w-3 h-1.5 rounded-sm" style={{ background: l.color }} />
            <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
