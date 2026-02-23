'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import BmgGauge from '../components/BmgGauge'
import { fetchDashboard, fetchAffairSystemHealth, runFullCycle, type DashboardData, type SystemStats, type Affair } from '../lib/api'

// ── Helpers ──────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diff = Math.floor((now - then) / 1000)
  if (diff < 60) return 'à l\'instant'
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
    politique: 'bg-purple-100 text-purple-700 border-purple-200',
    economie: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    social: 'bg-blue-100 text-blue-700 border-blue-200',
    environnement: 'bg-green-100 text-green-700 border-green-200',
    sante: 'bg-rose-100 text-rose-700 border-rose-200',
    justice: 'bg-amber-100 text-amber-700 border-amber-200',
    securite: 'bg-red-100 text-red-700 border-red-200',
    education: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    culture: 'bg-pink-100 text-pink-700 border-pink-200',
    sport: 'bg-cyan-100 text-cyan-700 border-cyan-200',
    infrastructure: 'bg-orange-100 text-orange-700 border-orange-200',
  }
  return map[theme] || 'bg-slate-100 text-slate-600 border-slate-200'
}

function alertBadge(niveau: string) {
  const map: Record<string, string> = {
    critique: 'badge-critical', élevé: 'badge-high',
    modéré: 'badge-medium', faible: 'badge-low',
  }
  return map[niveau?.toLowerCase()] || 'badge-info'
}

// ── Skeleton ──────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="skeleton h-4 w-24 mb-3" />
      <div className="skeleton h-8 w-16 mb-2" />
      <div className="skeleton h-3 w-20" />
    </div>
  )
}

// ── Stat Card ────────────────────────────────────────────
function StatCard({ label, value, sub, color = 'text-slate-800', icon }: {
  label: string; value: string | number; sub?: string; color?: string;
  icon: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 card-hover shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wider mb-1">{label}</p>
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
          {sub && <p className="text-xs text-slate-400 mt-1">{sub}</p>}
        </div>
        <div className="p-2 bg-slate-50 rounded-lg text-slate-400">
          {icon}
        </div>
      </div>
    </div>
  )
}

