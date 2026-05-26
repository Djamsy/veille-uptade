'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import Link from 'next/link'
import { fetchAffairsByInstitution, type Affair } from '../../../lib/api'
import { MOCK_AFFAIRS } from './mocks'

type Institution = 'departement' | 'region'

const INSTITUTION_META: Record<Institution, { label: string; href: string }> = {
  departement: { label: 'Conseil départemental', href: '/departement' },
  region: { label: 'Conseil régional', href: '/region' },
}

// ── Helpers (données réelles, pas de proxy) ─────────────────
function timeAgo(dateStr?: string): string {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 60) return `il y a ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `il y a ${h} h`
  return `il y a ${Math.floor(h / 24)} j`
}

function gravityColor(g: number): string {
  if (g >= 0.75) return 'var(--negative)'
  if (g >= 0.55) return 'var(--warning)'
  if (g >= 0.4) return 'var(--caution)'
  return 'var(--positive)'
}

function gravityLabel(g: number): string {
  if (g >= 0.75) return 'Critique'
  if (g >= 0.55) return 'Élevé'
  if (g >= 0.4) return 'À suivre'
  return 'Calme'
}

function isNegative(s?: string): boolean {
  return !!s && /neg|négat|negative/i.test(s)
}

// Entités citées par une affaire (entités + élus + institutions + entité principale)
function affairEntities(a: Affair): string[] {
  return Array.from(new Set([
    ...(a.entities || []),
    ...(a.elected || []),
    ...(a.institutions || []),
    ...(a.primary_entity ? [a.primary_entity] : []),
  ].filter(Boolean)))
}

// ── Verdict climat — calculé sur du signal RÉEL ─────────────
function climatVerdict(avgBmg: number): { text: string; color: string } {
  if (avgBmg >= 0.6) return { text: 'Climat tendu', color: 'var(--negative)' }
  if (avgBmg >= 0.4) return { text: 'Climat sous surveillance', color: 'var(--warning)' }
  if (avgBmg >= 0.2) return { text: 'Climat actif', color: 'var(--caution)' }
  return { text: 'Climat apaisé', color: 'var(--positive)' }
}

type Props = {
  avgBmg: number // 0..1 — avg_bmg réel du dashboard
  trendPct?: number // variation volume articles / 7j (étiqueté honnêtement)
  sentimentDist: Record<string, number>
  isMock?: boolean
}

export function CollectiviteHero({ avgBmg, trendPct, sentimentDist, isMock }: Props) {
  const [institution, setInstitution] = useState<Institution>('departement')
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [totalMatched, setTotalMatched] = useState(0)
  const [maxGravity, setMaxGravity] = useState(0)
  const [loading, setLoading] = useState(true)
  const [errored, setErrored] = useState(false)
  const [isMockData, setIsMockData] = useState(false)
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null)

  // Restaure le choix de collectivité
  useEffect(() => {
    const saved = localStorage.getItem('ma_collectivite')
    if (saved === 'region' || saved === 'departement') setInstitution(saved)
  }, [])

  const pick = (v: Institution) => {
    setInstitution(v)
    localStorage.setItem('ma_collectivite', v)
  }

  const load = useCallback(async () => {
    setLoading(true)
    setErrored(false)
    setIsMockData(false)
    setSelectedEntity(null)
    try {
      const res = await fetchAffairsByInstitution(institution)
      const all = Object.values(res.groups || {}).flatMap(g => g.affairs || [])
      all.sort((a, b) => new Date(b.last_activity || b.created_at).getTime() - new Date(a.last_activity || a.created_at).getTime())
      const maxG = Object.values(res.groups || {}).reduce((m, g) => Math.max(m, g.max_gravity || 0), 0)
      setAffairs(all)
      setTotalMatched(res.total_matched ?? all.length)
      setMaxGravity(maxG)
    } catch {
      // Fallback démo (pas de backend dispo) — cohérent avec les autres widgets
      const mock = MOCK_AFFAIRS
      setAffairs(mock)
      setTotalMatched(mock.length)
      setMaxGravity(mock.reduce((m, a) => Math.max(m, a.gravity_score || 0), 0))
      setIsMockData(true)
    } finally {
      setLoading(false)
    }
  }, [institution])

  useEffect(() => { load() }, [load])

  const meta = INSTITUTION_META[institution]
  const verdict = climatVerdict(avgBmg)
  const bmg100 = Math.round(avgBmg * 100)

  // Entités citées (top 6 par fréquence) → chips de filtre
  const entityCounts = useMemo(() => {
    const m = new Map<string, number>()
    affairs.forEach(a => affairEntities(a).forEach(e => m.set(e, (m.get(e) || 0) + 1)))
    return [...m.entries()].sort((x, y) => y[1] - x[1]).slice(0, 6)
  }, [affairs])

  // Filtrage par entité sélectionnée
  const filteredAffairs = selectedEntity
    ? affairs.filter(a => affairEntities(a).includes(selectedEntity))
    : affairs
  const displayCount = selectedEntity ? filteredAffairs.length : totalMatched
  const negCount = filteredAffairs.filter(a => isNegative(a.sentiment)).length
  const filteredMaxG = filteredAffairs.reduce((mx, a) => Math.max(mx, a.gravity_score || 0), 0)
  const effMaxG = selectedEntity ? filteredMaxG : maxGravity

  // Répartition sentiment (réelle) pour la barre
  const sTotal = Object.values(sentimentDist).reduce((s, n) => s + (n || 0), 0) || 1
  const sNeg = Object.entries(sentimentDist).filter(([k]) => isNegative(k)).reduce((s, [, n]) => s + (n || 0), 0)
  const sPos = Object.entries(sentimentDist).filter(([k]) => /pos/i.test(k)).reduce((s, [, n]) => s + (n || 0), 0)
  const sNeu = Math.max(0, sTotal - sNeg - sPos)
  const pct = (n: number) => Math.round((n / sTotal) * 100)

  return (
    <section className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-5 reveal reveal-2">
      {/* ════ ON PARLE DE VOUS — bloc prioritaire ════ */}
      <article
        className="flex flex-col p-5 backdrop-blur-md elev-card"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderLeft: `3px solid ${gravityColor(effMaxG)}`, borderRadius: 'var(--radius)' }}
      >
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: 'var(--text-muted)' }}>
              On parle de vous
            </span>
            {isMockData && (
              <span
                className="font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm shrink-0"
                style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
              >
                Aperçu
              </span>
            )}
          </div>
          {/* Switch collectivité — les deux tuyaux existent */}
          <div className="flex items-center gap-1 p-0.5 rounded-sm" style={{ background: 'var(--bg-elevated)' }}>
            {(['departement', 'region'] as Institution[]).map(v => (
              <button
                key={v}
                onClick={() => pick(v)}
                className="font-mono text-[10px] uppercase tracking-[0.1em] px-2 py-1 rounded-sm transition-colors"
                style={{
                  background: institution === v ? 'var(--bg-surface)' : 'transparent',
                  color: institution === v ? 'var(--text)' : 'var(--text-muted)',
                  border: institution === v ? '1px solid var(--border)' : '1px solid transparent',
                }}
              >
                {v === 'departement' ? 'Dépt' : 'Région'}
              </button>
            ))}
          </div>
        </div>

        <div className="font-serif text-base italic mb-3" style={{ color: 'var(--text-secondary)' }}>
          {meta.label}
        </div>

        {loading ? (
          <div className="flex items-baseline gap-3">
            <div className="skeleton" style={{ width: 80, height: 48 }} />
          </div>
        ) : errored ? (
          <p className="font-mono text-xs py-4" style={{ color: 'var(--text-muted)' }}>
            Données indisponibles (accès requis).
          </p>
        ) : (
          <>
            <div className="flex items-end gap-3 flex-wrap">
              <span className="font-serif text-5xl lg:text-6xl font-semibold tabular-data leading-none" style={{ color: gravityColor(effMaxG) }}>
                {displayCount}
              </span>
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] pb-1.5" style={{ color: 'var(--text-muted)' }}>
                {selectedEntity ? <>affaires citant<br />cette entité</> : <>affaires vous<br />concernant</>}
              </span>
              <span
                className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] px-2 py-1 rounded-sm self-end"
                style={{ background: 'var(--bg-elevated)', color: gravityColor(effMaxG), border: `1px solid var(--border)` }}
              >
                Gravité max · {gravityLabel(effMaxG)}
              </span>
            </div>

            {negCount > 0 && (
              <p className="font-mono text-[11px] mt-2.5" style={{ color: 'var(--negative)' }}>
                dont {negCount} à tonalité négative
              </p>
            )}

            {/* Filtre par entité (élus, institutions, personnalités citées) */}
            {entityCounts.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-4">
                <span className="font-mono text-[9px] uppercase tracking-[0.14em] mr-0.5 shrink-0" style={{ color: 'var(--text-muted)' }}>
                  Entité
                </span>
                <button
                  onClick={() => setSelectedEntity(null)}
                  className="font-mono text-[10px] px-2 py-0.5 rounded-sm transition-colors cursor-pointer"
                  style={{
                    background: !selectedEntity ? 'var(--accent-press)' : 'var(--bg-elevated)',
                    color: !selectedEntity ? 'var(--on-accent)' : 'var(--text-secondary)',
                    border: '1px solid var(--border)',
                  }}
                >
                  Toutes
                </button>
                {entityCounts.map(([e, n]) => {
                  const active = selectedEntity === e
                  return (
                    <button
                      key={e}
                      onClick={() => setSelectedEntity(s => (s === e ? null : e))}
                      title={`${e} — ${n} affaire(s)`}
                      className="font-mono text-[10px] px-2 py-0.5 rounded-sm transition-colors truncate max-w-[150px] cursor-pointer"
                      style={{
                        background: active ? 'var(--accent-press)' : 'var(--bg-elevated)',
                        color: active ? 'var(--on-accent)' : 'var(--text-secondary)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      {e} · {n}
                    </button>
                  )
                })}
              </div>
            )}

            {/* Dernières citations (filtrées) */}
            <div className="mt-4 pt-4 space-y-2.5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              {filteredAffairs.slice(0, 3).map(a => (
                <Link key={a._id} href={`/affairs/${a._id}`} className="flex gap-2.5 group">
                  <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: gravityColor(a.gravity_score) }} />
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm leading-snug truncate group-hover:underline" style={{ color: 'var(--text)' }}>
                      {a.title}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--text-muted)' }}>
                      {a.theme} · {timeAgo(a.last_activity || a.created_at)}
                    </span>
                  </span>
                </Link>
              ))}
              {filteredAffairs.length === 0 && (
                <p className="font-serif text-sm italic py-1" style={{ color: 'var(--text-secondary)' }}>
                  {selectedEntity ? 'Aucune affaire pour cette entité.' : 'Aucune affaire ne mentionne votre collectivité sur la période.'}
                </p>
              )}
            </div>

            <Link
              href={meta.href}
              className="mt-4 self-start font-mono text-[11px] uppercase tracking-[0.1em] hover:underline"
              style={{ color: 'var(--accent-link)' }}
            >
              Voir tout →
            </Link>
          </>
        )}
      </article>

      {/* ════ CLIMAT MÉDIA — verdict honnête ════ */}
      <article
        className="relative flex flex-col p-5 backdrop-blur-md elev-card"
        style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
      >
        {isMock && (
          <span
            className="absolute top-3 right-3 font-mono text-[9px] uppercase tracking-[0.12em] px-1 py-0.5 rounded-sm"
            style={{ background: 'var(--warn-soft)', color: '#9d551f', border: '1px solid #f3dcc5' }}
          >
            Aperçu
          </span>
        )}
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] mb-4" style={{ color: 'var(--text-muted)' }}>
          Climat média · 971 · 7 jours
        </span>

        <h2 className="font-serif text-2xl lg:text-3xl italic font-medium leading-tight" style={{ color: verdict.color }}>
          {verdict.text}
        </h2>

        <div className="flex items-baseline gap-2.5 mt-3">
          <span className="font-serif text-4xl font-semibold tabular-data leading-none" style={{ color: 'var(--text)' }}>
            {bmg100}
          </span>
          <span className="font-mono text-[11px] uppercase tracking-[0.12em]" style={{ color: 'var(--text-muted)' }}>
            BMG moyen
          </span>
          {trendPct != null && trendPct !== 0 && (
            <span className="font-mono text-xs ml-auto" style={{ color: trendPct > 0 ? 'var(--warning)' : 'var(--positive)' }}>
              {trendPct > 0 ? '↗ +' : '↘ '}{trendPct}% vol.
            </span>
          )}
        </div>

        {/* Répartition sentiment — barre 3 segments (données réelles) */}
        <div className="mt-5">
          <div className="flex h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--bg-elevated)' }}>
            {sNeg > 0 && <div style={{ width: `${pct(sNeg)}%`, background: 'var(--negative)' }} />}
            {sNeu > 0 && <div style={{ width: `${pct(sNeu)}%`, background: 'var(--neutral)' }} />}
            {sPos > 0 && <div style={{ width: `${pct(sPos)}%`, background: 'var(--positive)' }} />}
          </div>
          <div className="flex justify-between mt-2 font-mono text-[10px] uppercase tracking-[0.1em]" style={{ color: 'var(--text-muted)' }}>
            <span style={{ color: 'var(--negative)' }}>Négatif {pct(sNeg)}%</span>
            <span>Neutre {pct(sNeu)}%</span>
            <span style={{ color: 'var(--positive)' }}>Positif {pct(sPos)}%</span>
          </div>
        </div>

        <Link
          href="/analytics"
          className="mt-auto pt-4 self-start font-mono text-[11px] uppercase tracking-[0.1em] hover:underline"
          style={{ color: 'var(--accent-link)' }}
        >
          Analyse détaillée →
        </Link>
      </article>
    </section>
  )
}
