// Editorial horizontal segmented sentiment bar (matches v3-check.jpg proposal):
// score serif + chip on top, segmented bar with 3 segments, neg/neu/pos labels.

type Props = {
  sentimentDist: Record<string, number>
}

function computeScore(dist: Record<string, number>): number {
  const total = Object.values(dist).reduce((s, n) => s + n, 0)
  if (total === 0) return 50
  const pos = (dist['positif'] || dist['positive'] || 0)
  const neu = (dist['neutre'] || dist['neutral'] || 0)
  const mix = (dist['mixte'] || dist['mixed'] || 0)
  const neg = (dist['négatif'] || dist['negatif'] || dist['negative'] || 0)
  return Math.round((pos * 100 + neu * 55 + mix * 50 + neg * 10) / total)
}

function chipFor(score: number): { label: string; bg: string; color: string; border: string } {
  if (score >= 70) return { label: 'Positif', bg: 'var(--ok-soft)', color: '#3d6f44', border: '#cce5d0' }
  if (score >= 50) return { label: 'Neutre', bg: 'var(--info-soft)', color: '#2f5680', border: '#d3dde9' }
  if (score >= 30) return { label: 'Mitigé', bg: 'var(--warn-soft)', color: '#9d551f', border: '#f3dcc5' }
  return { label: 'Tendu', bg: 'var(--crit-soft)', color: '#b02939', border: '#f5d4d9' }
}

export function SentimentBar({ sentimentDist }: Props) {
  const total = Object.values(sentimentDist).reduce((s, n) => s + n, 0)
  const pos = (sentimentDist['positif'] || sentimentDist['positive'] || 0)
  const neu = (sentimentDist['neutre'] || sentimentDist['neutral'] || 0)
    + (sentimentDist['mixte'] || sentimentDist['mixed'] || 0)
  const neg = (sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0)
  const score = computeScore(sentimentDist)
  const chip = chipFor(score)

  const pct = (n: number) => total === 0 ? 0 : Math.round((n / total) * 100)
  const posPct = pct(pos)
  const negPct = pct(neg)
  const neuPct = 100 - posPct - negPct

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <span className="font-serif text-3xl font-semibold tabular-nums leading-none" style={{ color: 'var(--text)' }}>
          {score}
        </span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>/ 100</span>
        <span
          className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-sm"
          style={{ background: chip.bg, color: chip.color, border: `1px solid ${chip.border}` }}
        >
          {chip.label}
        </span>
      </div>

      <div className="flex h-1.5 rounded-sm overflow-hidden" style={{ background: 'var(--bg-elevated)' }}>
        <div style={{ width: `${negPct}%`, background: 'var(--negative)' }} />
        <div style={{ width: `${neuPct}%`, background: 'var(--neutral)' }} />
        <div style={{ width: `${posPct}%`, background: 'var(--positive)' }} />
      </div>

      <div className="flex items-baseline justify-between mt-2 font-mono text-[10px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
        <span><span style={{ color: 'var(--negative)' }}>{negPct}%</span> nég.</span>
        <span><span style={{ color: 'var(--text-secondary)' }}>{neuPct}%</span> neu.</span>
        <span><span style={{ color: 'var(--positive)' }}>{posPct}%</span> pos.</span>
      </div>
    </div>
  )
}
