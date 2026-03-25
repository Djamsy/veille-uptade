'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import Sidebar from '../components/Sidebar'
import {
  fetchEnrichedDashboard,
  fetchAffairsByCommune,
  fetchStorageStats,
  fetchMapData,
  fetchSearch,
  runFullCycle,
  runReaffiliate,
  runScrapeNow,
  runBulkEnrich,
  fetchSummary,
  fetchRadioHealth,
  fetchRadioToday,
  triggerRadioCapture,
  type EnrichedDashboardData,
  type Affair,
  type DailyActivity,
  type TopEntity,
  type TopSource,
  type OrphanArticle,
  type TimelineEvent,
  type StorageStats,
  type MapResponse,
  type SearchResult,
  type SummaryResponse,
  type MediaSummary,
} from '../lib/api'

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || '';

// ── Coordonnées communes Guadeloupe ─────────────────
const COMMUNE_COORDS: Record<string, [number, number]> = {
  'Pointe-à-Pitre': [-61.5339, 16.2411], 'Les Abymes': [-61.5028, 16.2706],
  'Baie-Mahault': [-61.5917, 16.2678], 'Le Moule': [-61.3469, 16.3339],
  'Sainte-Anne': [-61.3833, 16.2267], 'Saint-François': [-61.2753, 16.2536],
  'Le Gosier': [-61.4936, 16.2133], 'Petit-Bourg': [-61.5897, 16.1933],
  'Capesterre-Belle-Eau': [-61.5667, 16.0500], 'Sainte-Rose': [-61.6972, 16.3339],
  'Deshaies': [-61.7917, 16.3078], 'Bouillante': [-61.7719, 16.1378],
  'Trois-Rivières': [-61.6333, 15.9750], 'Basse-Terre': [-61.7256, 15.9978],
  "Morne-à-l'Eau": [-61.4539, 16.3339], 'Port-Louis': [-61.5278, 16.4189],
  'Lamentin': [-61.6333, 16.2700], 'Goyave': [-61.5800, 16.1300],
  'Vieux-Habitants': [-61.7580, 16.0600], 'Pointe-Noire': [-61.7900, 16.2300],
  'Saint-Claude': [-61.6900, 16.0200], 'Gourbeyre': [-61.7000, 15.9800],
  'Vieux-Fort': [-61.7000, 15.9500], 'Marie-Galante': [-61.2700, 15.9400],
  'La Désirade': [-61.0500, 16.3100], 'Terre-de-Haut': [-61.5900, 15.8600],
  'Terre-de-Bas': [-61.6400, 15.8600], 'Anse-Bertrand': [-61.5000, 16.4700],
  'Petit-Canal': [-61.4900, 16.3700],
};

