'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../../components/Sidebar'
import BmgGauge from '../../components/BmgGauge'
import { fetchAffairs, type Affair } from '../../lib/api'

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

function themeStyle(theme: string): { bg: string; color: string; border: string } {
  const map: Record<string, { bg: string; color: string; border: string }> = {
    politique: { bg: 'rgba(168,85,247,0.12)', color: '#c084fc', border: 'rgba(168,85,247,0.25)' },
    economie: { bg: 'rgba(16,185,129,0.12)', color: '#34d399', border: 'rgba(16,185,129,0.25)' },
    social: { bg: 'rgba(96,165,250,0.12)', color: '#93c5fd', border: 'rgba(96,165,250,0.25)' },
    environnement: { bg: 'rgba(74,222,128,0.12)', color: '#86efac', border: 'rgba(74,222,128,0.25)' },
    sante: { bg: 'rgba(251,113,133,0.12)', color: '#fda4af', border: 'rgba(251,113,133,0.25)' },
    justice: { bg: 'rgba(251,191,36,0.12)', color: '#fde68a', border: 'rgba(251,191,36,0.25)' },
    securite: { bg: 'rgba(248,113,113,0.12)', color: '#fca5a5', border: 'rgba(248,113,113,0.25)' },
  }
  return map[theme] || { bg: 'rgba(148,163,184,0.12)', color: '#cbd5e1', border: 'rgba(148,163,184,0.25)' }
}

function alertBadgeStyle(niveau: string): { bg: string; color: string; border: string } {
  const n = niveau?.toLowerCase()
  if (n === 'critique') return { bg: 'rgba(239,68,68,0.12)', color: '#f87171', border: 'rgba(239,68,68,0.25)' }
  if (n === 'élevé') return { bg: 'rgba(249,115,22,0.12)', color: '#fb923c', border: 'rgba(249,115,22,0.25)' }
  if (n === 'modéré') return { bg: 'rgba(245,158,11,0.12)', color: '#fbbf24', border: 'rgba(245,158,11,0.25)' }
  return { bg: 'rgba(16,185,129,0.12)', color: '#34d399', border: 'rgba(16,185,129,0.25)' }
}

type Priority = 'hot' | 'watch' | 'minor'

const PRIORITY_CONFIG: Record<Priority, { label: string; icon: string; color: string; glow: string; bg: string; border: string }> = {
  hot: {
    label: 'Urgentes',
    icon: '●',
    color: '#f87171',
    glow: 'rgba(239,68,68,0.25)',
    bg: 'rgba(239,68,68,0.05)',
    border: 'rgba(239,68,68,0.12)',
  },
  watch: {
    label: 'À surveiller',
    icon: '●',
    color: '#fbbf24',
    glow: 'rgba(251,191,36,0.2)',
    bg: 'rgba(251,191,36,0.04)',
    border: 'rgba(251,191,36,0.10)',
  },
  minor: {
    label: 'Mineures',
    icon: '●',
    color: '#34d399',
    glow: 'rgba(16,185,129,0.2)',
    bg: 'rgba(16,185,129,0.04)',
    border: 'rgba(16,185,129,0.10)',
  },
}

function getAffairPriority(a: Affair): Priority {
  if (a.priority === 'hot' || a.priority === 'watch' || a.priority === 'minor') return a.priority
  const g = a.gravity_score || 0
  const bmg = a.bmg || 0
  const items = a.item_count || 1
  if (g >= 0.75) return 'hot'
  if (bmg >= 0.65 && items >= 2) return 'hot'
  if (g >= 0.55) return 'watch'
  if (bmg >= 0.35 && items >= 2) return 'watch'
  return 'minor'
}

type SortField = 'bmg' | 'gravity' | 'recent' | 'items'
type StatusFilter = 'all' | 'active' | 'stale' | 'archived'

