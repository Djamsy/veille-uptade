'use client'

import { useState, useEffect, useCallback } from 'react'
import Sidebar from '../../components/Sidebar'
import {
  fetchAffairSystemHealth,
  fetchReconciliationHealth,
  fetchArticleIndex,
  runReconciliation,
  runFullCycle,
  type SystemStats,
} from '../../lib/api'

// ════════════════════════════════════════════════════════════
// ANALYTICS PAGE — System health, reconciliation, pipeline stats
// ════════════════════════════════════════════════════════════
export default function AnalyticsPage() {
  const [health, setHealth] = useState<SystemStats | null>(null)
  const [reconHealth, setReconHealth] = useState<Record<string, any> | null>(null)
  const [indexStatus, setIndexStatus] = useState<Record<string, any> | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [h, r, idx] = await Promise.allSettled([
        fetchAffairSystemHealth(),
        fetchReconciliationHealth(),
        fetchArticleIndex(),
      ])
      if (h.status === 'fulfilled') setHealth(h.value)
      if (r.status === 'fulfilled') setReconHealth(r.value)
      if (idx.status === 'fulfilled') setIndexStatus(idx.value)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleAction = async (action: string, fn: () => Promise<any>) => {
    setActionLoading(action)
    try {
      await fn()
      await loadData()
    } catch (e) {
      console.error(`Action ${action} failed:`, e)
    } finally {
      setActionLoading('')
    }
  }

  // ── Loading ─────────────────────────────────
  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen bg-gradient-to-br from-[#06060a] to-[#0a0a0f]">
          <div className="max-w-6xl mx-auto">
            <div className="skeleton h-8 w-40 mb-8" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="glass-card-static p-6">
                  <div className="skeleton h-4 w-32 mb-4" />
                  <div className="skeleton h-24 w-full" />
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen bg-gradient-to-br from-[#06060a] to-[#0a0a0f]">
        <div className="max-w-6xl mx-auto animate-fade-in">

          {/* ── Header ─────────────────────────── */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Analytics & Système</h1>
              <p className="text-sm text-[rgba(255,255,255,0.5)] mt-0.5">État du pipeline, réconciliation et santé système</p>
            </div>
            <button
              onClick={loadData}
              className="px-3 py-2 rounded-lg glass-card-static text-[rgba(255,255,255,0.5)] text-sm hover:bg-[rgba(255,255,255,0.08)] transition-colors border border-[rgba(255,255,255,0.06)]"
            >
              Rafraîchir
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* ── Pipeline Affaires ────────────── */}
            <div className="glass-card-static p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-[rgba(255,255,255,0.5)] uppercase tracking-wider">Pipeline Affaires</h2>
                <div
                  className={`w-2 h-2 rounded-full ${health?.status === 'healthy' ? 'bg-[#10b981]' : 'bg-[#ef4444]'}`}
                  style={health?.status === 'healthy' ? { boxShadow: '0 0 6px rgba(16,185,129,0.5)' } : {}}
                />
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Statut</span>
                  <span className={`text-xs font-medium ${health?.status === 'healthy' ? 'text-[#34d399]' : 'text-[#ef4444]'}`}>
                    {health?.status || 'inconnu'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Candidats total</span>
                  <span className="text-xs text-white font-medium">{health?.candidates_total ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Non classés</span>
                  <span className="text-xs text-[#fbbf24] font-medium">{health?.candidates_unclustered ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Clusters actifs</span>
                  <span className="text-xs text-[#c084fc] font-medium">{health?.clusters_active ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Affaires actives</span>
                  <span className="text-xs text-[#34d399] font-medium">{health?.affairs_active ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-[rgba(255,255,255,0.4)]">Affaires en veille</span>
                  <span className="text-xs text-[rgba(255,255,255,0.35)] font-medium">{health?.affairs_stale ?? '—'}</span>
                </div>
              </div>

              <button
                onClick={() => handleAction('cycle', () => runFullCycle())}
                disabled={actionLoading === 'cycle'}
                className="mt-4 w-full px-3 py-2 rounded-lg text-white text-xs font-medium transition-colors disabled:opacity-50 bg-[rgba(16,185,129,0.2)] hover:bg-[rgba(16,185,129,0.3)] text-[#34d399]"
              >
                {actionLoading === 'cycle' ? 'Cycle en cours...' : 'Lancer le cycle complet'}
              </button>
            </div>

            {/* ── Réconciliation ───────────────── */}
            <div className="glass-card-static p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-[rgba(255,255,255,0.5)] uppercase tracking-wider">Réconciliation</h2>
                <div
                  className={`w-2 h-2 rounded-full ${reconHealth ? 'bg-[#10b981]' : 'bg-[rgba(255,255,255,0.25)]'}`}
                  style={reconHealth ? { boxShadow: '0 0 6px rgba(16,185,129,0.5)' } : {}}
                />
              </div>

              {reconHealth ? (
                <div className="space-y-3">
                  {Object.entries(reconHealth).slice(0, 8).map(([key, val]) => (
                    <div key={key} className="flex justify-between items-center">
                      <span className="text-xs text-[rgba(255,255,255,0.4)]">{key.replace(/_/g, ' ')}</span>
                      <span className="text-xs text-[rgba(255,255,255,0.7)] font-medium">
                        {typeof val === 'object' ? JSON.stringify(val).slice(0, 30) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[rgba(255,255,255,0.4)]">Service non disponible</p>
              )}

              <button
                onClick={() => handleAction('recon', () => runReconciliation(3, false))}
                disabled={actionLoading === 'recon'}
                className="mt-4 w-full px-3 py-2 rounded-lg text-xs font-medium transition-colors disabled:opacity-50 bg-[rgba(168,85,247,0.2)] hover:bg-[rgba(168,85,247,0.3)] text-[#c084fc]"
              >
                {actionLoading === 'recon' ? 'Réconciliation...' : 'Réconcilier (3 jours)'}
              </button>
            </div>

            {/* ── Index Articles ───────────────── */}
            <div className="glass-card-static p-6">
              <h2 className="text-sm font-semibold text-[rgba(255,255,255,0.5)] uppercase tracking-wider mb-4">Index Articles</h2>

              {indexStatus ? (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-[rgba(255,255,255,0.4)]">Articles indexés</span>
                    <span className="text-xs text-white font-medium">{indexStatus.index_size ?? '—'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-[rgba(255,255,255,0.4)]">Âge de l'index</span>
                    <span className="text-xs text-[rgba(255,255,255,0.35)]">
                      {indexStatus.index_age_minutes ? `${indexStatus.index_age_minutes} min` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-[rgba(255,255,255,0.4)]">Entités uniques</span>
                    <span className="text-xs text-[#c084fc] font-medium">{indexStatus.unique_entities ?? '—'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-[rgba(255,255,255,0.4)]">Affaires dans l'index</span>
                    <span className="text-xs text-[#34d399] font-medium">{indexStatus.affairs_in_index ?? '—'}</span>
                  </div>

                  {/* Themes distribution */}
                  {indexStatus.themes_distribution && (
                    <div className="mt-3 pt-3 border-t border-[rgba(255,255,255,0.06)]">
                      <p className="text-[10px] text-[rgba(255,255,255,0.35)] uppercase tracking-wider mb-2">Thèmes</p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(indexStatus.themes_distribution as Record<string, number>)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 8)
                          .map(([theme, count]) => (
                            <span key={theme} className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(255,255,255,0.04)] text-[rgba(255,255,255,0.35)]">
                              {theme} ({count as number})
                            </span>
                          ))
                        }
                      </div>
                    </div>
                  )}

                  {/* Top entities */}
                  {indexStatus.entities_list && (indexStatus.entities_list as string[]).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-[rgba(255,255,255,0.06)]">
                      <p className="text-[10px] text-[rgba(255,255,255,0.35)] uppercase tracking-wider mb-2">
                        Entités ({(indexStatus.entities_list as string[]).length})
                      </p>
                      <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
                        {(indexStatus.entities_list as string[]).slice(0, 20).map((e, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-[rgba(255,255,255,0.04)] text-[rgba(255,255,255,0.35)]">
                            {e}
                          </span>
                        ))}
                        {(indexStatus.entities_list as string[]).length > 20 && (
                          <span className="text-[10px] text-[rgba(255,255,255,0.35)]">
                            +{(indexStatus.entities_list as string[]).length - 20} de plus
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-[rgba(255,255,255,0.4)]">Index non disponible</p>
              )}
            </div>

            {/* ── Actions rapides ──────────────── */}
            <div className="glass-card-static p-6">
              <h2 className="text-sm font-semibold text-[rgba(255,255,255,0.5)] uppercase tracking-wider mb-4">Actions rapides</h2>
              <div className="space-y-3">
                <button
                  onClick={() => handleAction('cycle', () => runFullCycle())}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg glass-card-static hover:bg-[rgba(255,255,255,0.06)] text-white text-sm transition-colors disabled:opacity-50 text-left border border-[rgba(255,255,255,0.06)]"
                >
                  <div className="w-8 h-8 rounded-lg bg-[rgba(16,185,129,0.2)] flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-[#34d399]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-white">Cycle complet</p>
                    <p className="text-[10px] text-[rgba(255,255,255,0.35)]">Clustering + Promotion + BMG + Lifecycle</p>
                  </div>
                </button>

                <button
                  onClick={() => handleAction('recon', () => runReconciliation(3, false))}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg glass-card-static hover:bg-[rgba(255,255,255,0.06)] text-white text-sm transition-colors disabled:opacity-50 text-left border border-[rgba(255,255,255,0.06)]"
                >
                  <div className="w-8 h-8 rounded-lg bg-[rgba(168,85,247,0.2)] flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-[#c084fc]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-white">Réconciliation transcriptions</p>
                    <p className="text-[10px] text-[rgba(255,255,255,0.35)]">Corriger les noms via articles de référence</p>
                  </div>
                </button>

                <button
                  onClick={() => handleAction('recon_dry', () => runReconciliation(3, true))}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg glass-card-static hover:bg-[rgba(255,255,255,0.06)] text-white text-sm transition-colors disabled:opacity-50 text-left border border-[rgba(255,255,255,0.06)]"
                >
                  <div className="w-8 h-8 rounded-lg bg-[rgba(251,191,36,0.2)] flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-[#fbbf24]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-white">Réconciliation (dry run)</p>
                    <p className="text-[10px] text-[rgba(255,255,255,0.35)]">Simulation sans écriture en base</p>
                  </div>
                </button>
              </div>

              {actionLoading && (
                <div className="mt-4 flex items-center gap-2 text-xs text-[#34d399]">
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Action en cours...
                </div>
              )}
            </div>

          </div>
        </div>
      </main>
    </div>
  )
}