// ── Mapbox 3D Map (interactif, plein écran) ─────────────
function MapboxFullMap({
  communes,
  onSelectCommune,
}: {
  communes?: Record<string, { stats: { total_items: number; max_gravity: number }; affairs?: any[] }>;
  onSelectCommune?: (name: string | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState('');
  const initAttempted = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined' || initAttempted.current) return;
    initAttempted.current = true;

    // Token peut venir de l'env OU être hardcodé en fallback côté client
    const token = MAPBOX_TOKEN || (window as any).__MAPBOX_TOKEN || '';
    if (!token) {
      setMapError('Token Mapbox manquant');
      return;
    }

    const initMap = () => {
      if (!containerRef.current || mapRef.current) return;
      const mapboxgl = (window as any).mapboxgl;
      if (!mapboxgl) { setMapError('Mapbox GL non chargé'); return; }

      try {
        mapboxgl.accessToken = token;
        const map = new mapboxgl.Map({
          container: containerRef.current,
          style: 'mapbox://styles/mapbox/satellite-streets-v12',
          center: [-61.55, 16.18],
          zoom: 10.2,
          pitch: 55,
          bearing: -15,
          antialias: true,
          attributionControl: false,
          failIfMajorPerformanceCaveat: false,
        });

        map.on('load', () => {
          setReady(true);
          try {
            map.addSource('mapbox-dem', {
              type: 'raster-dem', url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
              tileSize: 512, maxzoom: 14,
            });
            map.setTerrain({ source: 'mapbox-dem', exaggeration: 1.8 });
            map.addLayer({
              id: 'sky', type: 'sky',
              paint: { 'sky-type': 'atmosphere', 'sky-atmosphere-sun': [0.0, 80.0], 'sky-atmosphere-sun-intensity': 15 },
            });
          } catch (e) { console.warn('[Map] Terrain/Sky error:', e); }
        });

        map.on('error', (e: any) => {
          console.error('[Map] Error:', e?.error?.message || e);
        });

        map.addControl(new mapboxgl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right');
        mapRef.current = map;
      } catch (e: any) {
        setMapError(e.message || 'Erreur init carte');
      }
    };

    // Charger Mapbox GL JS via CDN si pas déjà chargé
    const loadAndInit = () => {
      if ((window as any).mapboxgl) { initMap(); return; }

      // CSS
      if (!document.querySelector('link[href*="mapbox-gl"]')) {
        const css = document.createElement('link');
        css.rel = 'stylesheet';
        css.href = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css';
        document.head.appendChild(css);
      }

      // JS
      if (!document.querySelector('script[src*="mapbox-gl"]')) {
        const js = document.createElement('script');
        js.src = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.js';
        js.onload = () => { setTimeout(initMap, 100); };
        js.onerror = () => { setMapError('CDN Mapbox inaccessible'); };
        document.head.appendChild(js);
      } else {
        // Script déjà en cours de chargement, attendre
        const check = setInterval(() => {
          if ((window as any).mapboxgl) { clearInterval(check); initMap(); }
        }, 200);
        setTimeout(() => clearInterval(check), 10000);
      }
    };

    loadAndInit();
    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, []);

  // Markers communes
  useEffect(() => {
    if (!mapRef.current || !communes || !ready) return;
    const mapboxgl = (window as any).mapboxgl;
    if (!mapboxgl) return;

    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    for (const [name, cData] of Object.entries(communes)) {
      const coords = COMMUNE_COORDS[name];
      if (!coords || !cData.stats) continue;
      const g = cData.stats.max_gravity;
      const color = g >= 0.7 ? '#ef4444' : g >= 0.5 ? '#f97316' : g >= 0.3 ? '#eab308' : '#22c55e';
      const size = Math.min(44, Math.max(16, 10 + cData.stats.total_items * 2));

      const el = document.createElement('div');
      el.style.cssText = `width:${size}px;height:${size}px;cursor:pointer;background:radial-gradient(circle,${color}cc 0%,${color}44 50%,transparent 100%);border:2px solid ${color}aa;border-radius:50%;box-shadow:0 0 ${size * 1.5}px ${color}66;transition:transform 0.2s;`;
      el.title = `${name} — ${cData.stats.total_items} items`;
      el.onmouseenter = () => { el.style.transform = 'scale(1.3)'; };
      el.onmouseleave = () => { el.style.transform = 'scale(1)'; };
      el.onclick = () => {
        if (onSelectCommune) onSelectCommune(name);
        mapRef.current?.flyTo({ center: coords, zoom: 13, pitch: 60, duration: 1500 });
      };

      const marker = new mapboxgl.Marker({ element: el }).setLngLat(coords).addTo(mapRef.current);
      markersRef.current.push(marker);
    }
  }, [communes, ready, onSelectCommune]);

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" style={{ width: '100%', height: '100%' }} />
      {/* Fallback visible avant que la carte charge */}
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center"
          style={{ background: 'radial-gradient(ellipse at 50% 55%, #0c1a30 0%, #020617 70%)' }}>
          <div className="text-center">
            <div className="w-16 h-16 rounded-full border-2 border-indigo-500/30 border-t-indigo-400 animate-spin mx-auto mb-4" />
            <p className="text-sm font-medium" style={{ color: 'rgba(255,255,255,0.5)' }}>
              {mapError ? mapError : 'Chargement de la carte 3D...'}
            </p>
            {mapError && (
              <p className="text-[10px] mt-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
                Vérifiez NEXT_PUBLIC_MAPBOX_TOKEN dans Vercel
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ── Helpers ──────────────────────────────────────────────
function timeAgo(dateStr: string): string {
  if (!dateStr) return ''
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
    economie_emploi: 'Économie', eau_env: 'Environnement',
    energie_transports: 'Transports', sante_social: 'Santé',
    securite_justice: 'Justice', education: 'Éducation',
    culture_patrimoine: 'Culture', sport: 'Sport', general: 'Général',
    environnement: 'Environnement', sante: 'Santé', justice: 'Justice',
    culture: 'Culture', securite: 'Sécurité', infrastructure: 'Infra',
  }
  return map[theme] || theme
}

function themeColor(theme: string): string {
  const map: Record<string, string> = {
    politique: '#facc15', economie: '#34d399', social: '#93c5fd',
    environnement: '#86efac', sante: '#fda4af', justice: '#fde68a',
    securite: '#fca5a5', education: '#93c5fd', culture: '#f9a8d4',
    sport: '#67e8f9', infrastructure: '#fdba74', general: '#cbd5e1',
    economie_emploi: '#34d399', eau_env: '#86efac',
    energie_transports: '#fdba74', sante_social: '#fda4af',
    securite_justice: '#fde68a', culture_patrimoine: '#f9a8d4',
  }
  return map[theme] || '#cbd5e1'
}

function themeColorParts(theme: string): [string, string, string] {
  const map: Record<string, string> = {
    politique: 'rgba(22,163,74,0.12)_#facc15_rgba(22,163,74,0.25)',
    economie: 'rgba(16,185,129,0.12)_#34d399_rgba(16,185,129,0.25)',
    social: 'rgba(96,165,250,0.12)_#93c5fd_rgba(96,165,250,0.25)',
    environnement: 'rgba(74,222,128,0.12)_#86efac_rgba(74,222,128,0.25)',
    sante: 'rgba(251,113,133,0.12)_#fda4af_rgba(251,113,133,0.25)',
    justice: 'rgba(251,191,36,0.12)_#fde68a_rgba(251,191,36,0.25)',
    securite: 'rgba(248,113,113,0.12)_#fca5a5_rgba(248,113,113,0.25)',
    education: 'rgba(129,140,248,0.12)_#93c5fd_rgba(129,140,248,0.25)',
    culture: 'rgba(244,114,182,0.12)_#f9a8d4_rgba(244,114,182,0.25)',
    sport: 'rgba(34,211,238,0.12)_#67e8f9_rgba(34,211,238,0.25)',
    infrastructure: 'rgba(251,146,60,0.12)_#fdba74_rgba(251,146,60,0.25)',
  }
  const raw = map[theme] || 'rgba(148,163,184,0.12)_#cbd5e1_rgba(148,163,184,0.25)'
  return raw.split('_') as [string, string, string]
}

function ThemeBadge({ theme }: { theme: string }) {
  const [bg, color, border] = themeColorParts(theme)
  return (
    <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: bg, color, border: `1px solid ${border}` }}>
      {themeLabel(theme)}
    </span>
  )
}

function TrendArrow({ pct }: { pct: number }) {
  if (pct === 0) return <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>—</span>
  const up = pct > 0
  return (
    <span className="text-[10px] font-semibold flex items-center gap-0.5" style={{ color: up ? '#34d399' : '#f87171' }}>
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"
        style={{ transform: up ? 'rotate(0)' : 'rotate(180deg)' }}>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      </svg>
      {Math.abs(pct)}%
    </span>
  )
}

// ── Sentiment Arc Gauge ─────────────────────────────────
function SentimentGauge({ sentimentDist }: { sentimentDist: Record<string, number> }) {
  const entries = Object.entries(sentimentDist)
  const total = entries.reduce((s, [, c]) => s + c, 0)
  if (total === 0) return <div className="text-center py-8 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</div>

  const positif = (sentimentDist['positif'] || sentimentDist['positive'] || 0)
  const negatif = (sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0)
  const neutre = (sentimentDist['neutre'] || sentimentDist['neutral'] || 0)
  const mixte = (sentimentDist['mixte'] || sentimentDist['mixed'] || 0)

  // Global sentiment score: 0-100 where 50=neutral, >50=positive, <50=negative
  const score = total > 0
    ? Math.round(((positif * 100 + neutre * 55 + mixte * 50 + negatif * 10) / total))
    : 50

  // Arc: 180 degrees, score maps to position
  const angle = (score / 100) * 180
  const r = 70
  const cx = 80, cy = 80

  // Arc path for background
  const arcPath = (startAngle: number, endAngle: number) => {
    const s = (startAngle - 180) * Math.PI / 180
    const e = (endAngle - 180) * Math.PI / 180
    const x1 = cx + r * Math.cos(s)
    const y1 = cy + r * Math.sin(s)
    const x2 = cx + r * Math.cos(e)
    const y2 = cy + r * Math.sin(e)
    const large = endAngle - startAngle > 180 ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
  }

  // Needle position
  const needleAngle = (angle - 180) * Math.PI / 180
  const needleLen = r - 8
  const nx = cx + needleLen * Math.cos(needleAngle)
  const ny = cy + needleLen * Math.sin(needleAngle)

  const moodEmoji = score >= 70 ? '😊' : score >= 50 ? '😐' : score >= 30 ? '😟' : '😡'
  const moodLabel = score >= 70 ? 'Positif' : score >= 50 ? 'Neutre' : score >= 30 ? 'Tendu' : 'Négatif'
  const moodColor = score >= 70 ? '#34d399' : score >= 50 ? '#60a5fa' : score >= 30 ? '#fbbf24' : '#f87171'

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 160 95" className="w-full max-w-[200px]">
        {/* Background arc segments */}
        <path d={arcPath(0, 60)} fill="none" stroke="#f87171" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(60, 120)} fill="none" stroke="#fbbf24" strokeWidth="10" strokeLinecap="round" opacity="0.15" />
        <path d={arcPath(120, 180)} fill="none" stroke="#34d399" strokeWidth="10" strokeLinecap="round" opacity="0.15" />

        {/* Active arc */}
        <path d={arcPath(0, angle)} fill="none" stroke={moodColor} strokeWidth="10" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${moodColor}50)` }} />

        {/* Needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.8" />
        <circle cx={cx} cy={cy} r="4" fill="white" opacity="0.9" />

        {/* Score text */}
        <text x={cx} y={cy - 12} textAnchor="middle" fill="white" fontSize="22" fontWeight="bold">{score}</text>
        <text x={cx} y={cy - 0} textAnchor="middle" fill={moodColor} fontSize="8" fontWeight="500">{moodLabel}</text>
      </svg>

      <div className="text-2xl mt-1">{moodEmoji}</div>

      {/* Mini breakdown */}
      <div className="flex items-center gap-3 mt-3">
        {[
          { label: 'Positif', count: positif, color: '#34d399' },
          { label: 'Neutre', count: neutre, color: '#60a5fa' },
          { label: 'Négatif', count: negatif, color: '#f87171' },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {s.label} <span style={{ color: s.color }}>{total > 0 ? Math.round(s.count / total * 100) : 0}%</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Top Personalities ──────────────────────────────────
function TopPersonalities({ entities }: { entities: TopEntity[] }) {
  const colors = ['#60a5fa', '#34d399', '#facc15', '#f87171', '#c084fc', '#fb923c', '#67e8f9', '#f9a8d4']

  if (entities.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune entité</p>

  return (
    <div className="space-y-2">
      {entities.slice(0, 8).map((e, i) => {
        const color = colors[i % colors.length]
        const maxC = entities[0].count
        const initials = e.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
        return (
          <div key={i} className="flex items-center gap-3 group">
            {/* Avatar */}
            <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-[10px] font-bold"
              style={{
                background: `${color}18`,
                border: `1.5px solid ${color}40`,
                color: color,
              }}>
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.55)' }}>{e.name}</span>
                <span className="text-[10px] ml-2 flex-shrink-0 font-semibold" style={{ color }}>{e.count}</span>
              </div>
              <div className="h-1 rounded-full" style={{ background: 'rgba(255,255,255,0.03)' }}>
                <div className="h-full rounded-full transition-all duration-700" style={{
                  width: `${(e.count / maxC) * 100}%`,
                  background: `linear-gradient(90deg, ${color}80, ${color})`,
                  boxShadow: `0 0 6px ${color}20`,
                }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Trending Topics ────────────────────────────────────
function TrendingTopics({ themes }: { themes: Record<string, number> }) {
  const sorted = Object.entries(themes).sort(([, a], [, b]) => b - a)
  if (sorted.length === 0) return <p className="text-xs py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune donnée</p>

  const maxCount = sorted[0][1]

  return (
    <div className="space-y-3">
      {sorted.slice(0, 8).map(([theme, count], i) => {
        const color = themeColor(theme)
        const pct = Math.round((count / maxCount) * 100)
        return (
          <div key={theme}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold w-4 text-center" style={{ color: 'rgba(255,255,255,0.15)' }}>#{i + 1}</span>
                <span className="text-xs font-medium" style={{ color: 'rgba(255,255,255,0.55)' }}>{themeLabel(theme)}</span>
              </div>
              <span className="text-[11px] font-bold" style={{ color }}>{count} affaire{count > 1 ? 's' : ''}</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.03)' }}>
              <div className="h-full rounded-full transition-all duration-1000" style={{
                width: `${pct}%`,
                background: `linear-gradient(90deg, ${color}90, ${color})`,
                boxShadow: `0 0 8px ${color}30`,
              }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Activity Heatmap (7 days x hours) ──────────────────
function ActivityMiniChart({ data }: { data: DailyActivity[] }) {
  const maxArticles = Math.max(...data.map(d => d.articles), 1)
  return (
    <div className="flex items-end gap-2 h-32">
      {data.map((d, i) => {
        const h = (d.articles / maxArticles) * 100
        const isToday = i === data.length - 1
        return (
          <div key={i} className="flex-1 flex flex-col items-center gap-1.5 group relative">
            {/* Tooltip */}
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-200
              px-2.5 py-1 rounded-lg text-[9px] font-medium whitespace-nowrap z-10 pointer-events-none"
              style={{ background: 'rgba(37,99,235,0.95)', color: 'white', boxShadow: '0 4px 12px rgba(37,99,235,0.3)' }}>
              {d.articles} articles · {d.events} événements
            </div>
            {/* Bar */}
            <div className="w-full rounded-t-md transition-all duration-700 group-hover:brightness-125 relative"
              style={{
                height: `${Math.max(h, 4)}%`,
                background: isToday
                  ? 'linear-gradient(180deg, #facc15 0%, #f59e0b 100%)'
                  : `linear-gradient(180deg, #60a5fa 0%, #1d4ed8 100%)`,
                boxShadow: isToday ? '0 -2px 12px rgba(245,158,11,0.3)' : d.articles > 0 ? '0 -2px 12px rgba(37,99,235,0.15)' : 'none',
                borderRadius: '4px 4px 2px 2px',
              }}>
              {/* Value on top */}
              {d.articles > 0 && (
                <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ color: isToday ? '#facc15' : '#60a5fa' }}>
                  {d.articles}
                </span>
              )}
            </div>
            {/* Day label */}
            <span className={`text-[9px] leading-none font-medium ${isToday ? 'text-white/60' : ''}`}
              style={{ color: isToday ? undefined : 'rgba(255,255,255,0.2)' }}>
              {d.label.split(' ')[0]}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Major Stories Carousel ─────────────────────────────
