import { themeColor, themeLabel } from '../../../lib/formatters'

export function TrendingTopics({ themes }: { themes: Record<string, number> }) {
  const sorted = Object.entries(themes).sort(([, a], [, b]) => b - a)
  if (sorted.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune donnée</p>

  const maxCount = sorted[0][1]

  return (
    <div className="space-y-3">
      {sorted.slice(0, 8).map(([theme, count], i) => {
        const color = themeColor(theme)
        const pct = Math.round((count / maxCount) * 100)
        return (
          <div key={theme}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold w-4 text-center" style={{ color: 'rgba(255,255,255,0.15)' }}>#{i + 1}</span>
                <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.55)' }}>{themeLabel(theme)}</span>
              </div>
              <span className="text-[11px] font-bold" style={{ color }}>{count} affaire{count > 1 ? 's' : ''}</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div className="h-full rounded-full transition-all duration-1000" style={{
                width: `${pct}%`,
                background: `linear-gradient(90deg, ${color}90, ${color})`,
                boxShadow: `0 0 8px ${color}30`,
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}
