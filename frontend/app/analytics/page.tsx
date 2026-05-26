'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchAffairSystemHealth,
  fetchReconciliationHealth,
  fetchArticleIndex,
  fetchEnrichedDashboard,
  fetchPredictiveAnalysis,
  runReconciliation,
  runFullCycle,
  type SystemStats,
  type EnrichedDashboardData,
  type PredictiveAnalysis,
  type PredictiveItem,
} from '../../lib/api'

function pct(num: number, denom: number): number {
  if (!denom) return 0
  return Math.round((num / denom) * 100)
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] px-1.5 py-0.5 rounded-sm"
      style={{
        background: ok ? 'var(--ok-soft)' : 'var(--crit-soft)',
        color: ok ? '#3d6f44' : '#b02939',
        border: `1px solid ${ok ? '#cce5d0' : '#f5d4d9'}`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: ok ? 'var(--positive)' : 'var(--negative)' }} />
      {label}
    </span>
  )
}

export default function AnalyticsPage() {
  const [health, setHealth] = useState<SystemStats | null>(null)
  const [reconHealth, setReconHealth] = useState<Record<string, unknown> | null>(null)
  const [indexStatus, setIndexStatus] = useState<Record<string, unknown> | null>(null)
  const [dashboard, setDashboard] = useState<EnrichedDashboardData | null>(null)
  const [predictive, setPredictive] = useState<PredictiveAnalysis | null>(null)
  const [predictiveLoading, setPredictiveLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [h, r, idx, dash] = await Promise.allSettled([
        fetchAffairSystemHealth(),
        fetchReconciliationHealth(),
        fetchArticleIndex(),
        fetchEnrichedDashboard(),
      ])
      if (h.status === 'fulfilled') setHealth(h.value)
      if (r.status === 'fulfilled') setReconHealth(r.value as Record<string, unknown>)
      if (idx.status === 'fulfilled') setIndexStatus(idx.value as Record<string, unknown>)
      if (dash.status === 'fulfilled') setDashboard(dash.value)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleAction = async (action: string, fn: () => Promise<unknown>) => {
    setActionLoading(action)
    try { await fn(); await loadData() }
    catch (e) { console.error(`Action ${action} failed:`, e) }
    finally { setActionLoading('') }
  }

  const loadPredictive = async () => {
    setPredictiveLoading(true)
    try { const res = await fetchPredictiveAnalysis(); setPredictive(res.analysis) }
    catch (e) { console.error(e) }
    finally { setPredictiveLoading(false) }
  }

  const coverage = dashboard?.coverage
  const trends = dashboard?.trends
  const gravDist = dashboard?.gravity_distribution
  const sentDist = dashboard?.sentiment_distribution || {}
  const priorityCounts = dashboard?.priority_counts || {}
  const avgBmg = dashboard?.avg_bmg || 0
  const avgGravity = dashboard?.avg_gravity || 0
  const topSources = dashboard?.top_sources || []
  const topEntities = dashboard?.top_entities || []

  const pipelineOk = health?.status === 'healthy' || health?.status === 'ok'
  const reconOk = Boolean(reconHealth && (reconHealth.status === 'healthy' || reconHealth.status === 'ok'))
  const indexOk = Boolean(indexStatus && indexStatus.status === 'ok')
  const dashOk = Boolean(dashboard)

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Analyse / Analytics
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Analytics
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                Performance du pipeline, qualité des données et métriques système
              </p>
            </div>
            <button
              onClick={loadData}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors hover:bg-ink-100"
              style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
            >
              <svg className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" strokeWidth={1.7} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12a9 9 0 0115.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 01-15.5 6.3L3 16M3 21v-5h5" />
              </svg>
              Actualiser
            </button>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1500px] mx-auto space-y-5">
          {/* Health row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <HealthCard label="Pipeline" pill={<StatusPill ok={pipelineOk} label={pipelineOk ? 'OK' : 'KO'} />}>
              <div className="text-xs space-y-0.5" style={{ color: 'var(--text-secondary)' }}>
                <Row label="Candidats" value={String(health?.candidates_total ?? '—')} />
                <Row label="Clusters" value={String(health?.clusters_active ?? '—')} />
                <Row label="Affaires actives" value={String(health?.affairs_active ?? '—')} />
              </div>
            </HealthCard>

            <HealthCard label="Réconciliation" pill={<StatusPill ok={reconOk} label={reconOk ? 'OK' : 'KO'} />}>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {reconHealth ? 'Service opérationnel' : 'Indisponible'}
              </p>
            </HealthCard>

            <HealthCard label="Index articles" pill={<StatusPill ok={indexOk} label={indexOk ? 'OK' : 'KO'} />}>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {indexStatus ? `${(indexStatus as Record<string, unknown>).count || '—'} entrées` : 'Indisponible'}
              </p>
            </HealthCard>

            <HealthCard label="Dashboard" pill={<StatusPill ok={dashOk} label={dashOk ? 'OK' : 'KO'} />}>
              <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                {dashOk ? `${Math.round(avgBmg * 100)} BMG moy.` : 'Indisponible'}
              </p>
            </HealthCard>
          </div>

          {/* Actions */}
          <div className="flex gap-2 flex-wrap">
            <ActionBtn
              label="Lancer un cycle complet"
              loading={actionLoading === 'cycle'}
              onClick={() => handleAction('cycle', runFullCycle)}
            />
            <ActionBtn
              label="Lancer réconciliation"
              loading={actionLoading === 'recon'}
              onClick={() => handleAction('recon', runReconciliation)}
            />
            <ActionBtn
              label="Analyse prédictive"
              loading={predictiveLoading}
              onClick={loadPredictive}
              primary
            />
          </div>

          {/* Coverage + KPI */}
          {coverage && (
            <Section label="Couverture · 7 jours">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Articles" value={coverage.total_articles_7d} />
                <Kpi label="Enrichis" value={`${pct(coverage.enriched_articles_7d, coverage.total_articles_7d)}%`} />
                <Kpi label="Affiliés" value={`${pct(coverage.affiliated_articles_7d, coverage.total_articles_7d)}%`} />
                <Kpi label="Transcriptions" value={`${pct(coverage.processed_transcriptions_7d, coverage.total_transcriptions_7d)}%`} />
              </div>
            </Section>
          )}

          {/* Gravity + Sentiment distribution */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {gravDist && (
              <Section label="Gravité (distribution)">
                <Bars items={[
                  { label: 'Faible', value: gravDist.low, color: 'var(--positive)' },
                  { label: 'Moyen', value: gravDist.medium, color: 'var(--caution)' },
                  { label: 'Élevé', value: gravDist.high, color: 'var(--warning)' },
                  { label: 'Critique', value: gravDist.critical, color: 'var(--negative)' },
                ]} />
              </Section>
            )}
            {Object.keys(sentDist).length > 0 && (
              <Section label="Sentiment (distribution)">
                <Bars items={Object.entries(sentDist).map(([k, v]) => ({
                  label: k,
                  value: v,
                  color: k.includes('négatif') ? 'var(--negative)' : k.includes('positif') ? 'var(--positive)' : k.includes('mitigé') || k.includes('mixte') ? 'var(--warning)' : 'var(--neutral)',
                }))} />
              </Section>
            )}
          </div>

          {/* Top sources + entities */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {topSources.length > 0 && (
              <Section label="Top sources">
                <div className="space-y-2">
                  {topSources.slice(0, 6).map(s => {
                    const max = topSources[0]?.count || 1
                    return (
                      <div key={s.name}>
                        <div className="flex justify-between mb-1">
                          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{s.name}</span>
                          <span className="font-mono text-xs tabular-nums" style={{ color: 'var(--text)' }}>{s.count}</span>
                        </div>
                        <div className="h-1.5 rounded-sm" style={{ background: 'var(--bg-elevated)' }}>
                          <div className="h-full rounded-sm" style={{ width: `${(s.count / max) * 100}%`, background: 'var(--accent-press)' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </Section>
            )}
            {topEntities.length > 0 && (
              <Section label="Top entités">
                <div className="space-y-1.5">
                  {topEntities.slice(0, 6).map(e => (
                    <div key={e.name} className="flex justify-between text-xs py-0.5">
                      <span style={{ color: 'var(--text)' }}>{e.name}</span>
                      <span className="font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>{e.count}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>

          {/* Trends summary */}
          {trends && (
            <Section label="Tendances">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Kpi label="Articles · sem." value={trends.articles_this_week} hint={`vs ${trends.articles_last_week}`} />
                <Kpi label="Évolution" value={`${trends.articles_trend_pct > 0 ? '+' : ''}${Math.round(trends.articles_trend_pct)}%`} severity={trends.articles_trend_pct > 0 ? 'warn' : 'ok'} />
                <Kpi label="Affaires créées" value={trends.affairs_created_this_week} hint={`vs ${trends.affairs_created_last_week}`} />
              </div>
            </Section>
          )}

          {/* Priorities */}
          {Object.keys(priorityCounts).length > 0 && (
            <Section label="Priorités">
              <div className="grid grid-cols-3 gap-3">
                <Kpi label="Hot" value={priorityCounts.hot || 0} severity="crit" />
                <Kpi label="Watch" value={priorityCounts.watch || 0} severity="warn" />
                <Kpi label="Minor" value={priorityCounts.minor || 0} severity="ok" />
              </div>
            </Section>
          )}

          {/* Predictive */}
          {predictive && (
            <Section label="Analyse prédictive">
              {predictive.synthese && (
                <p className="font-serif text-base italic leading-relaxed mb-4" style={{ color: 'var(--text-secondary)' }}>
                  {predictive.synthese}
                </p>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <PredBlock label="Tendances" items={predictive.tendances} />
                <PredBlock label="Anticipations" items={predictive.anticipations} />
                <PredBlock label="Risques" items={predictive.risques} />
                <PredBlock label="Recommandations" items={predictive.recommandations} />
              </div>
            </Section>
          )}

          <div className="font-serif text-base font-medium tabular-nums" style={{ color: 'var(--text-muted)' }}>
            Moyenne gravité : <span style={{ color: 'var(--text)' }}>{Math.round(avgGravity * 100)}</span>
          </div>
        </div>
      </main>
    </div>
  )
}

function HealthCard({ label, pill, children }: { label: string; pill: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="p-4" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>{label}</span>
        {pill}
      </div>
      {children}
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
      <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>{label}</span>
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="font-mono tabular-nums" style={{ color: 'var(--text)' }}>{value}</span>
    </div>
  )
}

function Kpi({ label, value, severity, hint }: { label: string; value: number | string; severity?: 'crit' | 'warn' | 'ok'; hint?: string }) {
  const color = severity === 'crit' ? 'var(--negative)' : severity === 'warn' ? 'var(--warning)' : severity === 'ok' ? 'var(--positive)' : 'var(--text)'
  return (
    <div className="p-3" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-1.5" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="font-serif text-2xl font-semibold tabular-nums leading-none" style={{ color }}>{value}</span>
        {hint && <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{hint}</span>}
      </div>
    </div>
  )
}

function Bars({ items }: { items: { label: string; value: number; color: string }[] }) {
  const total = items.reduce((s, x) => s + x.value, 0)
  if (total === 0) return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Pas de données</p>
  return (
    <div className="space-y-2">
      {items.map(it => {
        const p = Math.round((it.value / total) * 100)
        return (
          <div key={it.label}>
            <div className="flex justify-between mb-1">
              <span className="text-xs capitalize" style={{ color: 'var(--text-secondary)' }}>{it.label}</span>
              <span className="font-mono text-xs tabular-nums" style={{ color: 'var(--text)' }}>{it.value} <span style={{ color: 'var(--text-muted)' }}>({p}%)</span></span>
            </div>
            <div className="h-1.5 rounded-sm" style={{ background: 'var(--bg-elevated)' }}>
              <div className="h-full rounded-sm" style={{ width: `${p}%`, background: it.color }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function PredBlock({ label, items }: { label: string; items: PredictiveItem[] }) {
  if (!items?.length) return null
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            <div className="font-medium" style={{ color: 'var(--text)' }}>
              {it.titre} <span className="font-mono ml-1" style={{ color: 'var(--text-muted)' }}>{Math.round(it.confiance * 100)}%</span>
            </div>
            <p className="leading-relaxed">{it.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function ActionBtn({ label, loading, onClick, primary }: { label: string; loading: boolean; onClick: () => void; primary?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
      style={
        primary
          ? { background: 'var(--accent-press)', color: 'var(--on-accent)', border: '1px solid var(--accent-press)' }
          : { background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }
      }
    >
      {loading && (
        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      )}
      {loading ? 'En cours…' : label}
    </button>
  )
}
