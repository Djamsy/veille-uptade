'use client'

/**
 * Carte de présence d'élus — Admin only.
 *
 * UI minimale V1 (avant refonte de la carte du dashboard public) :
 * - Sélecteur de période (7j / 30j / 6m / 12m / all)
 * - Sélecteur d'entité (40 élus V1)
 * - Liste agrégée par commune (count, dernière présence, top entités)
 * - Vue détail entité (communes + types de présence)
 * - Bouton backfill manuel
 *
 * NB : la carte choropleth Mapbox sera branchée dans une V1.1 — pour le moment
 * on affiche une grille triable, suffisante pour valider le pipeline.
 */

import { useEffect, useMemo, useState } from 'react'
import PresenceMap from '@/components/PresenceMap'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

type Period = '7' | '30' | '180' | '365' | 'all'
type EventKind = 'presence' | 'reaction' | 'all'

interface CommuneRow {
  commune: string
  count: number
  last_seen: string | null
  top_entities: { entity: string; count: number }[]
}

interface CommunesResponse {
  period_days: number | null
  entity_filter: string | null
  communes: CommuneRow[]
  total_presences: number
  active_communes: number
}

interface EntityListResponse {
  entities: string[]
  count: number
}

interface EntitySummary {
  entity: string
  total_presences: number
  communes: {
    commune: string
    count: number
    last_seen: string | null
    presence_types: string[]
  }[]
}

function authHeaders(): HeadersInit {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function adminGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

async function adminPost<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, { method: 'POST', headers: authHeaders() })
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

function fmtDate(s: string | null): string {
  if (!s) return '—'
  try {
    return new Date(s).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' })
  } catch {
    return s
  }
}

