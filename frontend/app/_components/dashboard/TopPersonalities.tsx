import type { TopEntity } from '../../../lib/api'

export function TopPersonalities({ entities }: { entities: TopEntity[] }) {
  const colors = ['#60a5fa', '#34d399', '#facc15', '#f87171', '#c084fc', '#fb923c', '#67e8f9', '#f9a8d4']

  if (entities.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune entité</p>

  return (
    <div className="space-y-2">
      {entities.slice(0, 8).map((e, i) => {
        const color = colors[i % colors.length]
        const maxC = entities[0].count
        const initials = e.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
        return (
          <div key={i} className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold"
              style={{
                background: `${color}18`,
                border: `1.5px solid ${color}40`,
                color: color,
              }}>
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.55)' }}>{e.name}</span>
                <span className="text-[10px] ml-2 flex-shrink-0 font-semibold" style={{ color }}>{e.count}</span>
              </div>
              <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div className="h-full rounded-full transition-all duration-700" style={{
                  width: `${(e.count / maxC) * 100}%`,
                  background: `linear-gradient(90deg, ${color}80, ${color})`,
                  boxShadow: `0 0 6px ${color}20`,
                }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
