export function GravityDonut({ distribution }: {
  distribution: { low: number; medium: number; high: number; critical: number }
}) {
  const total = distribution.low + distribution.medium + distribution.high + distribution.critical
  if (total === 0) return <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</p>

  const segments = [
    { key: 'low', label: 'Faible', count: distribution.low, color: '#34d399' },
    { key: 'medium', label: 'Moyen', count: distribution.medium, color: '#fbbf24' },
    { key: 'high', label: 'Élevé', count: distribution.high, color: '#fb923c' },
    { key: 'critical', label: 'Critique', count: distribution.critical, color: '#f87171' },
  ]

  const radius = 36, cx = 45, cy = 45
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const arcs = segments.filter(s => s.count > 0).map(s => {
    const pct = s.count / total
    const len = pct * circumference
    const arc = { ...s, pct, dasharray: `${len} ${circumference - len}`, dashoffset: -offset }
    offset += len
    return arc
  })

  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 90 90" className="w-20 h-20 flex-shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="10" />
        {arcs.map(a => (
          <circle key={a.key} cx={cx} cy={cy} r={radius} fill="none"
            stroke={a.color} strokeWidth="10"
            strokeDasharray={a.dasharray} strokeDashoffset={a.dashoffset}
            strokeLinecap="butt"
            style={{ filter: `drop-shadow(0 0 3px ${a.color}40)` }} />
        ))}
        <text x={cx} y={cy + 4} textAnchor="middle" fill="white" fontSize="14" fontWeight="bold"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}>
          {total}
        </text>
      </svg>
      <div className="space-y-1 flex-1">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px] flex-1" style={{ color: 'rgba(255,255,255,0.4)' }}>{s.label}</span>
            <span className="text-[10px] font-semibold" style={{ color: s.color }}>
              {s.count} <span style={{ color: 'rgba(255,255,255,0.12)' }}>({total > 0 ? Math.round(s.count / total * 100) : 0}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
