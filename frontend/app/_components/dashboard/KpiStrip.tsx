type Kpi = {
  label: string
  value: number | string
  trend?: { delta: number; period?: string }
  severity?: 'neutral' | 'crit' | 'warn' | 'ok'
}

function trendColor(delta: number, severity?: Kpi['severity']) {
  if (severity === 'crit') return 'var(--negative)'
  if (severity === 'warn') return 'var(--warning)'
  if (severity === 'ok') return 'var(--positive)'
  // Neutral: up = warn (more = worse for most metrics), down = ok
  return delta > 0 ? 'var(--warning)' : delta < 0 ? 'var(--positive)' : 'var(--text-muted)'
}

function trendArrow(delta: number) {
  if (delta > 0) return '↗'
  if (delta < 0) return '↘'
  return '→'
}

function Cell({ kpi }: { kpi: Kpi }) {
  const isCrit = kpi.severity === 'crit'
  return (
    <div
      className="p-4 transition-colors hover:bg-ink-100"
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        borderColor: isCrit ? '#f5d4d9' : 'var(--border)',
      }}
    >
      <div
        className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2"
        style={{ color: isCrit ? 'var(--negative)' : 'var(--text-muted)' }}
      >
        {kpi.label}
      </div>
      <div className="flex items-baseline gap-2.5">
        <span
          className="font-serif text-3xl font-semibold tabular-nums leading-none"
          style={{ color: isCrit ? 'var(--negative)' : 'var(--text)' }}
        >
          {kpi.value}
        </span>
        {kpi.trend && (
          <span
            className="font-mono text-xs tabular-nums"
            style={{ color: trendColor(kpi.trend.delta, kpi.severity) }}
          >
            {trendArrow(kpi.trend.delta)} {kpi.trend.delta > 0 ? '+' : ''}{kpi.trend.delta}{kpi.trend.period ? ` ${kpi.trend.period}` : ''}
          </span>
        )}
      </div>
    </div>
  )
}

export function KpiStrip({ kpis, isMock }: { kpis: Kpi[]; isMock?: boolean }) {
  return (
    <div className="relative">
      {isMock && (
        <span
          className="absolute -top-2 right-0 font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm z-10"
          style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
        >
          Aperçu
        </span>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map(k => <Cell key={k.label} kpi={k} />)}
      </div>
    </div>
  )
}
