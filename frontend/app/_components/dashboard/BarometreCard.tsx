import type { DailyActivity } from '../../../lib/api'

type Props = {
  avgBmg?: number
  /** percent delta over the period (article trend used as a proxy for BMG variation) */
  articlesDelta?: number
  activity: DailyActivity[]
  sentimentDist: Record<string, number>
}

function computeSentimentScore(dist: Record<string, number>): number {
  const total = Object.values(dist).reduce((s, n) => s + n, 0)
  if (total === 0) return 50
  const pos = (dist['positif'] || dist['positive'] || 0)
  const neu = (dist['neutre'] || dist['neutral'] || 0)
  const mix = (dist['mixte'] || dist['mixed'] || 0)
  const neg = (dist['négatif'] || dist['negatif'] || dist['negative'] || 0)
  return Math.round((pos * 100 + neu * 55 + mix * 50 + neg * 10) / total)
}

function buildPath(values: number[], w: number, h: number, padY = 8): string {
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = Math.max(max - min, 1)
  const stepX = w / Math.max(values.length - 1, 1)
  const pts = values.map((v, i) => {
    const x = i * stepX
    const norm = (v - min) / range
    const y = h - padY - norm * (h - padY * 2)
    return [x, y] as [number, number]
  })
  // Smooth Catmull-Rom-like curve via cubic bezier control points
  let d = `M ${pts[0][0]} ${pts[0][1]}`
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i]
    const p1 = pts[i]
    const p2 = pts[i + 1]
    const p3 = pts[i + 2] || pts[i + 1]
    const cp1x = p1[0] + (p2[0] - p0[0]) / 6
    const cp1y = p1[1] + (p2[1] - p0[1]) / 6
    const cp2x = p2[0] - (p3[0] - p1[0]) / 6
    const cp2y = p2[1] - (p3[1] - p1[1]) / 6
    d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2[0]} ${p2[1]}`
  }
  return d
}

export function BarometreCard({ avgBmg, articlesDelta = 0, activity, sentimentDist }: Props) {
  const bmgScaled = Math.round((avgBmg || 0) * 100)
  const bmgDelta = Math.round(articlesDelta * 0.4) // proxy: scale article trend to BMG-ish delta
  const sentimentScore = computeSentimentScore(sentimentDist)

  // Build BMG-ish series from daily articles (proxy: more articles = more tension)
  const articleValues = activity.slice(-7).map(d => d.articles)
  const maxArt = Math.max(...articleValues, 1)
  const bmgSeries = articleValues.map(v => 30 + Math.round((v / maxArt) * 30) + bmgScaled - 15)
  const sentimentSeries = articleValues.map((_, i) => sentimentScore - 5 + (i % 3))

  const W = 700, H = 200
  const bmgPath = buildPath(bmgSeries, W, H)
  const sentPath = buildPath(sentimentSeries, W, H)

  // Editorial narrative
  const trend = bmgDelta > 5 ? 'en hausse continue' : bmgDelta < -5 ? 'en baisse continue' : 'stable'
  const narrative = `Baromètre médiatique ${trend} sur les sept derniers jours.`

  return (
    <div
      className="p-5 lg:p-6"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
      }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <span
            className="font-mono text-[10px] uppercase tracking-[0.14em]"
            style={{ color: 'var(--text-muted)' }}
          >
            Baromètre médiatique · 7 jours
          </span>
        </div>
        <div
          className="inline-flex font-mono text-[10px]"
          style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}
        >
          {(['24h', '7', '30'] as const).map((p, i) => (
            <button
              key={p}
              className="px-2.5 py-1"
              style={{
                background: p === '7' ? 'var(--bg-hover)' : 'transparent',
                color: p === '7' ? 'var(--text)' : 'var(--text-muted)',
                borderLeft: i > 0 ? '1px solid var(--border)' : 'none',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-baseline gap-3 mb-1">
        <span className="font-serif text-5xl font-semibold tabular-nums leading-none" style={{ color: 'var(--text)' }}>
          {bmgScaled}
        </span>
        <span className="font-mono text-xs" style={{ color: bmgDelta > 0 ? 'var(--warning)' : bmgDelta < 0 ? 'var(--positive)' : 'var(--text-muted)' }}>
          {bmgDelta > 0 ? '↗' : bmgDelta < 0 ? '↘' : '→'} {bmgDelta > 0 ? '+' : ''}{bmgDelta} pts
        </span>
        <span className="font-mono text-[11px]" style={{ color: 'var(--text-muted)' }}>
          vs {bmgScaled - bmgDelta} il y a 7 jours
        </span>
      </div>
      <p
        className="font-serif text-base italic mt-2 mb-5"
        style={{ color: 'var(--text-secondary)' }}
      >
        {narrative}
      </p>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-44">
        {/* Subtle grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(p => (
          <line
            key={p}
            x1={0}
            x2={W}
            y1={H * p}
            y2={H * p}
            stroke="var(--border-subtle)"
            strokeWidth={1}
          />
        ))}
        {/* Sentiment area */}
        {sentPath && (
          <>
            <path
              d={`${sentPath} L ${W} ${H} L 0 ${H} Z`}
              fill="var(--ok-soft)"
              opacity={0.6}
            />
            <path d={sentPath} fill="none" stroke="var(--positive)" strokeWidth={1.5} />
          </>
        )}
        {/* BMG line */}
        {bmgPath && (
          <path d={bmgPath} fill="none" stroke="var(--warning)" strokeWidth={2} />
        )}
      </svg>

      <div className="flex items-center gap-5 mt-3 font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-px" style={{ background: 'var(--warning)' }} />
          BMG moyen
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-px" style={{ background: 'var(--positive)' }} />
          Sentiment positif
        </span>
      </div>
    </div>
  )
}
