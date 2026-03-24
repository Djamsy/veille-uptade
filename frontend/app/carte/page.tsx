'use client';

import React, { useState, useEffect, useMemo } from 'react';
import GuadeloupeMap from '../../components/GuadeloupeMap';
import { fetchMapData, type MapResponse, type MapCommuneData } from '../../lib/api';

/* ════════════════════════════════════════════════
   PAGE CARTE INTERACTIVE — Veille Média Guadeloupe
   Style « Google Earth » : carte centrale + widgets flottants
   ════════════════════════════════════════════════ */

const THEME_COLORS: Record<string, string> = {
  securite_justice: '#ef4444',
  politique: '#8b5cf6',
  economie: '#f59e0b',
  sante_social: '#10b981',
  education: '#3b82f6',
  eau_env: '#06b6d4',
  transport: '#f97316',
  culture: '#ec4899',
  general: '#6b7280',
};

const THEME_LABELS: Record<string, string> = {
  securite_justice: 'Sécurité / Justice',
  politique: 'Politique',
  economie: 'Économie',
  sante_social: 'Santé / Social',
  education: 'Éducation',
  eau_env: 'Eau / Environnement',
  transport: 'Transport',
  culture: 'Culture',
  general: 'Général',
};

const PRIORITY_BADGE: Record<string, { color: string; label: string }> = {
  hot: { color: '#ef4444', label: 'HOT' },
  watch: { color: '#f59e0b', label: 'WATCH' },
  minor: { color: '#6b7280', label: 'MINOR' },
};