// ── Affair Card ──────────────────────────────────────────
function AffairCard({ affair }: { affair: Affair }) {
  return (
    <Link href={`/affairs/${affair._id}`}>
      <div className="bg-white rounded-xl border border-slate-200 p-5 card-hover cursor-pointer shadow-sm">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-slate-800 truncate">
              {affair.title || affair.primary_entity || 'Affaire'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {affair.primary_entity && affair.title !== affair.primary_entity
                ? affair.primary_entity
                : timeAgo(affair.last_activity || affair.created_at)}
            </p>
          </div>
          <BmgGauge value={affair.bmg || 0} size={64} />
        </div>
        <div className="flex flex-wrap gap-1.5 mb-3">
          <span className={`badge border ${themeColor(affair.theme)}`}>
            {themeLabel(affair.theme)}
          </span>
          {affair.bmg_details?.niveau_alerte && (
            <span className={`badge ${alertBadge(affair.bmg_details.niveau_alerte)}`}>
              {affair.bmg_details.niveau_alerte}
            </span>
          )}
          <span className="badge bg-slate-100 text-slate-500 border border-slate-200">
            {affair.source_types?.length || 0} canaux
          </span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>{affair.item_count || 0} items</span>
          <span>{timeAgo(affair.last_activity || affair.created_at)}</span>
        </div>
      </div>
    </Link>
  )
}

// ── Alert Row ────────────────────────────────────────────
function AlertRow({ affair }: { affair: Affair }) {
  return (
    <Link href={`/affairs/${affair._id}`}>
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-red-50 border border-red-200 hover:bg-red-100 transition-colors cursor-pointer">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate">
            {affair.title || affair.primary_entity}
          </p>
          <p className="text-xs text-slate-500">
            BMG {Math.round(affair.bmg || 0)} — {themeLabel(affair.theme)}
          </p>
        </div>
        <div className="text-xs text-red-600 font-medium flex-shrink-0">
          {affair.bmg_details?.niveau_alerte || 'alerte'}
        </div>
      </div>
    </Link>
  )
}

// ════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [health, setHealth] = useState<SystemStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cycleRunning, setCycleRunning] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const loadData = useCallback(async () => {
    try {
      const [dash, hlth] = await Promise.allSettled([
        fetchDashboard(),
        fetchAffairSystemHealth(),
      ])
      if (dash.status === 'fulfilled') { setDashboard(dash.value); setError('') }
      else { setError('Impossible de charger le dashboard') }
      if (hlth.status === 'fulfilled') { setHealth(hlth.value) }
      setLastRefresh(new Date())
    } catch (e: any) {
      setError(e.message || 'Erreur de connexion')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 60_000)
    return () => clearInterval(interval)
  }, [loadData])

  const handleRunCycle = async () => {
    setCycleRunning(true)
    try { await runFullCycle(); await loadData() }
    catch (e: any) { console.error('Cycle error:', e) }
    finally { setCycleRunning(false) }
  }

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="ml-64 flex-1 p-8 min-h-screen bg-[#faf9f6]">
          <div className="max-w-7xl mx-auto">
            <div className="skeleton h-8 w-48 mb-8" />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
              {[...Array(5)].map((_, i) => <SkeletonCard key={i} />)}
            </div>
          </div>
        </main>
      </div>
    )
  }

  const topAffairs = dashboard?.top_affairs || []
  const criticals = dashboard?.critical_alerts || []
  const stats = dashboard?.stats || health

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-64 flex-1 p-8 min-h-screen bg-[#faf9f6]">
        <div className="max-w-7xl mx-auto animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-bold text-slate-800">Tableau de bord</h1>
              <p className="text-sm text-slate-500 mt-0.5">
                Dernière mise à jour : {lastRefresh.toLocaleTimeString('fr-FR')}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={loadData}
                className="px-3 py-2 rounded-lg bg-white border border-slate-200 text-slate-600 text-sm hover:bg-slate-50 transition-colors shadow-sm">
                <svg className="w-4 h-4 inline mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Rafraîchir
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning}
                className="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium transition-colors disabled:opacity-50 shadow-sm">
                {cycleRunning ? (
                  <><svg className="w-4 h-4 inline mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>Cycle en cours...</>
                ) : 'Lancer le cycle complet'}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-600 text-sm">{error}</div>
          )}

          {criticals.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <h2 className="text-sm font-semibold text-red-600 uppercase tracking-wider">
                  Alertes critiques ({criticals.length})
                </h2>
              </div>
              <div className="space-y-2">
                {criticals.slice(0, 5).map((a) => <AlertRow key={a._id} affair={a} />)}
              </div>
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
            <StatCard label="Affaires actives" value={stats?.affairs_active ?? '—'}
              sub={`${stats?.affairs_stale ?? 0} en veille`} color="text-teal-600"
              icon={<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>} />
            <StatCard label="Clusters" value={stats?.clusters_active ?? '—'}
              sub="groupes détectés" color="text-purple-600"
              icon={<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>} />
            <StatCard label="Candidats" value={stats?.candidates_total ?? '—'}
              sub={`${stats?.candidates_unclustered ?? 0} non classés`} color="text-amber-600"
              icon={<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>} />
            <StatCard label="Système" value={stats?.status === 'healthy' ? 'OK' : stats?.status ?? '—'}
              color={stats?.status === 'healthy' ? 'text-emerald-600' : 'text-red-600'}
              icon={<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>} />
            <StatCard label="Top BMG" value={topAffairs.length > 0 ? Math.round(topAffairs[0]?.bmg || 0) : '—'}
              sub={topAffairs.length > 0 ? (topAffairs[0]?.title || '').slice(0, 25) : 'Aucune affaire'}
              color={(topAffairs[0]?.bmg || 0) >= 75 ? 'text-red-600' : (topAffairs[0]?.bmg || 0) >= 50 ? 'text-orange-600' : (topAffairs[0]?.bmg || 0) >= 25 ? 'text-yellow-600' : 'text-emerald-600'}
              icon={<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>} />
          </div>

          {/* Top Affaires Grid */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-slate-800">Affaires majeures</h2>
              <Link href="/affairs" className="text-sm text-teal-600 hover:text-teal-500 transition-colors">Voir tout →</Link>
            </div>
            {topAffairs.length === 0 ? (
              <div className="bg-white/60 rounded-xl border border-slate-200 p-12 text-center shadow-sm">
                <svg className="w-12 h-12 mx-auto text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p className="text-slate-500 text-sm">Aucune affaire active pour le moment</p>
                <p className="text-slate-400 text-xs mt-1">Lancez le cycle complet pour détecter de nouvelles affaires</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {topAffairs.slice(0, 9).map((affair) => <AffairCard key={affair._id} affair={affair} />)}
              </div>
            )}
          </div>

          {/* Pipeline Status */}
          {stats && (
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wider mb-4">Pipeline</h2>
              <div className="flex items-center gap-6 overflow-x-auto">
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="w-10 h-10 rounded-full bg-amber-50 border border-amber-200 flex items-center justify-center">
                    <span className="text-sm font-bold text-amber-600">{stats.candidates_total ?? 0}</span>
                  </div>
                  <div><p className="text-xs font-medium text-slate-600">Candidats</p><p className="text-[10px] text-slate-400">Ingestion</p></div>
                </div>
                <svg className="w-5 h-5 text-slate-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="w-10 h-10 rounded-full bg-purple-50 border border-purple-200 flex items-center justify-center">
                    <span className="text-sm font-bold text-purple-600">{stats.clusters_active ?? 0}</span>
                  </div>
                  <div><p className="text-xs font-medium text-slate-600">Clusters</p><p className="text-[10px] text-slate-400">Regroupement</p></div>
                </div>
                <svg className="w-5 h-5 text-slate-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="w-10 h-10 rounded-full bg-teal-50 border border-teal-200 flex items-center justify-center">
                    <span className="text-sm font-bold text-teal-600">{stats.affairs_active ?? 0}</span>
                  </div>
                  <div><p className="text-xs font-medium text-slate-600">Affaires</p><p className="text-[10px] text-slate-400">Promues</p></div>
                </div>
                <svg className="w-5 h-5 text-slate-300 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="w-10 h-10 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center">
                    <span className="text-sm font-bold text-slate-500">{stats.affairs_stale ?? 0}</span>
                  </div>
                  <div><p className="text-xs font-medium text-slate-600">En veille</p><p className="text-[10px] text-slate-400">Archivage</p></div>
                </div>
              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  )
}
