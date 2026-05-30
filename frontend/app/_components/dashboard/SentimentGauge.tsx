export function SentimentGauge({ sentimentDist }: { sentimentDist: Record<string, number> }) {
  const entries = Object.entries(sentimentDist)
  const total = entries.reduce((s, [, c]) => s + c, 0)
  if (total === 0) return <div className="text-center py-8 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</div>

  const positif = (sentimentDist['positif'] || sentimentDist['positive'] || 0)
  const negatif = (sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0)
  const neutre = (sentimentDist['neutre'] || sentimentDist['neutral'] || 0)
  const mixte = (sentimentDist['mixte'] || sentimentDist['mixed'] || 0)

  const score = total > 0
    ? Math.round(((positif * 100 + neutre * 55 + mixte * 50 + negatif * 10) / total))
    : 50

  const angle = (score / 100) * 180
  const r = 70
  const cx = 80, cy = 80

  const arcPath = (startAngle: number, endAngle: number) => {
    const s = (startAngle - 180) * Math.PI / 180
    const e = (endAngle - 180) * Math.PI / 180
    const x1 = cx + r * Math.cos(s)
    const y1 = cy + r * Math.sin(s)
    const x2 = cx + r * Math.cos(e)
    const y2 = cy + r * Math.sin(e)
    const large = endAngle - startAngle > 180 ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
  }

  const needleAngle = (angle - 180) * Math.PI / 180
  const needleLen = r - 8
  const nx = cx + needleLen * Math.cos(needleAngle)
  const ny = cy + needleLen * Math.sin(needleAngle)

  const moodEmoji = score >= 70 ? '😊' : score >= 50 ? '😐' : score >= 30 ? '😟' : '😡'
  const moodLabel = score >= 70 ? 'Positif' : score >= 50 ? 'Neutre' : score >= 30 ? 'Tendu' : 'Négatif'
  const moodColor = score >= 70 ? '#34d399' : score >= 50 ? '#5FD0E0' : score >= 30 ? '#fbbf24' : '#f87171'

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 160 95" className="w-full max-w-[200px]">
        <path d={arcPath(0, 60)} fill="none" stroke="#f87171" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(60, 120)} fill="none" stroke="#fbbf24" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(120, 180)} fill="none" stroke="#34d399" strokeWidth="10" strokeLinecap="round" opacity="0.15" />

        <path d={arcPath(0, angle)} fill="none" stroke={moodColor} strokeWidth="10" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${moodColor}50)` }} />

        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
        <circle cx={cx} cy={cy} r="4" fill="white" opacity="0.9" />

        <text x={cx} y={cy - 12} textAnchor="middle" fill="white" fontSize="22" fontWeight="bold">{score}</text>
        <text x={cx} y={cy - 0} textAnchor="middle" fill={moodColor} fontSize="8" fontWeight="500">{moodLabel}</text>
      </svg>

      <div className="text-2xl mt-1">{moodEmoji}</div>

      <div className="flex items-center gap-3 mt-3">
        {[
          { label: 'Positif', count: positif, color: '#34d399' },
          { label: 'Neutre', count: neutre, color: '#5FD0E0' },
          { label: 'Négatif', count: negatif, color: '#f87171' },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {s.label} <span style={{ color: s.color }}>{total > 0 ? Math.round(s.count / total * 100) : 0}%</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