export default function PresencePage() {
  const [period, setPeriod] = useState<Period>('30')
  const [eventKind, setEventKind] = useState<EventKind>('presence')
  const [entityFilter, setEntityFilter] = useState<string>('')
  const [entities, setEntities] = useState<string[]>([])
  const [communes, setCommunes] = useState<CommuneRow[]>([])
  const [totals, setTotals] = useState<{ total: number; active: number }>({ total: 0, active: 0 })
  const [entityDetail, setEntityDetail] = useState<EntitySummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [backfilling, setBackfilling] = useState(false)
  const [message, setMessage] = useState<string>('')
  const [error, setError] = useState<string>('')

  const periodDays = useMemo(() => (period === 'all' ? null : Number(period)), [period])

  // Charger la liste d'élus une seule fois
  useEffect(() => {
    adminGet<EntityListResponse>('/api/presence/entities')
      .then(d => setEntities(d.entities))
      .catch(e => setError(`Liste élus indisponible : ${e.message}`))
  }, [])

  // Recharger à chaque changement de période, entité ou type d'événement
  useEffect(() => {
    setLoading(true)
    setError('')
    const qs = new URLSearchParams()
    if (periodDays != null) qs.set('period_days', String(periodDays))
    if (entityFilter) qs.set('entity', entityFilter)
    qs.set('event_kind', eventKind)
    const url = `/api/presence/communes?${qs}`

    adminGet<CommunesResponse>(url)
      .then(d => {
        setCommunes(d.communes)
        setTotals({ total: d.total_presences, active: d.active_communes })
      })
      .catch(e => setError(`Chargement communes : ${e.message}`))
      .finally(() => setLoading(false))
  }, [periodDays, entityFilter, eventKind])

  // Détail entité
  useEffect(() => {
    if (!entityFilter) {
      setEntityDetail(null)
      return
    }
    const qs = new URLSearchParams({ event_kind: eventKind })
    if (periodDays != null) qs.set('period_days', String(periodDays))
    adminGet<EntitySummary>(`/api/presence/entity/${encodeURIComponent(entityFilter)}?${qs}`)
      .then(setEntityDetail)
      .catch(() => setEntityDetail(null))
  }, [entityFilter, periodDays, eventKind])

  async function handleBackfill() {
    setBackfilling(true)
    setMessage('')
    setError('')
    try {
      const r = await adminPost<any>('/api/presence/backfill?days=30&limit=500')
      setMessage(
        `Backfill OK — ${r.processed} articles traités, ${r.inserted} présences ajoutées, ${r.skipped_no_match} hors scope, ${r.errors} erreurs.`
      )
      // Recharger
      const qs = new URLSearchParams()
      if (periodDays != null) qs.set('period_days', String(periodDays))
      const d = await adminGet<CommunesResponse>(`/api/presence/communes${qs.toString() ? '?' + qs : ''}`)
      setCommunes(d.communes)
      setTotals({ total: d.total_presences, active: d.active_communes })
    } catch (e: any) {
      setError(`Backfill : ${e.message}`)
    } finally {
      setBackfilling(false)
    }
  }

  const sortedCommunes = useMemo(
    () => [...communes].sort((a, b) => b.count - a.count),
    [communes]
  )

  return (
    <div className="min-h-screen p-6" style={{ background: 'var(--bg-base)', color: 'var(--text)' }}>
      <div className="max-w-6xl mx-auto">
        <header className="mb-6 flex items-center justify-between pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
              Système / Carte de présence
            </div>
            <h1 className="font-serif text-3xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
              Carte de présence
            </h1>
            <p className="text-sm mt-2" style={{ color: 'var(--text-secondary)' }}>
              Présence politique/professionnelle d&apos;élus dans la presse de Guadeloupe.
              Visibilité réservée aux administrateurs.
            </p>
          </div>
          <button
            onClick={handleBackfill}
            disabled={backfilling}
            className="px-3 py-1.5 text-xs font-semibold rounded-sm transition-colors disabled:opacity-50"
            style={{ background: 'var(--accent-press)', color: '#fafafa', border: '1px solid var(--accent-press)' }}
          >
            {backfilling ? 'Backfill en cours…' : 'Lancer un backfill (30 j)'}
          </button>
        </header>

        {error && <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-700 text-red-300 text-sm">{error}</div>}
        {message && <div className="mb-4 p-3 rounded bg-emerald-900/30 border border-emerald-700 text-emerald-300 text-sm">{message}</div>}

        {/* Filtres */}
        <div className="mb-6 flex flex-wrap gap-3 items-center">
          <label className="text-sm text-gray-400">Période :</label>
          {(['7', '30', '180', '365', 'all'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 rounded text-sm border ${
                period === p
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-gray-900 border-gray-700 text-gray-300 hover:border-gray-500'
              }`}
            >
              {p === 'all' ? 'Tout' : p === '7' ? '7 j' : p === '30' ? '30 j' : p === '180' ? '6 mois' : '12 mois'}
            </button>
          ))}

          <label className="text-sm text-gray-400 ml-4">Type :</label>
          {([
            { v: 'presence' as EventKind, label: 'Présences', tip: 'L\'élu était physiquement sur place' },
            { v: 'reaction' as EventKind, label: 'Réactions', tip: 'L\'élu commente/réagit depuis ailleurs' },
            { v: 'all' as EventKind, label: 'Les deux', tip: 'Présences + réactions' },
          ]).map(k => (
            <button
              key={k.v}
              onClick={() => setEventKind(k.v)}
              title={k.tip}
              className={`px-3 py-1.5 rounded text-sm border ${
                eventKind === k.v
                  ? 'bg-emerald-600 border-emerald-500 text-white'
                  : 'bg-gray-900 border-gray-700 text-gray-300 hover:border-gray-500'
              }`}
            >
              {k.label}
            </button>
          ))}

          <label className="text-sm text-gray-400 ml-4">Élu :</label>
          <select
            value={entityFilter}
            onChange={e => setEntityFilter(e.target.value)}
            className="px-3 py-1.5 rounded bg-gray-900 border border-gray-700 text-gray-200 text-sm"
          >
            <option value="">— Tous —</option>
            {entities.map(e => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-xs text-gray-400">Présences cumulées</div>
            <div className="text-2xl font-bold mt-1">{totals.total}</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-xs text-gray-400">Communes actives</div>
            <div className="text-2xl font-bold mt-1">{totals.active} / 32</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="text-xs text-gray-400">Élus suivis (V1)</div>
            <div className="text-2xl font-bold mt-1">{entities.length}</div>
          </div>
        </div>

        {/* Carte choropleth */}
        <div className="mb-6 bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">
            Carte de présence — densité par commune
            {entityFilter && <span className="text-blue-400"> · {entityFilter}</span>}
          </h2>
          <PresenceMap
            data={Object.fromEntries(
              communes.map(c => [
                c.commune,
                {
                  count: c.count,
                  topEntities: c.top_entities,
                  lastSeen: c.last_seen,
                },
              ])
            )}
            onCommuneClick={(name) => {
              // Sélectionne la commune cliquée comme filtre rapide (pas encore implémenté)
              // pour l'instant on copie juste son nom dans le presse-papier
              try { navigator.clipboard.writeText(name) } catch {}
            }}
          />
        </div>

        {/* Détail entité (si filtré) */}
        {entityDetail && (
          <div className="mb-6 bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-lg font-semibold mb-3">{entityDetail.entity}</h2>
            <p className="text-sm text-gray-400 mb-3">
              {entityDetail.total_presences} présences cumulées sur la période.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {entityDetail.communes.map(c => (
                <div key={c.commune} className="bg-gray-950 border border-gray-800 rounded p-3">
                  <div className="font-medium">{c.commune}</div>
                  <div className="text-sm text-gray-400">{c.count} présence{c.count > 1 ? 's' : ''}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    {c.presence_types.join(' · ') || '—'}
                  </div>
                  <div className="text-xs text-gray-500">Dernière : {fmtDate(c.last_seen)}</div>
                </div>
              ))}
              {entityDetail.communes.length === 0 && (
                <div className="text-sm text-gray-500 col-span-3">Aucune présence enregistrée sur la période.</div>
              )}
            </div>
          </div>
        )}

        {/* Table communes */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-950 text-gray-400">
              <tr>
                <th className="text-left p-3">Commune</th>
                <th className="text-right p-3">Présences</th>
                <th className="text-left p-3">Dernière</th>
                <th className="text-left p-3">Top élus</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={4} className="p-4 text-center text-gray-500">Chargement…</td></tr>
              )}
              {!loading && sortedCommunes.map(c => (
                <tr key={c.commune} className="border-t border-gray-800 hover:bg-gray-850/50">
                  <td className="p-3 font-medium">{c.commune}</td>
                  <td className="p-3 text-right">
                    <span className={c.count > 0 ? 'text-emerald-400' : 'text-gray-600'}>
                      {c.count}
                    </span>
                  </td>
                  <td className="p-3 text-gray-400">{fmtDate(c.last_seen)}</td>
                  <td className="p-3 text-gray-400">
                    {c.top_entities.length > 0
                      ? c.top_entities.map(e => `${e.entity} (${e.count})`).join(' · ')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <footer className="mt-6 text-xs text-gray-500">
          V1 admin · 40 élus suivis · Présence politique/professionnelle uniquement · Pas de vie privée.
        </footer>
      </div>
    </div>
  )
}
