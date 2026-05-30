'use client'

import { useState, useEffect, useMemo } from 'react'
import Sidebar from '../../components/Sidebar'
import { MapboxFullMap } from '../_components/dashboard/MapboxFullMap'
import { fetchMapData, type MapResponse } from '../../lib/api'

function getGravityColor(g: number): string {
  if (g >= 0.7) return 'var(--negative)'
  if (g >= 0.5) return 'var(--warning)'
  if (g >= 0.3) return 'var(--caution)'
  return 'var(--positive)'
}

export default function CartePage() {
  const [mapData, setMapData] = useState<MapResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(7)
  const [error, setError] = useState<string | null>(null)
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchMapData(days)
      .then(setMapData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Erreur'))
      .finally(() => setLoading(false))
  }, [days])

  const communeMap = useMemo(() => {
    if (!mapData?.communes) return {}
    return mapData.communes
  }, [mapData])

  const topCommunes = useMemo(() => {
    if (!mapData?.communes) return []
    return Object.entries(mapData.communes)
      .map(([name, data]) => ({
        name,
        article_count: data.stats?.article_count || 0,
        transcription_count: data.stats?.transcription_count || 0,
        affair_count: data.stats?.affair_count || 0,
        max_gravity: data.stats?.max_gravity || 0,
        total_items: data.stats?.total_items || 0,
      }))
      .sort((a, b) => b.total_items - a.total_items)
      .slice(0, 8)
  }, [mapData])

  const selectedData = selectedCommune ? communeMap[selectedCommune] : null

  const globalStats = useMemo(() => {
    if (!mapData?.communes) return { communes: 0, articles: 0, transcriptions: 0, affairs: 0 }
    const list = Object.values(mapData.communes)
    return {
      communes: list.filter(c => (c.stats?.total_items || 0) > 0).length,
      articles: list.reduce((s, c) => s + (c.stats?.article_count || 0), 0),
      transcriptions: list.reduce((s, c) => s + (c.stats?.transcription_count || 0), 0),
      affairs: list.reduce((s, c) => s + (c.stats?.affair_count || 0), 0),
    }
  }, [mapData])

  // Cast for MapboxFullMap (relaxed shape)
  const mapForBackend = mapData?.communes as unknown as Record<string, { stats: { total_items: number; max_gravity: number; article_count?: number; transcription_count?: number; affair_count?: number }; affairs?: unknown[] }>

  return (
    <div className="flex min-h-screen" style={{ background: 'var(--bg-base)' }}>
      <Sidebar />
      <main className="lg:ml-16 flex-1 overflow-y-auto">
        <header className="px-6 lg:px-8 pt-5 pb-5" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: 'var(--text-muted)' }}>
                Terrain / Carte
              </div>
              <h1 className="font-serif text-3xl lg:text-4xl font-medium tracking-tight italic" style={{ color: 'var(--text)' }}>
                Carte des événements
              </h1>
              <p className="font-mono text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
                <span style={{ color: 'var(--text)' }}>{globalStats.communes}</span> communes actives sur{' '}
                <span style={{ color: 'var(--text)' }}>{days}</span> jours
              </p>
            </div>
            <div className="inline-flex" style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
              {[3, 7, 14, 30].map((d, i) => (
                <button
                  key={d}
                  onClick={() => { setDays(d); setSelectedCommune(null) }}
                  className="px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: days === d ? 'var(--bg-hover)' : 'var(--bg-surface)',
                    color: days === d ? 'var(--text)' : 'var(--text-muted)',
                    borderLeft: i > 0 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  {d}j
                </button>
              ))}
            </div>
          </div>
        </header>

        <div className="px-6 lg:px-8 py-6 max-w-[1700px] mx-auto space-y-5">
          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Kpi label="Communes actives" value={globalStats.communes} />
            <Kpi label="Articles" value={globalStats.articles} />
            <Kpi label="Captures radio" value={globalStats.transcriptions} />
            <Kpi label="Affaires" value={globalStats.affairs} />
          </div>

          {error && (
            <div
              className="px-4 py-3 text-xs"
              style={{ background: 'var(--crit-soft)', color: '#b02939', border: '1px solid #f5d4d9', borderRadius: 'var(--radius-sm)' }}
            >
              {error}
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
            {/* Map panel */}
            <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                  Concentration géographique · {days}j
                </span>
                {selectedCommune && (
                  <button
                    onClick={() => setSelectedCommune(null)}
                    className="font-mono text-[10px] hover:underline"
                    style={{ color: 'var(--accent-link)' }}
                  >
                    Vue globale
                  </button>
                )}
              </div>
              <div className="relative" style={{ height: 600 }}>
                <MapboxFullMap communes={mapForBackend} onSelectCommune={setSelectedCommune} />
              </div>
            </div>

            {/* Side rail */}
            <aside className="flex flex-col gap-4 min-w-0">
              {/* Top communes */}
              <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                <div className="px-3.5 py-3" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                    Top communes
                  </span>
                </div>
                <div className="px-2 py-2">
                  {loading ? (
                    <p className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>Chargement…</p>
                  ) : topCommunes.length === 0 ? (
                    <p className="text-xs text-center py-4" style={{ color: 'var(--text-muted)' }}>Aucune donnée</p>
                  ) : (
                    topCommunes.map((c, i) => (
                      <button
                        key={c.name}
                        onClick={() => setSelectedCommune(c.name)}
                        className="w-full flex items-center gap-2 px-2 py-2 rounded-sm text-left transition-colors"
                        style={{
                          background: selectedCommune === c.name ? 'var(--bg-hover)' : 'transparent',
                        }}
                      >
                        <span className="font-mono text-[10px] w-4 text-center" style={{ color: 'var(--text-muted)' }}>
                          {String(i + 1).padStart(2, '0')}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium truncate" style={{ color: 'var(--text)' }}>{c.name}</div>
                          <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                            {c.article_count} art · {c.transcription_count} radio · {c.affair_count} aff
                          </div>
                        </div>
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: getGravityColor(c.max_gravity) }} />
                      </button>
                    ))
                  )}
                </div>
              </div>

              {/* Selected commune detail */}
              {selectedData && selectedCommune && (
                <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <div
                    className="px-4 py-3.5"
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      borderLeft: `3px solid ${getGravityColor(selectedData.stats.max_gravity)}`,
                    }}
                  >
                    <div className="font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-muted)' }}>
                      Commune
                    </div>
                    <h3 className="font-serif text-xl font-semibold tracking-tight" style={{ color: 'var(--text)' }}>
                      {selectedCommune}
                    </h3>
                    <div className="grid grid-cols-3 gap-3 mt-3">
                      {[
                        { v: selectedData.stats.article_count, l: 'Articles' },
                        { v: selectedData.stats.transcription_count, l: 'Radios' },
                        { v: selectedData.stats.affair_count, l: 'Affaires' },
                      ].map(s => (
                        <div key={s.l}>
                          <div className="font-serif text-xl font-semibold tabular-nums leading-none" style={{ color: 'var(--text)' }}>
                            {s.v ?? 0}
                          </div>
                          <div className="font-mono text-[9px] uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--text-muted)' }}>
                            {s.l}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedData.affairs && selectedData.affairs.length > 0 && (
                    <div className="px-2 py-2">
                      <div className="font-mono text-[10px] uppercase tracking-[0.12em] px-2 pb-2" style={{ color: 'var(--text-muted)' }}>
                        Affaires principales
                      </div>
                      {(selectedData.affairs as Array<{ title: string; theme?: string; gravity_score?: number }>).slice(0, 5).map((a, i) => {
                        const g = Math.round((a.gravity_score || 0) * 100)
                        return (
                          <div
                            key={`${a.title}-${i}`}
                            className="flex items-start gap-2 px-2 py-2"
                            style={{ borderBottom: i < Math.min(4, selectedData.affairs!.length - 1) ? '1px solid var(--border-subtle)' : 'none' }}
                          >
                            <span
                              className="font-serif text-sm font-semibold tabular-nums w-8 text-center shrink-0"
                              style={{ color: getGravityColor(g / 100) }}
                            >
                              {g}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs font-medium leading-snug" style={{ color: 'var(--text)' }}>{a.title}</div>
                              <div className="font-mono text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>{a.theme || 'general'}</div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </aside>
          </div>
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="p-4"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--text-muted)' }}>
        {label}
      </div>
      <span className="font-serif text-3xl font-semibold tabular-nums" style={{ color: 'var(--text)' }}>{value}</span>
    </div>
  )
}