export default function CartePage() {
  const [mapData, setMapData] = useState<MapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchMapData(days)
      .then(setMapData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days]);

  // Transformer les données pour GuadeloupeMap
  const communeMapData = useMemo(() => {
    if (!mapData) return {};
    const result: Record<string, { count: number; maxGravity: number }> = {};
    for (const [name, data] of Object.entries(mapData.communes)) {
      result[name] = {
        count: data.stats.total_items,
        maxGravity: data.stats.max_gravity,
      };
    }
    return result;
  }, [mapData]);

  const selectedData: MapCommuneData | null = useMemo(() => {
    if (!selectedCommune || !mapData) return null;
    return mapData.communes[selectedCommune] || null;
  }, [selectedCommune, mapData]);

  // Stats globales
  const globalStats = useMemo(() => {
    if (!mapData) return { communes: 0, articles: 0, transcriptions: 0, affairs: 0 };
    let articles = 0, transcriptions = 0, affairs = 0;
    for (const data of Object.values(mapData.communes)) {
      articles += data.stats.article_count;
      transcriptions += data.stats.transcription_count;
      affairs += data.stats.affair_count;
    }
    return {
      communes: mapData.total_communes_active,
      articles,
      transcriptions,
      affairs,
    };
  }, [mapData]);

  // Top communes par activité
  const topCommunes = useMemo(() => {
    if (!mapData) return [];
    return Object.entries(mapData.communes)
      .map(([name, data]) => ({ name, ...data.stats }))
      .sort((a, b) => b.total_items - a.total_items)
      .slice(0, 8);
  }, [mapData]);

  return (
    <main className="min-h-screen p-3 md:p-6 max-w-[1800px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-white flex items-center gap-2">
            <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            Carte Média Guadeloupe
          </h1>
          <p className="text-xs text-white/40 mt-0.5">
            {mapData?.total_communes_active || 0} communes actives · {days} derniers jours
          </p>
        </div>
        {/* Period selector */}
        <div className="flex gap-1">
          {[3, 7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => { setDays(d); setSelectedCommune(null); }}
              className={`px-3 py-1.5 text-xs rounded-lg transition-all ${
                days === d
                  ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/40'
                  : 'bg-white/5 text-white/50 border border-white/10 hover:bg-white/10'
              }`}
            >
              {d}j
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-center">
            <div className="w-12 h-12 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-white/40 text-sm">Chargement de la carte...</p>
          </div>
        </div>
      ) : error ? (
        <div className="card-rose p-6 rounded-2xl text-center">
          <p className="text-red-300">Erreur : {error}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* ═══ LEFT PANEL — Stats globales + Top communes ═══ */}
          <div className="lg:col-span-3 space-y-3">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 gap-2">
              <div className="card-blue p-3 rounded-xl">
                <div className="text-2xl font-bold text-blue-300">{globalStats.communes}</div>
                <div className="text-[10px] text-white/40 uppercase tracking-wider">Communes</div>
              </div>
              <div className="card-amber p-3 rounded-xl">
                <div className="text-2xl font-bold text-amber-300">{globalStats.articles}</div>
                <div className="text-[10px] text-white/40 uppercase tracking-wider">Articles</div>
              </div>
              <div className="card-cyan p-3 rounded-xl">
                <div className="text-2xl font-bold text-cyan-300">{globalStats.transcriptions}</div>
                <div className="text-[10px] text-white/40 uppercase tracking-wider">Radios</div>
              </div>
              <div className="card-violet p-3 rounded-xl">
                <div className="text-2xl font-bold text-violet-300">{globalStats.affairs}</div>
                <div className="text-[10px] text-white/40 uppercase tracking-wider">Affaires</div>
              </div>
            </div>

            {/* Top communes */}
            <div className="glass-card-static p-3 rounded-xl">
              <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wider mb-2">
                Top communes
              </h3>
              <div className="space-y-1.5">
                {topCommunes.map((c, i) => (
                  <button
                    key={c.name}
                    onClick={() => setSelectedCommune(c.name)}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-all ${
                      selectedCommune === c.name
                        ? 'bg-indigo-500/20 border border-indigo-500/30'
                        : 'hover:bg-white/5 border border-transparent'
                    }`}
                  >
                    <span className="text-xs font-mono text-white/30 w-4">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-white/80 truncate">{c.name}</div>
                      <div className="text-[10px] text-white/30">
                        {c.article_count} art · {c.transcription_count} radio · {c.affair_count} aff
                      </div>
                    </div>
                    <div
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{
                        background:
                          c.max_gravity >= 0.7 ? '#ef4444' :
                          c.max_gravity >= 0.5 ? '#f97316' :
                          c.max_gravity >= 0.3 ? '#eab308' : '#10b981',
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ═══ CENTER — Carte SVG ═══ */}
          <div className="lg:col-span-5">
            <div
              className="rounded-2xl overflow-hidden"
              style={{
                background: 'linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(7,11,20,0.95) 100%)',
                border: '1px solid rgba(99,102,241,0.12)',
              }}
            >
              <GuadeloupeMap
                communeData={communeMapData}
                onCommuneClick={(name) => setSelectedCommune(name)}
              />
            </div>
            {/* Instruction */}
            <p className="text-center text-[10px] text-white/25 mt-2">
              Cliquez sur une commune pour voir le détail des contenus médiatiques
            </p>
          </div>

          {/* ═══ RIGHT PANEL — Détail commune sélectionnée ═══ */}
          <div className="lg:col-span-4 space-y-3">
            {selectedData && selectedCommune ? (
              <>
                {/* Header commune */}
                <div className="card-blue p-4 rounded-xl">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-bold text-white">{selectedCommune}</h2>
                      <p className="text-xs text-blue-300/60">
                        {selectedData.stats.total_items} contenus · {days} derniers jours
                      </p>
                    </div>
                    <button
                      onClick={() => setSelectedCommune(null)}
                      className="text-white/30 hover:text-white/60 transition-colors"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  {/* Mini stats */}
                  <div className="flex gap-3 mt-3">
                    <div className="text-center">
                      <div className="text-sm font-bold text-amber-300">{selectedData.stats.article_count}</div>
                      <div className="text-[9px] text-white/30">Articles</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm font-bold text-cyan-300">{selectedData.stats.transcription_count}</div>
                      <div className="text-[9px] text-white/30">Radios</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm font-bold text-violet-300">{selectedData.stats.affair_count}</div>
                      <div className="text-[9px] text-white/30">Affaires</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm font-bold" style={{
                        color: selectedData.stats.max_gravity >= 0.7 ? '#ef4444' :
                               selectedData.stats.max_gravity >= 0.5 ? '#f97316' : '#10b981'
                      }}>
                        {Math.round(selectedData.stats.max_gravity * 100)}%
                      </div>
                      <div className="text-[9px] text-white/30">Gravité max</div>
                    </div>
                  </div>
                </div>

                {/* Affaires dans la commune */}
                {selectedData.affairs.length > 0 && (
                  <div className="glass-card-static p-3 rounded-xl">
                    <h3 className="text-xs font-semibold text-violet-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                      </svg>
                      Affaires ({selectedData.affairs.length})
                    </h3>
                    <div className="space-y-2">
                      {selectedData.affairs.map((aff, i) => {
                        const badge = PRIORITY_BADGE[aff.priority || 'minor'];
                        return (
                          <a
                            key={aff.id || i}
                            href={`/affairs/${aff.id}`}
                            className="block p-2 rounded-lg hover:bg-white/5 transition-colors border border-white/5"
                          >
                            <div className="flex items-start gap-2">
                              <span
                                className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase flex-shrink-0 mt-0.5"
                                style={{
                                  background: `${badge.color}22`,
                                  color: badge.color,
                                  border: `1px solid ${badge.color}44`,
                                }}
                              >
                                {badge.label}
                              </span>
                              <div className="min-w-0">
                                <div className="text-xs text-white/80 font-medium leading-tight">{aff.title}</div>
                                <div className="text-[10px] text-white/30 mt-0.5">
                                  {aff.items} items · BMG {typeof aff.bmg === 'number' ? Math.round(aff.bmg < 2 ? aff.bmg * 100 : aff.bmg) : '?'}
                                </div>
                              </div>
                            </div>
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Articles */}
                {selectedData.articles.length > 0 && (
                  <div className="glass-card-static p-3 rounded-xl max-h-[300px] overflow-y-auto">
                    <h3 className="text-xs font-semibold text-amber-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2" />
                      </svg>
                      Articles ({selectedData.articles.length})
                    </h3>
                    <div className="space-y-1.5">
                      {selectedData.articles.slice(0, 15).map((art, i) => (
                        <div key={art.id || i} className="flex items-start gap-2 py-1 border-b border-white/5 last:border-0">
                          <div
                            className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                            style={{ background: THEME_COLORS[art.theme || 'general'] || '#6b7280' }}
                          />
                          <div className="min-w-0 flex-1">
                            <div className="text-[11px] text-white/70 leading-tight">{art.title}</div>
                            <div className="text-[9px] text-white/25 mt-0.5">
                              {art.source} · {THEME_LABELS[art.theme || 'general'] || art.theme}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Transcriptions radio */}
                {selectedData.transcriptions.length > 0 && (
                  <div className="glass-card-static p-3 rounded-xl max-h-[200px] overflow-y-auto">
                    <h3 className="text-xs font-semibold text-cyan-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424" />
                      </svg>
                      Radio ({selectedData.transcriptions.length})
                    </h3>
                    <div className="space-y-1.5">
                      {selectedData.transcriptions.slice(0, 10).map((t, i) => (
                        <div key={i} className="py-1 border-b border-white/5 last:border-0">
                          <div className="text-[11px] text-white/70 leading-tight">{t.title}</div>
                          <div className="text-[9px] text-white/25 mt-0.5">{t.station}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* Empty state */
              <div className="flex items-center justify-center h-full min-h-[300px]">
                <div className="text-center">
                  <svg className="w-16 h-16 mx-auto mb-3 text-white/10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                  </svg>
                  <p className="text-sm text-white/30">Sélectionnez une commune</p>
                  <p className="text-[10px] text-white/15 mt-1">sur la carte ou dans la liste</p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
