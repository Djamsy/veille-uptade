'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import BmgGauge from '../../components/BmgGauge'
import { fetchAffairs, runFullCycle, type Affair } from '../../lib/api'

// ── Helpers ──────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return "à l'instant"
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)}min`
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`
  return `il y a ${Math.floor(diff / 86400)}j`
}

function themeLabel(theme: string): string {
  const map: Record<string, string> = {
    politique: 'Politique', economie: 'Économie', social: 'Social',
    environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
    education: 'Éducation', culture: 'Culture', sport: 'Sport',
    securite: 'Sécurité', infrastructure: 'Infrastructure', general: 'Général',
  }
  return map[theme] || theme
}

function themeColor(theme: string): string {
  const map: Record<string, string> = {
    politique: 'bg-purple-100 text-purple-600 border-purple-200',
    economie: 'bg-emerald-100 text-emerald-600 border-emerald-200',
    social: 'bg-blue-100 text-blue-400 border-blue-200',
    environnement: 'bg-green-100 text-green-400 border-green-200',
    sante: 'bg-rose-100 text-rose-400 border-rose-200',
    justice: 'bg-amber-100 text-amber-600 border-amber-200',
    securite: 'bg-red-100 text-red-600 border-red-200',
  }
  return map[theme] || 'bg-slate-100 text-slate-500 border-slate-200'
}

function alertBadgeClass(niveau: string): string {
  const n = niveau?.toLowerCase()
  if (n === 'critique') return 'badge-critical'
  if (n === 'élevé') return 'badge-high'
  if (n === 'modéré') return 'badge-medium'
  return 'badge-low'
}

type SortField = 'bmg' | 'gravity' | 'recent' | 'items'
type StatusFilter = 'all' | 'active' | 'stale' | 'archived'

