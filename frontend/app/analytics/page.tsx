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
        <main className="ml-64 flex-1 p-8 min-h-screen">
          <div className="max-w-6xl mx-auto">
            <div className="skeleton h-8 w-40 mb-8" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
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
      <main className="ml-64 flex-1 p-8 min-h-screen">
        <div className="max-w-6xl mx-auto animate-fade-in">

          {/* ── Header ─────────────────────────── */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-white">Analytics & Système</h1>
              <p className="text-sm text-slate-400 mt-0.5">État du pipeline, réconciliation et santé système</p>
            </div>
            <button
              onClick={loadData}
              className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-sm hover:bg-slate-700 transition-colors"
            >
              Rafraîchir
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* ── Pipeline Affaires ────────────── */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Pipeline Affaires</h2>
                <div className={`w-2 h-2 rounded-full ${health?.status === 'healthy' ? 'bg-emerald-500' : 'bg-red-500'}`} />
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Statut</span>
                  <span className={`text-xs font-medium ${health?.status === 'healthy' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {health?.status || 'inconnu'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Candidats total</span>
                  <span className="text-xs text-white font-medium">{health?.candidates_total ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Non classés</span>
                  <span className="text-xs text-amber-400 font-medium">{health?.candidates_unclustered ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Clusters actifs</span>
                  <span className="text-xs text-purple-400 font-medium">{health?.clusters_active ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Affaires actives</span>
                  <span className="text-xs text-sky-400 font-medium">{health?.affairs_active ?? '—'}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Affaires en veille</span>
                  <span className="text-xs text-slate-500 font-medium">{health?.affairs_stale ?? '—'}</span>
                </div>
              </div>

              <button
                onClick={() => handleAction('cycle', () => runFullCycle())}
                disabled={actionLoading === 'cycle'}
                className="mt-4 w-full px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
              >
                {actionLoading === 'cycle' ? 'Cycle en cours...' : 'Lancer le cycle complet'}
              </button>
            </div>

            {/* ── Réconciliation ───────────────── */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Réconciliation</h2>
                <div className={`w-2 h-2 rounded-full ${reconHealth ? 'bg-emerald-500' : 'bg-slate-600'}`} />
              </div>

              {reconHealth ? (
                <div className="space-y-3">
                  {Object.entries(reconHealth).slice(0, 8).map(([key, val]) => (
                    <div key={key} className="flex justify-between items-center">
                      <span className="text-xs text-slate-400">{key.replace(/_/g, ' ')}</span>
                      <span className="text-xs text-white font-medium">
                        {typeof val === 'object' ? JSON.stringify(val).slice(0, 30) : String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-600">Service non disponible</p>
              )}

              <button
                onClick={() => handleAction('recon', () => runReconciliation(3, false))}
                disabled={actionLoading === 'recon'}
                className="mt-4 w-full px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
              >
                {actionLoading === 'recon' ? 'Réconciliation...' : 'Réconcilier (3 jours)'}
              </button>
            </div>

            {/* ── Index Articles ───────────────── */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">Index Articles</h2>

              {indexStatus ? (
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">Articles indexés</span>
                    <span className="text-xs text-white font-medium">{indexStatus.index_size ?? '—'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">Âge de l'index</span>
                    <span className="text-xs text-slate-300">
                      {indexStatus.index_age_minutes ? `${indexStatus.index_age_minutes} min` : '—'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">Entités uniques</span>
                    <span className="text-xs text-purple-400 font-medium">{indexStatus.unique_entities ?? '—'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-slate-400">Affaires dans l'index</span>
                    <span className="text-xs text-sky-400 font-medium">{indexStatus.affairs_in_index ?? '—'}</span>
                  </div>

                  {/* Themes distribution */}
                  {indexStatus.themes_distribution && (
                    <div className="mt-3 pt-3 border-t border-slate-700/30">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Thèmes</p>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(indexStatus.themes_distribution as Record<string, number>)
                          .sort(([, a], [, b]) => (b as number) - (a as number))
                          .slice(0, 8)
                          .map(([theme, count]) => (
                            <span key={theme} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700/30 text-slate-400">
                              {theme} ({count as number})
                            </span>
                          ))
                        }
                      </div>
                    </div>
                  )}

                  {/* Top entities */}
                  {indexStatus.entities_list && (indexStatus.entities_list as string[]).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-700/30">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">
                        Entités ({(indexStatus.entities_list as string[]).length})
                      </p>
                      <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
                        {(indexStatus.entities_list as string[]).slice(0, 20).map((e, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/40 text-slate-400">
                            {e}
                          </span>
                        ))}
                        {(indexStatus.entities_list as string[]).length > 20 && (
                          <span className="text-[10px] text-slate-600">
                            +{(indexStatus.entities_list as string[]).length - 20} de plus
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-600">Index non disponible</p>
              )}
            </div>

            {/* ── Actions rapides ──────────────── */}
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">Actions rapides</h2>
              <div className="space-y-3">
                <button
                  onClick={() => handleAction('cycle', () => runFullCycle())}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-700/30 hover:bg-slate-700/50 text-slate-300 text-sm transition-colors disabled:opacity-50 text-left"
                >
                  <div className="w-8 h-8 rounded-lg bg-sky-500/20 flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium">Cycle complet</p>
                    <p className="text-[10px] text-slate-500">Clustering + Promotion + BMG + Lifecycle</p>
                  </div>
                </button>

                <button
                  onClick={() => handleAction('recon', () => runReconciliation(3, false))}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-700/30 hover:bg-slate-700/50 text-slate-300 text-sm transition-colors disabled:opacity-50 text-left"
                >
                  <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium">Réconciliation transcriptions</p>
                    <p className="text-[10px] text-slate-500">Corriger les noms via articles de référence</p>
                  </div>
                </button>

                <button
                  onClick={() => handleAction('recon_dry', () => runReconciliation(3, true))}
                  disabled={!!actionLoading}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-lg bg-slate-700/30 hover:bg-slate-700/50 text-slate-300 text-sm transition-colors disabled:opacity-50 text-left"
                >
                  <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center flex-shrink-0">
                    <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-xs font-medium">Réconciliation (dry run)</p>
                    <p className="text-[10px] text-slate-500">Simulation sans écriture en base</p>
                  </div>
                </button>
              </div>

              {actionLoading && (
                <div className="mt-4 flex items-center gap-2 text-xs text-sky-400">
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