export default function AffairsPage() {
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [sortBy, setSortBy] = useState<SortField>('bmg')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [minorExpanded, setMinorExpanded] = useState(false)

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
    } finally { setLoading(false) }
  }, [statusFilter, sortBy])

  useEffect(() => { loadAffairs() }, [loadAffairs])

  const sortedAffairs = [...affairs].sort((a, b) => {
    switch (sortBy) {
      case 'bmg': return (b.bmg || 0) - (a.bmg || 0)
      case 'gravity': return (b.gravity_score || 0) - (a.gravity_score || 0)
      case 'items': return (b.item_count || 0) - (a.item_count || 0)
      case 'recent':
        return new Date(b.last_activity || b.created_at).getTime() - new Date(a.last_activity || a.created_at).getTime()
      default: return 0
    }
  })

  const grouped: Record<Priority, Affair[]> = { hot: [], watch: [], minor: [] }
  sortedAffairs.forEach(a => {
    const p = getAffairPriority(a)
    grouped[p].push(a)
  })

  const hotCount = grouped.hot.length
  const watchCount = grouped.watch.length
  const minorCount = grouped.minor.length

  const renderGridCard = (affair: Affair) => {
    const ts = themeStyle(affair.theme)
    const as_ = affair.bmg_details?.niveau_alerte ? alertBadgeStyle(affair.bmg_details.niveau_alerte) : null
    const priority = getAffairPriority(affair)
    const pc = PRIORITY_CONFIG[priority]
    return (
      <Link key={affair._id} href={`/affairs/${affair._id}`}>
        <div className="glass-card p-5 cursor-pointer h-full group" style={{
          borderLeft: `2px solid ${pc.color}`,
        }}>
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold text-white truncate group-hover:text-white/95">{affair.title || affair.primary_entity || 'Affaire'}</h3>
              {affair.primary_entity && affair.title !== affair.primary_entity && (
                <p className="text-xs truncate mt-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>{affair.primary_entity}</p>
              )}
            </div>
            <BmgGauge value={(affair.bmg || 0) * 100} size={60} />
          </div>
          {affair.description && <p className="text-xs line-clamp-2 mb-3" style={{ color: 'rgba(255,255,255,0.35)' }}>{affair.description}</p>}
          <div className="flex flex-wrap gap-1.5 mb-3">
            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: ts.bg, color: ts.color, border: `1px solid ${ts.border}` }}>{themeLabel(affair.theme)}</span>
            {as_ && <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: as_.bg, color: as_.color, border: `1px solid ${as_.border}` }}>{affair.bmg_details!.niveau_alerte}</span>}
            <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
              background: affair.status === 'active' ? 'rgba(16,185,129,0.08)' : 'rgba(255,255,255,0.03)',
              color: affair.status === 'active' ? '#34d399' : 'rgba(255,255,255,0.25)',
              border: `1px solid ${affair.status === 'active' ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.06)'}`,
            }}>{affair.status}</span>
          </div>
          {affair.entities && affair.entities.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-3">
              {affair.entities.slice(0, 3).map((e, i) => (
                <span key={i} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.03)', color: 'rgba(255,255,255,0.3)' }}>{e}</span>
              ))}
              {affair.entities.length > 3 && <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>+{affair.entities.length - 3}</span>}
            </div>
          )}
          {affair.sentiment && affair.sentiment !== 'neutre' && (
            <div className="mb-2">
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{
                background: affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif') || affair.sentiment === 'critique'
                  ? 'rgba(248,113,113,0.1)' : affair.sentiment.includes('positif') ? 'rgba(110,231,183,0.1)' : 'rgba(251,191,36,0.1)',
                color: affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif') || affair.sentiment === 'critique'
                  ? '#fca5a5' : affair.sentiment.includes('positif') ? '#6ee7b7' : '#fde68a',
                border: `1px solid ${affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif') || affair.sentiment === 'critique'
                  ? 'rgba(248,113,113,0.15)' : affair.sentiment.includes('positif') ? 'rgba(110,231,183,0.15)' : 'rgba(251,191,36,0.15)'}`,
              }}>
                {affair.sentiment}
              </span>
            </div>
          )}
          <div className="flex items-center justify-between text-xs pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.04)', color: 'rgba(255,255,255,0.25)' }}>
            <div className="flex items-center gap-3">
              <span>{affair.item_count || 0} items</span>
              <span>{affair.bmg_details?.active_canals || (new Set(affair.source_types || []).size) || 1} canaux</span>
              <span>{new Set(affair.sources || []).size || 1} sources</span>
            </div>
            <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
          </div>
        </div>
      </Link>
    )
  }

  const renderListRow = (affair: Affair) => {
    const ts = themeStyle(affair.theme)
    const as_ = affair.bmg_details?.niveau_alerte ? alertBadgeStyle(affair.bmg_details.niveau_alerte) : null
    const priority = getAffairPriority(affair)
    const pc = PRIORITY_CONFIG[priority]
    return (
      <Link key={affair._id} href={`/affairs/${affair._id}`}>
        <div className="flex items-center gap-4 p-4 glass-card cursor-pointer group" style={{ borderLeft: `2px solid ${pc.color}` }}>
          <BmgGauge value={(affair.bmg || 0) * 100} size={48} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="text-sm font-semibold text-white truncate group-hover:text-white/95">{affair.title || affair.primary_entity || 'Affaire'}</h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: ts.bg, color: ts.color, border: `1px solid ${ts.border}` }}>{themeLabel(affair.theme)}</span>
            </div>
            <div className="flex items-center gap-3 text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
              <span>{affair.item_count || 0} items</span>
              <span>{affair.bmg_details?.active_canals || (new Set(affair.source_types || []).size) || 1} canaux</span>
              <span>{new Set(affair.sources || []).size || 1} sources</span>
              <span>Gravité {Math.round((affair.gravity_score || 0) * 100)}%</span>
              {affair.sentiment && affair.sentiment !== 'neutre' && (
                <span style={{
                  color: affair.sentiment.includes('négatif') || affair.sentiment.includes('negatif') || affair.sentiment === 'critique'
                    ? '#f87171'
                    : affair.sentiment.includes('positif') ? '#6ee7b7' : '#fbbf24'
                }}>
                  {affair.sentiment}
                </span>
              )}
              <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
            </div>
          </div>
          {as_ && <span className="text-[10px] px-2 py-0.5 rounded-full font-medium flex-shrink-0" style={{ background: as_.bg, color: as_.color, border: `1px solid ${as_.border}` }}>{affair.bmg_details!.niveau_alerte}</span>}
          <svg className="w-4 h-4 flex-shrink-0 group-hover:translate-x-0.5 transition-transform" style={{ color: 'rgba(255,255,255,0.15)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
        </div>
      </Link>
    )
  }

  const renderSection = (priority: Priority, items: Affair[], collapsible: boolean = false) => {
    if (items.length === 0) return null
    const config = PRIORITY_CONFIG[priority]
    const isCollapsed = collapsible && !minorExpanded

    return (
      <div key={priority} className="mb-8">
        <div
          className="flex items-center gap-3 mb-4 cursor-pointer select-none group"
          onClick={() => collapsible && setMinorExpanded(!minorExpanded)}
        >
          <div className="w-2 h-2 rounded-full" style={{
            backgroundColor: config.color,
            boxShadow: `0 0 8px ${config.glow}`,
          }} />
          <h2 className="text-sm font-semibold" style={{ color: config.color }}>
            {config.label}
          </h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{
            background: config.bg,
            color: config.color,
            border: `1px solid ${config.border}`,
          }}>
            {items.length}
          </span>
          <div className="flex-1 h-px" style={{ background: `linear-gradient(90deg, ${config.border}, transparent)` }} />
          {collapsible && (
            <svg
              className="w-4 h-4 transition-transform duration-300"
              style={{
                color: config.color,
                transform: isCollapsed ? 'rotate(0deg)' : 'rotate(180deg)',
              }}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>

        {!isCollapsed && (
          viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger-fade">
              {items.map(renderGridCard)}
            </div>
          ) : (
            <div className="space-y-2 stagger-fade">
              {items.map(renderListRow)}
            </div>
          )
        )}

        {isCollapsed && (
          <div
            className="glass-card-static p-3 text-center cursor-pointer hover:bg-white/[0.03] transition-colors"
            onClick={() => setMinorExpanded(true)}
            style={{ borderColor: config.border }}
          >
            <p className="text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
              {items.length} affaire{items.length > 1 ? 's' : ''} mineure{items.length > 1 ? 's' : ''} — cliquer pour déplier
            </p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="lg:ml-60 flex-1 p-5 lg:p-8 min-h-screen">
        <div className="max-w-7xl mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
            <div>
              <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Affaires</h1>
              <p className="text-sm mt-0.5" style={{ color: 'rgba(255,255,255,0.3)' }}>
                {total} affaire{total > 1 ? 's' : ''} au total
                {hotCount > 0 && (
                  <span style={{ color: '#f87171' }}> — {hotCount} urgente{hotCount > 1 ? 's' : ''}</span>
                )}
              </p>
            </div>
            <button onClick={loadAffairs} className="btn-glass px-3 py-2 text-sm">
              <span className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                Actualiser
              </span>
            </button>
          </div>

          {/* Priority summary pills */}
          {!loading && sortedAffairs.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {(['hot', 'watch', 'minor'] as Priority[]).map(p => {
                const count = grouped[p].length
                if (count === 0) return null
                const c = PRIORITY_CONFIG[p]
                return (
                  <div key={p} className="flex items-center gap-2 px-3 py-1.5 rounded-xl" style={{
                    background: c.bg,
                    border: `1px solid ${c.border}`,
                  }}>
                    <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c.color, boxShadow: `0 0 4px ${c.glow}` }} />
                    <span className="text-xs font-medium" style={{ color: c.color }}>{count} {c.label.toLowerCase()}</span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 mb-6 glass-card-static p-3 lg:p-4">
            <div className="flex rounded-xl p-0.5" style={{ background: 'rgba(255,255,255,0.03)' }}>
              {(['all', 'active', 'stale', 'archived'] as StatusFilter[]).map((s) => (
                <button key={s} onClick={() => setStatusFilter(s)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={statusFilter === s ? { background: 'rgba(99,102,241,0.15)', color: '#818cf8' } : { color: 'rgba(255,255,255,0.3)' }}
                >
                  {s === 'all' ? 'Toutes' : s === 'active' ? 'Actives' : s === 'stale' ? 'En veille' : 'Archivées'}
                </button>
              ))}
            </div>
            <div style={{ width: '1px', height: '20px', background: 'rgba(255,255,255,0.06)' }} />
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortField)} className="input-dark px-3 py-1.5 text-xs">
              <option value="bmg">Tri: BMG</option>
              <option value="gravity">Tri: Gravité</option>
              <option value="recent">Tri: Plus récent</option>
              <option value="items">Tri: Nb items</option>
            </select>
            <div className="ml-auto flex rounded-xl p-0.5" style={{ background: 'rgba(255,255,255,0.03)' }}>
              {(['grid', 'list'] as const).map((mode) => (
                <button key={mode} onClick={() => setViewMode(mode)} className="p-1.5 rounded-lg transition-all"
                  style={viewMode === mode ? { background: 'rgba(255,255,255,0.06)', color: 'white' } : { color: 'rgba(255,255,255,0.25)' }}
                >
                  {mode === 'grid' ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
                  )}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl text-sm" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)', color: '#f87171' }}>{error}</div>
          )}

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="glass-card-static p-5"><div className="skeleton h-4 w-32 mb-3" /><div className="skeleton h-16 w-full mb-3" /><div className="skeleton h-3 w-24" /></div>
              ))}
            </div>
          ) : sortedAffairs.length === 0 ? (
            <div className="glass-card-static p-16 text-center">
              <svg className="w-14 h-14 mx-auto mb-4" style={{ color: 'rgba(255,255,255,0.1)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              <p className="text-sm" style={{ color: 'rgba(255,255,255,0.3)' }}>Aucune affaire avec ce filtre</p>
              <button onClick={() => setStatusFilter('all')} className="text-sm mt-2 font-medium hover:underline" style={{ color: '#818cf8' }}>Voir toutes les affaires</button>
            </div>
          ) : (
            <div>
              {renderSection('hot', grouped.hot)}
              {renderSection('watch', grouped.watch)}
              {renderSection('minor', grouped.minor, true)}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