// ════════════════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════════════════
export default function AffairsPage() {
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [sortBy, setSortBy] = useState<SortField>('bmg')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  const loadAffairs = useCallback(async () => {
    setLoading(true)
    try {
      const apiStatus = statusFilter === 'all' ? 'active' : statusFilter
      const data = await fetchAffairs(apiStatus, 50, sortBy === 'recent' ? 'last_activity' : sortBy)
      setAffairs(data.affairs || [])
      setTotal(data.total || 0)
      setError('')
    } catch (e: any) {
      setError(e.message || 'Erreur de chargement')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, sortBy])

  useEffect(() => { loadAffairs() }, [loadAffairs])

  // Local sort for client-side refinement
  const sortedAffairs = [...affairs].sort((a, b) => {
    switch (sortBy) {
      case 'bmg': return (b.bmg || 0) - (a.bmg || 0)
      case 'gravity': return (b.gravity_score || 0) - (a.gravity_score || 0)
      case 'items': return (b.item_count || 0) - (a.item_count || 0)
      case 'recent':
        return new Date(b.last_activity || b.created_at).getTime() -
               new Date(a.last_activity || a.created_at).getTime()
      default: return 0
    }
  })

  const criticalCount = affairs.filter(a => (a.bmg_details?.niveau_alerte || '').toLowerCase() === 'critique').length

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen">
        <div className="max-w-7xl mx-auto animate-fade-in">

          {/* ── Header ──────────────────────────── */}
          <div className="flex items-start justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-slate-800">Affaires</h1>
              <p className="text-sm text-slate-500 mt-0.5">
                {total} affaire{total > 1 ? 's' : ''} au total
                {criticalCount > 0 && (
                  <span className="ml-2 text-red-600">
                    — {criticalCount} critique{criticalCount > 1 ? 's' : ''}
                  </span>
                )}
              </p>
            </div>
            <button
              onClick={loadAffairs}
              className="px-3 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 text-sm hover:bg-slate-100 transition-colors"
            >
              Actualiser
            </button>
          </div>

          {/* ── Filters Bar ─────────────────────── */}
          <div className="flex flex-wrap items-center gap-3 mb-6 p-4 bg-white/60 rounded-xl border border-slate-200">
            {/* Status tabs */}
            <div className="flex bg-slate-50 rounded-lg p-0.5">
              {(['all', 'active', 'stale', 'archived'] as StatusFilter[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    statusFilter === s
                      ? 'bg-teal-600 text-slate-800'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {s === 'all' ? 'Toutes' : s === 'active' ? 'Actives' : s === 'stale' ? 'En veille' : 'Archivées'}
                </button>
              ))}
            </div>

            <div className="h-5 w-px bg-slate-100" />

            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortField)}
              className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-600 focus:outline-none focus:ring-1 focus:ring-sky-500"
            >
              <option value="bmg">Tri: BMG</option>
              <option value="gravity">Tri: Gravité</option>
              <option value="recent">Tri: Plus récent</option>
              <option value="items">Tri: Nb items</option>
            </select>

            {/* View mode */}
            <div className="ml-auto flex bg-slate-50 rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-slate-100 text-slate-800' : 'text-slate-500'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                </svg>
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'list' ? 'bg-slate-100 text-slate-800' : 'text-slate-500'}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
          </div>

          {/* ── Error ───────────────────────────── */}
          {error && (
            <div className="mb-6 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">
              {error}
            </div>
          )}

          {/* ── Loading ─────────────────────────── */}
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="bg-white rounded-xl border border-slate-200 p-5">
                  <div className="skeleton h-4 w-32 mb-3" />
                  <div className="skeleton h-16 w-full mb-3" />
                  <div className="skeleton h-3 w-24" />
                </div>
              ))}
            </div>
          ) : sortedAffairs.length === 0 ? (
            /* ── Empty state ──────────────────── */
            <div className="bg-white/60 rounded-xl border border-slate-200 p-16 text-center">
              <svg className="w-16 h-16 mx-auto text-slate-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              <p className="text-slate-500 text-sm mb-2">Aucune affaire avec ce filtre</p>
              <button
                onClick={() => setStatusFilter('all')}
                className="text-teal-600 text-sm hover:text-teal-500"
              >
                Voir toutes les affaires
              </button>
            </div>
          ) : viewMode === 'grid' ? (
            /* ── Grid View ────────────────────── */
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {sortedAffairs.map((affair) => (
                <Link key={affair._id} href={`/affairs/${affair._id}`}>
                  <div className="bg-white rounded-xl border border-slate-200 p-5 card-hover cursor-pointer h-full">
                    {/* Header with BMG */}
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-semibold text-slate-800 truncate">
                          {affair.title || affair.primary_entity || 'Affaire'}
                        </h3>
                        {affair.primary_entity && affair.title !== affair.primary_entity && (
                          <p className="text-xs text-slate-500 truncate mt-0.5">{affair.primary_entity}</p>
                        )}
                      </div>
                      <BmgGauge value={(affair.bmg || 0) * 100} size={60} />
                    </div>

                    {/* Description snippet */}
                    {affair.description && (
                      <p className="text-xs text-slate-500 line-clamp-2 mb-3">{affair.description}</p>
                    )}

                    {/* Tags */}
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      <span className={`badge border ${themeColor(affair.theme)}`}>
                        {themeLabel(affair.theme)}
                      </span>
                      {affair.bmg_details?.niveau_alerte && (
                        <span className={`badge ${alertBadgeClass(affair.bmg_details.niveau_alerte)}`}>
                          {affair.bmg_details.niveau_alerte}
                        </span>
                      )}
                      <span className={`badge ${
                        affair.status === 'active' ? 'bg-emerald-100 text-emerald-600 border border-emerald-200'
                        : affair.status === 'stale' ? 'bg-slate-100 text-slate-500 border border-slate-200'
                        : 'bg-slate-100 text-slate-500 border border-slate-200'
                      }`}>
                        {affair.status}
                      </span>
                    </div>

                    {/* Entities */}
                    {affair.entities && affair.entities.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-3">
                        {affair.entities.slice(0, 3).map((e, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                            {e}
                          </span>
                        ))}
                        {affair.entities.length > 3 && (
                          <span className="text-[10px] text-slate-500">+{affair.entities.length - 3}</span>
                        )}
                      </div>
                    )}

                    {/* Footer */}
                    <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-200">
                      <div className="flex items-center gap-3">
                        <span>{affair.item_count || 0} items</span>
                        <span>{affair.source_types?.length || 0} canaux</span>
                      </div>
                      <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            /* ── List View ────────────────────── */
            <div className="space-y-2">
              {sortedAffairs.map((affair) => (
                <Link key={affair._id} href={`/affairs/${affair._id}`}>
                  <div className="flex items-center gap-4 p-4 bg-white rounded-xl border border-slate-200 hover:bg-white/80 transition-colors cursor-pointer">
                    {/* BMG mini */}
                    <BmgGauge value={affair.bmg || 0} size={48} />

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-semibold text-slate-800 truncate">
                          {affair.title || affair.primary_entity || 'Affaire'}
                        </h3>
                        <span className={`badge border ${themeColor(affair.theme)}`}>
                          {themeLabel(affair.theme)}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500">
                        <span>{affair.item_count || 0} items</span>
                        <span>{affair.source_types?.length || 0} canaux</span>
                        <span>Gravité {Math.round((affair.gravity_score || 0) * 100)}%</span>
                        <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
                      </div>
                    </div>

                    {/* Entities */}
                    <div className="hidden lg:flex flex-wrap gap-1 max-w-[200px]">
                      {(affair.entities || []).slice(0, 3).map((e, i) => (
                        <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 truncate max-w-[100px]">
                          {e}
                        </span>
                      ))}
                    </div>

                    {/* Status */}
                    {affair.bmg_details?.niveau_alerte && (
                      <span className={`badge ${alertBadgeClass(affair.bmg_details.niveau_alerte)} flex-shrink-0`}>
                        {affair.bmg_details.niveau_alerte}
                      </span>
                    )}

                    <svg className="w-4 h-4 text-slate-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
