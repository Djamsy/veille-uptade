type Kpi = {
  label: string
  value: number | string
  trend?: { delta: number; period?: string }
  severity?: 'neutral' | 'crit' | 'warn' | 'ok'
  // Direction sémantique du delta. 'up' = monter est bon (ex: articles, captures),
  // 'down' = monter est mauvais (ex: affaires urgentes), 'either' = neutre.
  // Si absent, défaut = 'down' (alerte si ça monte).
  goodDirection?: 'up' | 'down' | 'either'
}

function trendColor(delta: number, severity?: Kpi['severity'], goodDirection: Kpi['goodDirection'] = 'down') {
  if (severity === 'crit') return 'var(--negative)'
  if (severity === 'warn') return 'var(--warning)'
  if (severity === 'ok') return 'var(--positive)'
  if (delta === 0 || goodDirection === 'either') return 'var(--text-muted)'
  const isPositiveOutcome = (delta > 0 && goodDirection === 'up') || (delta < 0 && goodDirection === 'down')
  return isPositiveOutcome ? 'var(--positive)' : 'var(--warning)'
}

function trendArrow(delta: number) {
  if (delta > 0) return '↗'
  if (delta < 0) return '↘'
  return '→'
}

function Cell({ kpi, last }: { kpi: Kpi; last?: boolean }) {
  const isCrit = kpi.severity === 'crit'
  return (
    <div
      className="flex-1 min-w-[150px] px-4 py-3 transition-colors hover:bg-ink-100"
      style={{ borderRight: last ? 'none' : '1px solid var(--border-subtle)' }}
    >
      <div
        className="font-mono text-[10px] uppercase tracking-[0.14em]"
        style={{ color: isCrit ? 'var(--negative)' : 'var(--text-muted)' }}
      >
        {kpi.label}
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span
          className="font-serif text-2xl font-semibold tabular-data leading-none"
          style={{ color: isCrit ? 'var(--negative)' : 'var(--text)' }}
        >
          {kpi.value}
        </span>
        {kpi.trend && (
          <span
            className="font-mono text-[11px] tabular-nums"
            style={{ color: trendColor(kpi.trend.delta, kpi.severity, kpi.goodDirection) }}
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
    <div
      className="relative flex flex-wrap items-stretch overflow-hidden backdrop-blur-md"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
    >
      {kpis.map((k, i) => <Cell key={k.label} kpi={k} last={i === kpis.length - 1} />)}
      {isMock && (
        <span
          className="absolute top-1.5 right-2 font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm z-10"
          style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
        >
          Aperçu
        </span>
      )}
    </div>
  )
}