function MajorStories({ affairs }: { affairs: Affair[] }) {
  const [idx, setIdx] = useState(0)
  const stories = affairs.slice(0, 5)

  useEffect(() => {
    if (stories.length <= 1) return
    const timer = setInterval(() => setIdx(i => (i + 1) % stories.length), 6000)
    return () => clearInterval(timer)
  }, [stories.length])

  if (stories.length === 0) {
    return <div className="text-center py-10 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire majeure</div>
  }

  const affair = stories[idx]
  const priority = affair.priority || 'minor'
  const accentColor = priority === 'hot' ? '#f87171' : priority === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      {/* Story card */}
      <Link href={`/affairs/${affair._id}`}>
        <div className="group cursor-pointer transition-all duration-500">
          <div className="flex items-start gap-4">
            {/* BMG inline */}
            <div className="flex-shrink-0 w-14 h-14 rounded-full border-2 border-cyan-500/40 flex items-center justify-center text-xs font-bold text-cyan-300">
              {Math.round((affair.bmg || 0) * 100)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                {priority === 'hot' && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-bold animate-pulse"
                    style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}>
                    URGENT
                  </span>
                )}
                <ThemeBadge theme={affair.theme} />
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{timeAgo(affair.last_activity || affair.created_at)}</span>
              </div>
              <h3 className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors line-clamp-2 mb-1.5">
                {affair.title || affair.primary_entity || 'Affaire'}
              </h3>
              {affair.description && (
                <p className="text-[11px] line-clamp-2 leading-relaxed" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  {affair.description}
                </p>
              )}
              <div className="flex items-center gap-3 mt-2">
                <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
                  {affair.item_count || 0} sources
                </span>
                <span className="text-[10px] font-semibold" style={{ color: accentColor }}>
                  Gravité {Math.round((affair.gravity_score || 0) * 100)}%
                </span>
                {affair.sentiment && (
                  <span className="text-[10px] capitalize" style={{
                    color: affair.sentiment === 'positif' ? '#34d399' : affair.sentiment === 'négatif' ? '#f87171' : '#60a5fa'
                  }}>{affair.sentiment}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </Link>

      {/* Dots navigation */}
      {stories.length > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-4">
          {stories.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className="transition-all duration-300"
              style={{
                width: i === idx ? 16 : 6,
                height: 6,
                borderRadius: 3,
                background: i === idx ? accentColor : 'rgba(255,255,255,0.1)',
                boxShadow: i === idx ? `0 0 8px ${accentColor}40` : 'none',
              }} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Affair Timeline (chronologie) ──────────────────────
function AffairTimeline({ affairs }: { affairs: Affair[] }) {
  // Sort by creation date, most recent first
  const sorted = [...affairs]
    .filter(a => a.created_at)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 12)

  if (sorted.length === 0) {
    return <div className="text-center py-6 text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>Aucune affaire</div>
  }

  // Find time range
  const now = Date.now()
  const oldest = new Date(sorted[sorted.length - 1].created_at).getTime()
  const range = Math.max(now - oldest, 86400000) // min 1 day range

  const priorityColor = (p: string) =>
    p === 'hot' ? '#f87171' : p === 'watch' ? '#fbbf24' : '#34d399'

  return (
    <div className="relative">
      {/* Time axis */}
      <div className="h-px w-full mb-1" style={{ background: 'rgba(255,255,255,0.06)' }} />

      {/* Time labels */}
      <div className="flex justify-between mb-4">
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>
          {new Date(oldest).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })}
        </span>
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.15)' }}>Aujourd'hui</span>
      </div>

      {/* Affair items */}
      <div className="space-y-2">
        {sorted.map((affair) => {
          const created = new Date(affair.created_at).getTime()
          const lastAct = affair.last_activity ? new Date(affair.last_activity).getTime() : created
          const startPct = ((created - oldest) / range) * 100
          const endPct = Math.min(((lastAct - oldest) / range) * 100, 100)
          const widthPct = Math.max(endPct - startPct, 2)
          const color = priorityColor(affair.priority || 'minor')
          const tc = themeColor(affair.theme)

          return (
            <Link key={affair._id} href={`/affairs/${affair._id}`}>
              <div className="group flex items-center gap-2 cursor-pointer hover:bg-white/[0.02] rounded-lg px-2 py-1.5 transition-all">
                {/* Title */}
                <div className="w-32 lg:w-40 flex-shrink-0">
                  <p className="text-[11px] truncate font-medium group-hover:text-white/80 transition-colors" style={{ color: 'rgba(255,255,255,0.45)' }}>
                    {affair.title || affair.primary_entity || '—'}
                  </p>
                  <p className="text-[9px]" style={{ color: 'rgba(255,255,255,0.12)' }}>
                    {timeAgo(affair.created_at)}
                  </p>
                </div>

                {/* Timeline bar */}
                <div className="flex-1 h-5 relative rounded-sm" style={{ background: 'rgba(255,255,255,0.02)' }}>
                  <div className="absolute h-full rounded-sm transition-all duration-500 group-hover:brightness-125 flex items-center"
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                      minWidth: 8,
                      background: `linear-gradient(90deg, ${color}60, ${color})`,
                      boxShadow: `0 0 6px ${color}20`,
                    }}>
                    {widthPct > 15 && (
                      <span className="text-[8px] font-bold px-1 truncate" style={{ color: 'white' }}>
                        {affair.item_count || 0}
                      </span>
                    )}
                  </div>
                </div>

                {/* BMG badge */}
                <div className="w-10 text-right flex-shrink-0">
                  <span className="text-[10px] font-bold" style={{ color }}>
                    {Math.round((affair.bmg || 0) * 100)}
                  </span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 justify-center">
        {[
          { label: 'Urgente', color: '#f87171' },
          { label: 'Suivi', color: '#fbbf24' },
          { label: 'Mineure', color: '#34d399' },
        ].map(l => (
          <div key={l.label} className="flex items-center gap-1">
            <div className="w-3 h-1.5 rounded-sm" style={{ background: l.color }} />
            <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.2)' }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Gravity Donut (kept from original) ────────────────
function GravityDonut({ distribution }: {
  distribution: { low: number; medium: number; high: number; critical: number }
}) {
  const total = distribution.low + distribution.medium + distribution.high + distribution.critical
  if (total === 0) return <p className="text-xs text-center py-4" style={{ color: 'rgba(255,255,255,0.2)' }}>Pas de données</p>

  const segments = [
    { key: 'low', label: 'Faible', count: distribution.low, color: '#34d399' },
    { key: 'medium', label: 'Moyen', count: distribution.medium, color: '#fbbf24' },
    { key: 'high', label: 'Élevé', count: distribution.high, color: '#fb923c' },
    { key: 'critical', label: 'Critique', count: distribution.critical, color: '#f87171' },
  ]

  const radius = 36, cx = 45, cy = 45
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const arcs = segments.filter(s => s.count > 0).map(s => {
    const pct = s.count / total
    const len = pct * circumference
    const arc = { ...s, pct, dasharray: `${len} ${circumference - len}`, dashoffset: -offset }
    offset += len
    return arc
  })

  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 90 90" className="w-20 h-20 flex-shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="10" />
        {arcs.map(a => (
          <circle key={a.key} cx={cx} cy={cy} r={radius} fill="none"
            stroke={a.color} strokeWidth="10"
            strokeDasharray={a.dasharray} strokeDashoffset={a.dashoffset}
            strokeLinecap="butt"
            style={{ filter: `drop-shadow(0 0 3px ${a.color}40)` }} />
        ))}
        <text x={cx} y={cy + 4} textAnchor="middle" fill="white" fontSize="14" fontWeight="bold"
          style={{ transform: 'rotate(90deg)', transformOrigin: '50% 50%' }}>
          {total}
        </text>
      </svg>
      <div className="space-y-1 flex-1">
        {segments.map(s => (
          <div key={s.key} className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
            <span className="text-[10px] flex-1" style={{ color: 'rgba(255,255,255,0.4)' }}>{s.label}</span>
            <span className="text-[10px] font-semibold" style={{ color: s.color }}>
              {s.count} <span style={{ color: 'rgba(255,255,255,0.12)' }}>({total > 0 ? Math.round(s.count / total * 100) : 0}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Skeleton ────────────────────────────────
function SkeletonCard() {
  return (
    <div className="glass-card-static p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="skeleton h-2.5 w-20" />
        <div className="skeleton h-5 w-5 rounded-full" />
      </div>
      <div className="skeleton h-8 w-16 mb-2" />
      <div className="skeleton h-1.5 w-full mb-2 rounded-full" />
      <div className="skeleton h-2 w-24" />
    </div>
  )
}

function SkeletonWidget() {
  return (
    <div className="glass-card-static p-5">
      <div className="flex items-center justify-between mb-2">
        <div className="skeleton h-2.5 w-24" />
        <div className="skeleton h-5 w-5 rounded-full" />
      </div>
      <div className="skeleton h-2 w-40 mb-4" />
      <div className="space-y-3">
        <div className="skeleton h-3 w-full" />
        <div className="skeleton h-3 w-4/5" />
        <div className="skeleton h-3 w-3/5" />
        <div className="skeleton h-3 w-4/5" />
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════
// MAIN DASHBOARD
// ════════════════════════════════════════════════════════════
export default function DashboardPage() {
  const [data, setData] = useState<EnrichedDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cycleRunning, setCycleRunning] = useState(false)
  const [scraping, setScraping] = useState(false)
  const [reaffiliating, setReaffiliating] = useState(false)
  const [bulkEnriching, setBulkEnriching] = useState(false)
  const [bulkMsg, setBulkMsg] = useState('')
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [communeMapData, setCommuneMapData] = useState<Record<string, { count: number; maxGravity: number; affairs: Array<{ _id: string; title: string; gravity_score: number; sentiment: string; theme: string }> }>>({})
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null)
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null)
  const [mapBgData, setMapBgData] = useState<Record<string, { stats: { total_items: number; max_gravity: number } }>>({})

  // ── Search state ──
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const searchTimeout = useRef<NodeJS.Timeout | null>(null)

  // ── Theme mode ──
  const [themeMode, setThemeMode] = useState<'dark' | 'light'>('dark')

  useEffect(() => {
    const saved = localStorage.getItem('veille-theme') || 'dark'
    setThemeMode(saved as 'dark' | 'light')
    document.documentElement.setAttribute('data-theme', saved)
  }, [])

  // ── Summary state ──
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [summaryData, setSummaryData] = useState<SummaryResponse | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [summaryPeriod, setSummaryPeriod] = useState<'journalier' | 'hebdomadaire'>('journalier')

  // ── Map filters ──
  const [mapFilterTheme, setMapFilterTheme] = useState<string>('all')
  const [mapFilterGravity, setMapFilterGravity] = useState<string>('all')

  // ── Notifications ──
  const [notifications, setNotifications] = useState<Array<{ id: number; text: string; type: 'hot' | 'info' | 'success' }>>([])
  const notifIdRef = useRef(0)

  const addNotification = useCallback((text: string, type: 'hot' | 'info' | 'success' = 'info') => {
    const id = ++notifIdRef.current
    setNotifications(prev => [...prev.slice(-4), { id, text, type }])
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 5000)
  }, [])

  const handleGenerateSummary = useCallback(async (period: 'journalier' | 'hebdomadaire') => {
    setSummaryLoading(true)
    setSummaryPeriod(period)
    setSummaryOpen(true)
    try {
      const res = await fetchSummary(period)
      setSummaryData(res)
    } catch (e) {
      console.error('Summary error:', e)
    } finally {
      setSummaryLoading(false)
    }
  }, [])

  const toggleTheme = useCallback(() => {
    const next = themeMode === 'dark' ? 'light' : 'dark'
    setThemeMode(next)
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('veille-theme', next)
  }, [themeMode])

  // ── Radio state ──
  const [radioHealth, setRadioHealth] = useState<Array<{ key: string; name: string; status: string; latency_ms: number }>>([])
  const [radioToday, setRadioToday] = useState<{ count: number; cards: Array<Record<string, unknown>> }>({ count: 0, cards: [] })
  const [radioCapturing, setRadioCapturing] = useState<string | null>(null)
  const [radioPanelOpen, setRadioPanelOpen] = useState(false)

  const loadRadioStatus = useCallback(async () => {
    try {
      const [health, today] = await Promise.all([
        fetchRadioHealth().catch(() => ({ results: [], summary: { total: 0, healthy: 0, degraded: 0, down: 0 }, checked_at: '' })),
        fetchRadioToday().catch(() => ({ cards: [], count: 0 })),
      ])
      setRadioHealth(health.results || [])
      setRadioToday(today)
    } catch { /* silent */ }
  }, [])

  const handleRadioCapture = useCallback(async (streamKey: string) => {
    setRadioCapturing(streamKey)
    try {
      await triggerRadioCapture(streamKey, 30)
      await loadRadioStatus()
    } catch (e) {
      console.error('Radio capture error:', e)
    } finally {
      setRadioCapturing(null)
    }
  }, [loadRadioStatus])

  useEffect(() => { loadRadioStatus() }, [loadRadioStatus])

  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (!q.trim() || q.trim().length < 2) {
      setSearchResults(null)
      setSearchOpen(false)
      return
    }
    setSearching(true)
    searchTimeout.current = setTimeout(async () => {
      try {
        const res = await fetchSearch(q.trim())
        setSearchResults(res)
        setSearchOpen(true)
      } catch { setSearchResults(null) }
      finally { setSearching(false) }
    }, 400)
  }, [])

  const loadData = useCallback(async () => {
    try {
      const [result, mapRes, storageRes, mapBgRes] = await Promise.all([
        fetchEnrichedDashboard(),
        fetchAffairsByCommune().catch(() => ({ communes: {} })),
        fetchStorageStats().catch(() => null),
        fetchMapData(7).catch(() => null),
      ])
      setData(result)
      setCommuneMapData(mapRes.communes || {})
      if (storageRes) setStorageStats(storageRes)
      if (mapBgRes?.communes) setMapBgData(mapBgRes.communes as any)
      setError('')
      setLastRefresh(new Date())

      // Check for new hot affairs
      if (data && result) {
        const oldHot = data.affairs?.filter((a: any) => a.priority === 'hot').length || 0
        const newHot = result.affairs?.filter((a: any) => a.priority === 'hot').length || 0
        if (newHot > oldHot) {
          addNotification(`${newHot - oldHot} nouvelle(s) affaire(s) urgente(s) détectée(s)`, 'hot')
        }
      }
    } catch (e: unknown) {
      setError((e as Error).message || 'Erreur de connexion')
    } finally { setLoading(false) }
  }, [data, addNotification])

  // Rendre le body + html transparent pour que la carte Mapbox soit visible
  useEffect(() => {
    document.documentElement.style.background = 'transparent'
    document.body.classList.add('map-dashboard-mode')
    document.body.style.background = 'transparent'
    // Aussi forcer le parent Next.js
    const nextRoot = document.getElementById('__next')
    if (nextRoot) nextRoot.style.background = 'transparent'
    // Forcer le wrapper z-10 du layout à être transparent
    const zWrapper = document.querySelector('.relative.z-10') as HTMLElement
    if (zWrapper) zWrapper.style.background = 'transparent'
    return () => {
      document.documentElement.style.background = ''
      document.body.classList.remove('map-dashboard-mode')
      document.body.style.background = ''
      if (nextRoot) nextRoot.style.background = ''
      if (zWrapper) zWrapper.style.background = ''
    }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 90_000)
    return () => clearInterval(interval)
  }, [loadData])

  const handleRunCycle = async () => {
    setCycleRunning(true)
    try { await runFullCycle(); await loadData(); addNotification('Cycle terminé avec succès', 'success') }
    catch (e: unknown) { console.error('Cycle error:', e) }
    finally { setCycleRunning(false) }
  }

  const handleScrape = async () => {
    setScraping(true)
    try { await runScrapeNow(); await loadData(); addNotification('Scraping terminé', 'success') }
    catch (e: unknown) { console.error('Scrape error:', e) }
    finally { setScraping(false) }
  }

  const handleReaffiliate = async () => {
    setReaffiliating(true)
    try { await runReaffiliate(); await loadData() }
    catch (e: unknown) { console.error('Reaffiliate error:', e) }
    finally { setReaffiliating(false) }
  }

  const handleBulkEnrich = async () => {
    setBulkEnriching(true)
    setBulkMsg('')
    try {
      const res = await runBulkEnrich(200, 90)
      setBulkMsg(res.message || `${res.enriched} enrichis`)
      await loadData()
    } catch (e: unknown) { console.error('Bulk enrich error:', e); setBulkMsg('Erreur') }
    finally { setBulkEnriching(false) }
  }

  const topAffairs = data?.top_affairs || []
  const criticals = data?.critical_alerts || []
  const stats = data?.stats
  const coverage = data?.coverage
  const themes = data?.themes_distribution || {}
  const entities = data?.top_entities || []
  const activity = data?.daily_activity || []
  const orphans = data?.orphan_articles || []
  const timeline = data?.recent_timeline || []
  const sources = data?.top_sources || []
  const gravityDist = data?.gravity_distribution
  const sentimentDist = data?.sentiment_distribution || {}
  const priorityCounts = data?.priority_counts || {}
  const trends = data?.trends
  const avgBmg = data?.avg_bmg || 0

  // ── Panneau style commun ──
  const panelStyle = `rounded-2xl shadow-2xl ${themeMode === 'light' ? 'border border-black/8' : 'border border-white/10'}`
  const panelBg = themeMode === 'light'
    ? { background: 'rgba(255,255,255,0.82)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }
    : { background: 'rgba(2,6,23,0.82)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />

      {/* Zone principale = carte plein écran + widgets flottants */}
      <div className="lg:ml-60 flex-1 relative h-screen overflow-hidden">

        {/* ══ CARTE 3D PLEIN ÉCRAN ══ */}
        <MapboxFullMap communes={mapBgData} onSelectCommune={setSelectedCommune} />

        {/* ══ WIDGETS FLOTTANTS ══ */}
        <div className="absolute inset-0 z-10 pointer-events-none">

          {/* ── TOP BAR: Header + Actions ── */}
          <div className="pointer-events-auto absolute top-3 left-3 right-3 flex items-center justify-between gap-3">
            <div className={`${panelStyle} px-4 py-2.5 flex items-center gap-3`} style={panelBg}>
              <h1 className="text-sm lg:text-base font-bold text-white tracking-tight">Veille Média 971</h1>
              <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold"
                style={{ background: 'rgba(22,163,74,0.15)', color: '#34d399', border: '1px solid rgba(22,163,74,0.3)' }}>
                LIVE
              </span>
              <span className="text-[10px] font-medium" style={{ color: 'rgba(255,255,255,0.3)' }}>
                {lastRefresh.toLocaleTimeString('fr-FR')}
              </span>
            </div>

            {/* ── Search Bar ── */}
            <div className="relative flex-1 max-w-xs">
              <div className={`${panelStyle} flex items-center gap-2 px-3 py-1.5`} style={panelBg}>
                <svg className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'rgba(255,255,255,0.4)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  placeholder="Rechercher…"
                  value={searchQuery}
                  onChange={e => handleSearch(e.target.value)}
                  onFocus={() => searchResults && setSearchOpen(true)}
                  onBlur={() => setTimeout(() => setSearchOpen(false), 200)}
                  className="bg-transparent border-none outline-none text-xs text-white placeholder-white/30 w-full"
                />
                {searching && <span className="text-[10px] text-cyan-400 animate-pulse">⟳</span>}
                {searchQuery && !searching && (
                  <button onClick={() => { setSearchQuery(''); setSearchResults(null); setSearchOpen(false) }}
                    className="text-white/30 hover:text-white/60 text-xs">✕</button>
                )}
              </div>
              {/* Search Results Dropdown */}
              {searchOpen && searchResults && (searchResults.total_articles > 0 || searchResults.total_affairs > 0) && (
                <div className="absolute top-full mt-1 left-0 right-0 z-50 rounded-xl overflow-hidden shadow-2xl"
                  style={{ background: 'rgba(10,15,30,0.95)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)', maxHeight: '400px', overflowY: 'auto' }}>
                  {searchResults.total_affairs > 0 && (
                    <div className="px-3 pt-2 pb-1">
                      <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(147,197,253,0.6)' }}>
                        Affaires ({searchResults.total_affairs})
                      </p>
                      {searchResults.affairs.slice(0, 5).map(a => (
                        <div key={a._id} className="py-1.5 border-b border-white/5 cursor-pointer hover:bg-white/5 px-1 rounded"
                          onMouseDown={() => { setSelectedCommune(null); setSearchOpen(false) }}>
                          <p className="text-xs text-white/90 font-medium truncate">{a.title}</p>
                          <p className="text-[10px] text-white/40 truncate">{a.theme} · gravité {Math.round((a.gravity_score || 0) * 100)}%</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {searchResults.total_articles > 0 && (
                    <div className="px-3 pt-2 pb-2">
                      <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(253,224,71,0.6)' }}>
                        Articles ({searchResults.total_articles})
                      </p>
                      {searchResults.articles.slice(0, 5).map(a => (
                        <div key={a._id} className="py-1.5 border-b border-white/5 px-1">
                          <p className="text-xs text-white/90 truncate">{a.title}</p>
                          <p className="text-[10px] text-white/40 truncate">{a.source} · {a.date ? new Date(a.date).toLocaleDateString('fr-FR') : ''}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Theme Toggle */}
            <button onClick={toggleTheme} className="btn-glass px-2 py-1.5 rounded-xl text-sm" title={themeMode === 'dark' ? 'Mode clair' : 'Mode sombre'}>
              {themeMode === 'dark' ? '☀️' : '🌙'}
            </button>

            <div className={`${panelStyle} px-3 py-2 flex items-center gap-2`} style={panelBg}>
              <button onClick={() => handleGenerateSummary(summaryPeriod)} disabled={summaryLoading} className="btn-glass px-2.5 py-1 text-[10px] disabled:opacity-40">
                {summaryLoading ? '⟳...' : '📰 Résumé'}
              </button>
              <button onClick={loadData} className="btn-glass px-2.5 py-1 text-[10px]">
                <svg className="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                MAJ
              </button>
              <button onClick={handleScrape} disabled={scraping} className="btn-glass px-2.5 py-1 text-[10px] disabled:opacity-40">
                {scraping ? '⟳...' : 'Scraper'}
              </button>
              <button onClick={handleRunCycle} disabled={cycleRunning} className="btn-primary px-3 py-1 text-[10px]">
                {cycleRunning ? '⟳...' : '▶ Cycle'}
              </button>
              <button onClick={() => {
                const url = `${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'}/api/export/csv?type=affairs`
                window.open(url, '_blank')
              }} className="btn-glass px-2.5 py-1 text-[10px]">
                📥 CSV
              </button>
            </div>
          </div>

          {error && (
            <div className="pointer-events-auto absolute top-16 left-3 right-3 px-4 py-2 rounded-xl text-xs z-20" style={{
              background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#f87171',
              backdropFilter: 'blur(12px)',
            }}>{error}</div>
          )}

          {/* ── Map Filters ── */}
          <div className="pointer-events-auto absolute top-16 right-3 flex flex-col gap-1.5 z-20">
            <div className={`${panelStyle} px-2.5 py-2 flex flex-col gap-1`} style={panelBg}>
              <p className="text-[8px] uppercase tracking-wider font-semibold opacity-40 mb-0.5">Thème</p>
              {['all', 'politique', 'justice', 'social', 'économie', 'environnement', 'santé'].map(t => (
                <button key={t} onClick={() => setMapFilterTheme(t)}
                  className={`text-[9px] px-2 py-0.5 rounded-lg text-left transition-all ${mapFilterTheme === t ? 'bg-indigo-500/20 text-indigo-300 font-semibold' : 'opacity-50 hover:opacity-80'}`}>
                  {t === 'all' ? 'Tous' : t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <div className={`${panelStyle} px-2.5 py-2 flex flex-col gap-1`} style={panelBg}>
              <p className="text-[8px] uppercase tracking-wider font-semibold opacity-40 mb-0.5">Gravité</p>
              {[
                { key: 'all', label: 'Toutes', color: '' },
                { key: 'critical', label: 'Critique', color: 'text-red-400' },
                { key: 'high', label: 'Élevée', color: 'text-orange-400' },
                { key: 'medium', label: 'Moyenne', color: 'text-yellow-400' },
                { key: 'low', label: 'Faible', color: 'text-green-400' },
              ].map(g => (
                <button key={g.key} onClick={() => setMapFilterGravity(g.key)}
                  className={`text-[9px] px-2 py-0.5 rounded-lg text-left transition-all ${g.color} ${mapFilterGravity === g.key ? 'bg-white/10 font-semibold' : 'opacity-50 hover:opacity-80'}`}>
                  {g.label}
                </button>
              ))}
            </div>
          </div>

          {/* ══ LEFT PANEL: KPIs + Alertes + Affaires ══ */}
          <div className="pointer-events-auto absolute top-16 left-3 bottom-3 w-[320px] lg:w-[340px] flex flex-col gap-2.5 overflow-y-auto overflow-x-hidden scrollbar-hide" style={{ maxHeight: 'calc(100vh - 80px)' }}>

            {/* KPI Row */}
            {!loading && stats && (
              <div className="grid grid-cols-2 gap-2">
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(147,197,253,0.7)' }}>Affaires</p>
                  <p className="text-2xl font-bold" style={{ color: '#93c5fd' }}>{stats.affairs_active ?? 0}</p>
                  <div className="flex gap-1 mt-1">
                    {(priorityCounts.hot || 0) > 0 && <span className="text-[8px] px-1.5 py-0.5 rounded-full font-bold" style={{ background: 'rgba(239,68,68,0.2)', color: '#fca5a5' }}>{priorityCounts.hot} urgentes</span>}
                  </div>
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(253,224,71,0.7)' }}>Articles 7j</p>
                  <div className="flex items-baseline gap-1.5">
                    <p className="text-2xl font-bold" style={{ color: '#fde68a' }}>{coverage?.total_articles_7d ?? 0}</p>
                    {trends && <TrendArrow pct={trends.articles_trend_pct} />}
                  </div>
                  <p className="text-[9px] mt-0.5" style={{ color: 'rgba(253,224,71,0.4)' }}>{coverage?.enriched_articles_7d ?? 0} enrichis IA</p>
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(134,239,172,0.7)' }}>Climat</p>
                  {(() => {
                    const pos = sentimentDist['positif'] || sentimentDist['positive'] || 0
                    const neg = sentimentDist['négatif'] || sentimentDist['negatif'] || sentimentDist['negative'] || 0
                    const total = Object.values(sentimentDist).reduce((s, v) => s + v, 0)
                    const pctNeg = total > 0 ? Math.round(neg / total * 100) : 0
                    const isNeg = pctNeg > 30
                    return <>
                      <p className="text-lg font-bold" style={{ color: isNeg ? '#fca5a5' : '#86efac' }}>{isNeg ? 'Tendu' : 'Calme'}</p>
                      <div className="h-1.5 rounded-full overflow-hidden flex mt-1" style={{ background: 'rgba(255,255,255,0.08)' }}>
                        <div style={{ width: `${total > 0 ? Math.round(pos/total*100) : 33}%`, background: '#34d399' }} />
                        <div style={{ width: `${total > 0 ? Math.round((total-pos-neg)/total*100) : 34}%`, background: '#60a5fa' }} />
                        <div style={{ width: `${pctNeg}%`, background: '#f87171' }} />
                      </div>
                    </>
                  })()}
                </div>
                <div className={`${panelStyle} p-3`} style={panelBg}>
                  <p className="text-[9px] uppercase tracking-wider font-semibold" style={{ color: 'rgba(167,139,250,0.7)' }}>Couverture</p>
                  <p className="text-2xl font-bold" style={{ color: '#c4b5fd' }}>{coverage?.affiliation_rate ?? 0}%</p>
                  <p className="text-[9px] mt-0.5" style={{ color: 'rgba(167,139,250,0.4)' }}>{coverage?.total_transcriptions_7d ?? 0} radios</p>
                </div>
              </div>
            )}

            {/* Alertes critiques */}
            {criticals.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" style={{ boxShadow: '0 0 8px rgba(239,68,68,0.5)' }} />
                  <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#f87171' }}>Alertes</h2>
                </div>
                <div className="space-y-1">
                  {criticals.slice(0, 3).map((a) => (
                    <Link key={a._id} href={`/affairs/${a._id}`}>
                      <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition-all hover:translate-x-0.5"
                        style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)' }}>
                        <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
                        <p className="text-[11px] font-medium text-white truncate flex-1">{a.title || a.primary_entity}</p>
                        <span className="text-[10px] font-bold flex-shrink-0" style={{ color: '#f87171' }}>{Math.round((a.bmg || 0) * 100)}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Top Affaires */}
            {topAffairs.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>Affaires du moment</h2>
                  <Link href="/affairs" className="text-[9px]" style={{ color: '#60a5fa' }}>Tout voir →</Link>
                </div>
                <div className="space-y-1">
                  {topAffairs.slice(0, 8).map(affair => {
                    const g = affair.gravity_score || 0
                    const color = g >= 0.7 ? '#f87171' : g >= 0.5 ? '#fbbf24' : '#34d399'
                    return (
                      <Link key={affair._id} href={`/affairs/${affair._id}`}>
                        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg transition-all hover:bg-white/5 cursor-pointer">
                          <div className="w-1 h-6 rounded-full flex-shrink-0" style={{ background: color }} />
                          <div className="flex-1 min-w-0">
                            <p className="text-[11px] font-medium text-white truncate">{affair.title || affair.primary_entity}</p>
                            <div className="flex items-center gap-1.5">
                              <ThemeBadge theme={affair.theme || 'general'} />
                              <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{affair.item_count || 0} items</span>
                            </div>
                          </div>
                          <span className="text-[10px] font-bold flex-shrink-0" style={{ color }}>{Math.round((affair.bmg || 0) * 100)}</span>
                        </div>
                      </Link>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Sujets tendance */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Sujets tendance</h2>
              <TrendingTopics themes={themes} />
            </div>

            {/* ── Radio / Captures ── */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'rgba(139,92,246,0.6)' }}>
                  Radio · Captures
                </h2>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] px-1.5 py-0.5 rounded-full font-semibold"
                    style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa' }}>
                    {radioToday.count} aujourd'hui
                  </span>
                  <button onClick={() => setRadioPanelOpen(!radioPanelOpen)}
                    className="text-[9px] text-white/30 hover:text-white/60">
                    {radioPanelOpen ? '▾' : '▸'}
                  </button>
                </div>
              </div>

              {/* Status indicators */}
              <div className="flex flex-wrap gap-1 mb-2">
                {radioHealth.slice(0, 6).map(stream => (
                  <div key={stream.key} className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-lg"
                    style={{ background: 'rgba(255,255,255,0.03)' }}
                    title={`${stream.name} — ${stream.status} (${stream.latency_ms}ms)`}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{
                      background: stream.status === 'healthy' ? '#34d399' : stream.status === 'degraded' ? '#fbbf24' : '#f87171'
                    }} />
                    <span className="text-white/50 truncate max-w-[60px]">{stream.name?.split('_')[0] || stream.key}</span>
                  </div>
                ))}
              </div>

              {/* Expanded panel */}
              {radioPanelOpen && (
                <div className="space-y-1.5 mt-2 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <p className="text-[9px] text-white/30 mb-1">Lancer une capture manuelle :</p>
                  {radioHealth.map(stream => (
                    <div key={stream.key} className="flex items-center justify-between gap-2 py-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{
                          background: stream.status === 'healthy' ? '#34d399' : stream.status === 'degraded' ? '#fbbf24' : '#f87171'
                        }} />
                        <span className="text-[10px] text-white/70 truncate">{stream.name || stream.key}</span>
                        <span className="text-[8px] text-white/20">{stream.latency_ms}ms</span>
                      </div>
                      <button
                        onClick={() => handleRadioCapture(stream.key)}
                        disabled={radioCapturing !== null}
                        className="flex-shrink-0 text-[9px] px-2 py-0.5 rounded-lg font-semibold transition-all disabled:opacity-30"
                        style={{ background: 'rgba(139,92,246,0.15)', color: '#a78bfa', border: '1px solid rgba(139,92,246,0.2)' }}>
                        {radioCapturing === stream.key ? '⟳ Capture...' : '▶ Capturer'}
                      </button>
                    </div>
                  ))}
                  <button onClick={loadRadioStatus}
                    className="w-full text-[9px] text-white/30 hover:text-white/50 mt-1 py-1">
                    ↻ Rafraîchir statuts
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ══ RIGHT PANEL: Personnalités + Sentiment + Commune sélectionnée ══ */}
          <div className="pointer-events-auto absolute top-16 right-3 bottom-3 w-[280px] lg:w-[300px] hidden lg:flex flex-col gap-2.5 overflow-y-auto overflow-x-hidden scrollbar-hide" style={{ maxHeight: 'calc(100vh - 80px)' }}>

            {/* Commune sélectionnée */}
            {selectedCommune && mapBgData[selectedCommune] && (
              <div className={`${panelStyle} p-3`} style={{ ...panelBg, borderColor: 'rgba(99,102,241,0.3)' }}>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-xs font-bold text-white">{selectedCommune}</h2>
                  <button onClick={() => setSelectedCommune(null)} className="text-[10px] px-1.5 py-0.5 rounded" style={{ color: 'rgba(255,255,255,0.4)' }}>✕</button>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <p className="text-lg font-bold" style={{ color: '#60a5fa' }}>{(mapBgData[selectedCommune] as any)?.stats?.article_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Articles</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold" style={{ color: '#a78bfa' }}>{(mapBgData[selectedCommune] as any)?.stats?.transcription_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Radios</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold" style={{ color: '#fbbf24' }}>{(mapBgData[selectedCommune] as any)?.stats?.affair_count || 0}</p>
                    <p className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.3)' }}>Affaires</p>
                  </div>
                </div>
              </div>
            )}

            {/* Sentiment Gauge */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Climat médiatique</h2>
              <SentimentGauge sentimentDist={sentimentDist} />
            </div>

            {/* Personnalités */}
            <div className={`${panelStyle} p-3`} style={panelBg}>
              <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Personnalités clés</h2>
              <TopPersonalities entities={entities} />
            </div>

            {/* Gravité */}
            {gravityDist && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Gravité des affaires</h2>
                <GravityDonut distribution={gravityDist} />
              </div>
            )}

            {/* Sources */}
            {sources.length > 0 && (
              <div className={`${panelStyle} p-3`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Top sources</h2>
                <div className="space-y-1">
                  {sources.slice(0, 5).map((s, i) => (
                    <div key={s.name} className="flex items-center gap-2">
                      <span className="text-[9px] font-bold w-4 text-right" style={{ color: 'rgba(255,255,255,0.25)' }}>#{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[10px] text-white truncate">{s.name}</p>
                      </div>
                      <span className="text-[10px] font-semibold" style={{ color: '#60a5fa' }}>{s.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ══ BOTTOM BAR: Mini stats + Activité ══ */}
          <div className="pointer-events-auto absolute bottom-3 left-[340px] lg:left-[360px] right-[300px] lg:right-[320px] hidden lg:flex gap-2.5">
            {/* Activité mini chart */}
            {activity.length > 0 && (
              <div className={`${panelStyle} p-3 flex-1`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'rgba(255,255,255,0.35)' }}>Activité 7 jours</h2>
                <ActivityMiniChart data={activity} />
              </div>
            )}

            {/* Pipeline */}
            {stats && (
              <div className={`${panelStyle} p-3 flex-1`} style={panelBg}>
                <h2 className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'rgba(255,255,255,0.35)' }}>Pipeline</h2>
                <div className="flex items-center gap-2">
                  {[
                    { label: 'Candidats', value: stats.candidates_total, color: '#fbbf24' },
                    { label: 'Clusters', value: stats.clusters_active, color: '#facc15' },
                    { label: 'Actives', value: stats.affairs_active, color: '#60a5fa' },
                    { label: 'Veille', value: stats.affairs_stale, color: 'rgba(255,255,255,0.35)' },
                  ].map((s, i, arr) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <div className="text-center">
                        <p className="text-sm font-bold" style={{ color: s.color }}>{s.value ?? 0}</p>
                        <p className="text-[8px]" style={{ color: 'rgba(255,255,255,0.25)' }}>{s.label}</p>
                      </div>
                      {i < arr.length - 1 && <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.1)' }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Notifications ── */}
          <div className="pointer-events-auto fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
            {notifications.map(n => (
              <div key={n.id} className="animate-slide-up rounded-xl px-4 py-2.5 shadow-2xl text-xs font-medium flex items-center gap-2"
                style={{
                  background: n.type === 'hot' ? 'rgba(239,68,68,0.9)' : n.type === 'success' ? 'rgba(16,185,129,0.9)' : 'rgba(99,102,241,0.9)',
                  color: 'white',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid rgba(255,255,255,0.15)',
                }}>
                <span>{n.type === 'hot' ? '🔴' : n.type === 'success' ? '✅' : 'ℹ️'}</span>
                <span>{n.text}</span>
                <button onClick={() => setNotifications(prev => prev.filter(x => x.id !== n.id))} className="ml-auto opacity-60 hover:opacity-100">✕</button>
              </div>
            ))}
          </div>


        {/* ══ SUMMARY MODAL ══ */}
        {summaryOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}>
            <div className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl shadow-2xl"
              style={themeMode === 'light'
                ? { background: '#ffffff', border: '1px solid rgba(0,0,0,0.1)' }
                : { background: '#0f1219', border: '1px solid rgba(255,255,255,0.1)' }
              }>
              {/* Header */}
              <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b"
                style={themeMode === 'light'
                  ? { background: '#ffffff', borderColor: 'rgba(0,0,0,0.08)' }
                  : { background: '#0f1219', borderColor: 'rgba(255,255,255,0.08)' }
                }>
                <div>
                  <h2 className="text-lg font-bold" style={{ color: themeMode === 'light' ? '#1e293b' : '#f1f5f9' }}>
                    {summaryData?.summary?.titre || 'Résumé en cours...'}
                  </h2>
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => handleGenerateSummary('journalier')}
                      className={`text-[10px] px-2.5 py-1 rounded-full font-semibold transition-all ${summaryPeriod === 'journalier' ? 'bg-indigo-500 text-white' : 'btn-glass'}`}>
                      Journalier
                    </button>
                    <button onClick={() => handleGenerateSummary('hebdomadaire')}
                      className={`text-[10px] px-2.5 py-1 rounded-full font-semibold transition-all ${summaryPeriod === 'hebdomadaire' ? 'bg-indigo-500 text-white' : 'btn-glass'}`}>
                      Hebdomadaire
                    </button>
                  </div>
                </div>
                <button onClick={() => setSummaryOpen(false)} className="text-xl opacity-50 hover:opacity-100 transition-opacity">✕</button>
              </div>

              {/* Body */}
              <div className="px-6 py-4">
                {summaryLoading ? (
                  <div className="flex flex-col items-center justify-center py-16 gap-3">
                    <div className="text-3xl animate-spin">⟳</div>
                    <p className="text-sm opacity-50">Génération du résumé IA en cours...</p>
                    <p className="text-[10px] opacity-30">Analyse de {summaryPeriod === 'journalier' ? "24h" : "7 jours"} d'actualité</p>
                  </div>
                ) : summaryData?.summary ? (
                  <div className="space-y-6">
                    {/* Introduction */}
                    <p className="text-sm leading-relaxed opacity-80">{summaryData.summary.introduction}</p>

                    {/* Sections */}
                    {summaryData.summary.sections?.map((section, si) => (
                      <div key={si}>
                        <h3 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color: themeMode === 'light' ? '#4f46e5' : '#818cf8' }}>
                          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                          {section.titre}
                        </h3>
                        <div className="space-y-3 ml-3">
                          {section.articles?.map((art, ai) => (
                            <div key={ai} className="rounded-xl p-3 text-xs"
                              style={themeMode === 'light'
                                ? { background: 'rgba(0,0,0,0.03)', border: '1px solid rgba(0,0,0,0.06)' }
                                : { background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }
                              }>
                              <div className="flex items-start justify-between gap-2 mb-1">
                                <p className="font-semibold text-xs">{art.titre}</p>
                                <span className={`flex-shrink-0 text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                                  art.gravite === 'critique' ? 'badge-critical' :
                                  art.gravite === 'élevée' ? 'badge-high' :
                                  art.gravite === 'moyenne' ? 'badge-medium' : 'badge-low'
                                }`}>{art.gravite}</span>
                              </div>
                              <p className="opacity-70 leading-relaxed mb-1.5">{art.resume}</p>
                              {art.contexte && <p className="opacity-50 italic text-[10px] mb-1">{art.contexte}</p>}
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {art.communes?.map((c, ci) => (
                                  <span key={ci} className="text-[9px] px-1.5 py-0.5 rounded-full" style={themeMode === 'light' ? { background: 'rgba(99,102,241,0.1)', color: '#4f46e5' } : { background: 'rgba(99,102,241,0.15)', color: '#a5b4fc' }}>{c}</span>
                                ))}
                                {art.sources?.map((s, si) => (
                                  <span key={si} className="text-[9px] px-1.5 py-0.5 rounded-full" style={themeMode === 'light' ? { background: 'rgba(245,158,11,0.1)', color: '#b45309' } : { background: 'rgba(245,158,11,0.15)', color: '#fbbf24' }}>{s}</span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}

                    {/* Tendances */}
                    {summaryData.summary.tendances && (
                      <div className="rounded-xl p-4" style={themeMode === 'light' ? { background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)' } : { background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
                        <h3 className="text-xs font-bold mb-2" style={{ color: '#34d399' }}>Tendances</h3>
                        <p className="text-xs opacity-70 leading-relaxed">{summaryData.summary.tendances}</p>
                      </div>
                    )}

                    {/* À surveiller */}
                    {summaryData.summary.a_surveiller?.length > 0 && (
                      <div className="rounded-xl p-4" style={themeMode === 'light' ? { background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)' } : { background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                        <h3 className="text-xs font-bold mb-2" style={{ color: '#fbbf24' }}>À surveiller</h3>
                        <ul className="space-y-1">
                          {summaryData.summary.a_surveiller.map((item, i) => (
                            <li key={i} className="text-xs opacity-70 flex items-start gap-1.5">
                              <span className="text-[10px] mt-0.5" style={{ color: '#fbbf24' }}>▸</span>
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Meta */}
                    <p className="text-[10px] opacity-30 text-right">
                      Généré le {new Date(summaryData.generated_at).toLocaleString('fr-FR')} · {summaryData.affairs_count} affaires · {summaryData.articles_count} articles
                    </p>
                  </div>
                ) : (
                  <p className="text-sm opacity-50 text-center py-8">Aucun résumé disponible</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── BOTTOM TIMELINE BAR ── */}
        {!loading && data?.daily_activity && data.daily_activity.length > 0 && (
          <div className="pointer-events-auto absolute bottom-3 left-3 right-3 lg:left-[360px]">
            <div className={`${panelStyle} px-4 py-2.5 flex items-end gap-[3px]`}
              style={themeMode === 'light'
                ? { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }
                : panelBg
              }>
              <span className="text-[9px] font-semibold mr-2 self-center"
                style={{ color: themeMode === 'light' ? '#64748b' : 'rgba(255,255,255,0.4)' }}>
                30j
              </span>
              {(() => {
                const activity = data.daily_activity.slice(-30)
                const maxCount = Math.max(...activity.map((d: DailyActivity) => d.count), 1)
                return activity.map((d: DailyActivity, i: number) => {
                  const height = Math.max(4, (d.count / maxCount) * 32)
                  const isToday = i === activity.length - 1
                  return (
                    <div key={i} className="group relative flex-1 flex flex-col items-center">
                      <div className="absolute bottom-full mb-1 hidden group-hover:block z-50">
                        <div className="px-2 py-1 rounded-lg text-[9px] whitespace-nowrap font-medium"
                          style={themeMode === 'light'
                            ? { background: '#1e293b', color: '#f1f5f9' }
                            : { background: 'rgba(0,0,0,0.9)', color: '#f1f5f9' }
                          }>
                          {new Date(d.date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })} — {d.count} articles
                        </div>
                      </div>
                      <div
                        className="w-full rounded-sm transition-all duration-200 cursor-pointer hover:opacity-80"
                        style={{
                          height: `${height}px`,
                          minWidth: '3px',
                          background: isToday
                            ? '#6366f1'
                            : d.count > maxCount * 0.7
                              ? (themeMode === 'light' ? '#f59e0b' : '#fbbf24')
                              : d.count > maxCount * 0.3
                                ? (themeMode === 'light' ? '#6366f1' : '#818cf8')
                                : (themeMode === 'light' ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.15)'),
                          opacity: isToday ? 1 : 0.7,
                        }}
                      />
                    </div>
                  )
                })
              })()}
            </div>
          </div>
        )}
        </div>{/* fin pointer-events-none wrapper */}
      </div>{/* fin zone carte */}
    </div>
  )
}
