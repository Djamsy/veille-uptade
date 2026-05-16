import type { DailyActivity } from '../../../lib/api'

export function ActivityMiniChart({ data }: { data: DailyActivity[] }) {
  const maxArticles = Math.max(...data.map(d => d.articles), 1)
  return (
    <div className="flex items-end gap-2 h-32">
      {data.map((d, i) => {
        const h = (d.articles / maxArticles) * 100
        const isToday = i === data.length - 1
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1.5 group relative">
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-200
              px-2.5 py-1 rounded-lg text-[9px] font-medium whitespace-nowrap z-10 pointer-events-none"
              style={{ background: 'rgba(37,99,235,0.95)', color: 'white', boxShadow: '0 4px 12px rgba(37,99,235,0.3)' }}>
              {d.articles} articles · {d.events} événements
            </div>
            <div className="w-full rounded-t-md transition-all duration-700 group-hover:brightness-125 relative"
              style={{
                height: `${Math.max(h, 4)}%`,
                background: isToday
                  ? 'linear-gradient(180deg, #facc15 0%, #f59e0b 100%)'
                  : `linear-gradient(180deg, #60a5fa 0%, #1d4ed8 100%)`,
                boxShadow: isToday ? '0 -2px 12px rgba(245,158,11,0.3)' : d.articles > 0 ? '0 -2px 12px rgba(37,99,235,0.15)' : 'none',
                borderRadius: '4px 4px 2px 2px',
              }}>
              {d.articles > 0 && (
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ color: isToday ? '#facc15' : '#60a5fa' }}>
                  {d.articles}
                </span>
              )}
            </div>
            <span className={`text-[9px] leading-none font-medium ${isToday ? 'text-white/60' : ''}`}
              style={{ color: isToday ? undefined : 'rgba(255,255,255,0.2)' }}>
              {d.label.split(' ')[0]}
            </span>
          </div>
        )
      })}
    </div>
  )
}
