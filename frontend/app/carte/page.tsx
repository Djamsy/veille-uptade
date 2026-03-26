'use client';

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { fetchMapData, type MapResponse, type MapCommuneData } from '../../lib/api';

/* ════════════════════════════════════════════════════════════
   PAGE CARTE 3D SATELLITE — Veille Média Guadeloupe
   Mapbox GL JS — style satellite-streets, pitch 60°, bearing
   Communes en GeoJSON markers avec popups flottants
   ════════════════════════════════════════════════════════════ */

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || '';

// Coordonnées des communes de Guadeloupe
const COMMUNE_COORDS: Record<string, [number, number]> = {
  'Pointe-à-Pitre': [-61.5339, 16.2411],
  'Les Abymes': [-61.5028, 16.2706],
  'Baie-Mahault': [-61.5917, 16.2678],
  'Le Moule': [-61.3469, 16.3339],
  'Sainte-Anne': [-61.3833, 16.2267],
  'Saint-François': [-61.2753, 16.2536],
  'Le Gosier': [-61.4936, 16.2133],
  'Petit-Bourg': [-61.5897, 16.1933],
  'Capesterre-Belle-Eau': [-61.5667, 16.0500],
  'Sainte-Rose': [-61.6972, 16.3339],
  'Deshaies': [-61.7917, 16.3078],
  'Bouillante': [-61.7719, 16.1378],
  'Goyave': [-61.5736, 16.1361],
  'Lamentin': [-61.6336, 16.2706],
  'Trois-Rivières': [-61.6333, 15.9750],
  'Vieux-Habitants': [-61.7583, 16.0583],
  'Basse-Terre': [-61.7256, 15.9978],
  'Saint-Claude': [-61.6917, 16.0167],
  'Baillif': [-61.7500, 16.0250],
  'Gourbeyre': [-61.6917, 15.9833],
  'Vieux-Fort': [-61.6917, 15.9583],
  'Pointe-Noire': [-61.7903, 16.2353],
  "Morne-à-l'Eau": [-61.4539, 16.3339],
  'Port-Louis': [-61.5278, 16.4189],
  'Petit-Canal': [-61.4853, 16.3828],
  'Anse-Bertrand': [-61.5028, 16.4731],
  'Grand-Bourg': [-61.3167, 15.8833],
  'Capesterre-de-Marie-Galante': [-61.2333, 15.8833],
  'Saint-Louis': [-61.3167, 15.9500],
  'La Désirade': [-61.0833, 16.3167],
  'Terre-de-Haut': [-61.5833, 15.8583],
  'Terre-de-Bas': [-61.6333, 15.8583],
};

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

const PRIORITY_BADGE: Record<string, { color: string; label: string }> = {
  hot: { color: '#ef4444', label: 'HOT' },
  watch: { color: '#f59e0b', label: 'WATCH' },
  minor: { color: '#6b7280', label: 'MINOR' },
};

function getGravityColor(g: number): string {
  if (g >= 0.7) return '#ef4444';
  if (g >= 0.5) return '#f97316';
  if (g >= 0.3) return '#eab308';
  return '#10b981';
}

export default function CartePage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);

  const [mapData, setMapData] = useState<MapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [selectedCommune, setSelectedCommune] = useState<string | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  // Mode jour/nuit automatique (6h-18h heure Guadeloupe = UTC-4)
  const isDay = useMemo(() => {
    const now = new Date();
    // Heure Guadeloupe = UTC - 4
    const gpeHour = (now.getUTCHours() - 4 + 24) % 24;
    return gpeHour >= 6 && gpeHour < 18;
  }, []);

  // Load map data
  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchMapData(days)
      .then(setMapData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [days]);

  // Initialize Mapbox GL via CDN script
  useEffect(() => {
    if (typeof window === 'undefined') return;

    // Check if already loaded
    if ((window as any).mapboxgl) {
      initMap();
      return;
    }

    // Load CSS
    const cssLink = document.createElement('link');
    cssLink.rel = 'stylesheet';
    cssLink.href = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.css';
    document.head.appendChild(cssLink);

    // Load JS
    const script = document.createElement('script');
    script.src = 'https://api.mapbox.com/mapbox-gl-js/v3.9.0/mapbox-gl.js';
    script.onload = () => initMap();
    document.head.appendChild(script);

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  const initMap = useCallback(() => {
    if (!mapContainer.current || mapRef.current) return;
    const mapboxgl = (window as any).mapboxgl;
    if (!mapboxgl) return;

    mapboxgl.accessToken = MAPBOX_TOKEN;

    // Style jour/nuit automatique
    const mapStyle = isDay
      ? 'mapbox://styles/mapbox/outdoors-v12'
      : 'mapbox://styles/mapbox/satellite-streets-v12';

    const map = new mapboxgl.Map({
      container: mapContainer.current,
      style: mapStyle,
      center: [-61.55, 16.20],
      zoom: 9.8,
      pitch: 55,
      bearing: -15,
      antialias: true,
      attributionControl: false,
    });

    map.addControl(new mapboxgl.NavigationControl({ showCompass: true }), 'top-right');
    map.addControl(new mapboxgl.ScaleControl({ maxWidth: 120 }), 'bottom-left');

    map.on('load', () => {
      // Add 3D terrain
      map.addSource('mapbox-dem', {
        type: 'raster-dem',
        url: 'mapbox://mapbox.mapbox-terrain-dem-v1',
        tileSize: 512,
        maxzoom: 14,
      });
      map.setTerrain({ source: 'mapbox-dem', exaggeration: 1.8 });

      // Add sky atmosphere
      map.addLayer({
        id: 'sky',
        type: 'sky',
        paint: {
          'sky-type': 'atmosphere',
          'sky-atmosphere-sun': [0.0, 0.0],
          'sky-atmosphere-sun-intensity': 15,
        },
      });

      setMapReady(true);
    });

    mapRef.current = map;
  }, []);

  // Update markers when data changes
  useEffect(() => {
    if (!mapReady || !mapData || !mapRef.current) return;
    const mapboxgl = (window as any).mapboxgl;
    if (!mapboxgl) return;

    // Remove old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    const map = mapRef.current;

    for (const [communeName, data] of Object.entries(mapData.communes)) {
      const coords = COMMUNE_COORDS[communeName];
      if (!coords) continue;

      const stats = data.stats;
      const gravityColor = getGravityColor(stats.max_gravity);
      const size = Math.min(48, Math.max(20, 14 + stats.total_items * 2));

      // Create custom marker element
      const el = document.createElement('div');
      el.className = 'map-commune-marker';
      el.style.cssText = `
        width: ${size}px; height: ${size}px;
        background: radial-gradient(circle, ${gravityColor}cc 0%, ${gravityColor}44 70%, transparent 100%);
        border: 2px solid ${gravityColor};
        border-radius: 50%;
        cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        font-size: 10px; font-weight: 700; color: #fff;
        text-shadow: 0 1px 3px rgba(0,0,0,0.8);
        box-shadow: 0 0 ${size/2}px ${gravityColor}66;
        transition: transform 0.2s, box-shadow 0.2s;
      `;
      el.textContent = String(stats.total_items);
      el.title = communeName;

      el.addEventListener('mouseenter', () => {
        el.style.transform = 'scale(1.3)';
        el.style.boxShadow = `0 0 ${size}px ${gravityColor}`;
        el.style.zIndex = '10';
      });
      el.addEventListener('mouseleave', () => {
        el.style.transform = 'scale(1)';
        el.style.boxShadow = `0 0 ${size/2}px ${gravityColor}66`;
        el.style.zIndex = '1';
      });
      el.addEventListener('click', () => {
        setSelectedCommune(communeName);
        map.flyTo({
          center: coords,
          zoom: 12,
          pitch: 60,
          bearing: map.getBearing(),
          duration: 1500,
        });
      });

      // Popup on hover — inclut les affaires de la commune
      const affairsHtml = data.affairs.length > 0
        ? `<div style="margin-top:6px;padding-top:5px;border-top:1px solid rgba(255,255,255,0.1);">
            <div style="font-size:9px;color:rgba(255,255,255,0.4);text-transform:uppercase;margin-bottom:3px;">Affaires</div>
            ${data.affairs.slice(0, 3).map((aff: any) => {
              const pColor = aff.priority === 'hot' ? '#ef4444' : aff.priority === 'watch' ? '#f59e0b' : '#6b7280';
              return `<div style="font-size:10px;color:rgba(255,255,255,0.75);margin-bottom:2px;display:flex;align-items:center;gap:4px;">
                <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:${pColor};flex-shrink:0;"></span>
                ${(aff.title || '').substring(0, 50)}${(aff.title || '').length > 50 ? '…' : ''}
              </div>`;
            }).join('')}
            ${data.affairs.length > 3 ? `<div style="font-size:9px;color:rgba(255,255,255,0.3);margin-top:2px;">+${data.affairs.length - 3} autres</div>` : ''}
          </div>`
        : '';

      const popup = new mapboxgl.Popup({
        offset: [0, -size / 2 - 5],
        closeButton: false,
        closeOnClick: false,
        className: 'map-commune-popup',
      }).setHTML(`
        <div style="background:rgba(15,23,42,0.95);border:1px solid ${gravityColor}44;border-radius:10px;padding:8px 12px;color:#fff;font-family:system-ui;min-width:160px;max-width:250px;">
          <div style="font-weight:700;font-size:13px;margin-bottom:4px;color:${gravityColor}">${communeName}</div>
          <div style="font-size:10px;color:rgba(255,255,255,0.5);display:flex;gap:8px;">
            <span>${stats.article_count} art.</span>
            <span>${stats.transcription_count} radio</span>
            <span>${stats.affair_count} aff.</span>
          </div>
          <div style="font-size:10px;margin-top:3px;color:${gravityColor}">
            Gravité max: ${Math.round(stats.max_gravity * 100)}%
          </div>
          ${affairsHtml}
        </div>
      `);

      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat(coords)
        .setPopup(popup)
        .addTo(map);

      // Show popup on hover
      el.addEventListener('mouseenter', () => marker.togglePopup());
      el.addEventListener('mouseleave', () => {
        if (marker.getPopup().isOpen()) marker.togglePopup();
      });

      markersRef.current.push(marker);
    }
  }, [mapReady, mapData]);

  // Selected commune data
  const selectedData: MapCommuneData | null = useMemo(() => {
    if (!selectedCommune || !mapData) return null;
    return mapData.communes[selectedCommune] || null;
  }, [selectedCommune, mapData]);

  // Global stats
  const globalStats = useMemo(() => {
    if (!mapData) return { communes: 0, articles: 0, transcriptions: 0, affairs: 0 };
    let articles = 0, transcriptions = 0, affairs = 0;
    for (const data of Object.values(mapData.communes)) {
      articles += data.stats.article_count;
      transcriptions += data.stats.transcription_count;
      affairs += data.stats.affair_count;
    }
    return { communes: mapData.total_communes_active, articles, transcriptions, affairs };
  }, [mapData]);

  // Top communes
  const topCommunes = useMemo(() => {
    if (!mapData) return [];
    return Object.entries(mapData.communes)
      .map(([name, data]) => ({ name, ...data.stats }))
      .sort((a, b) => b.total_items - a.total_items)
      .slice(0, 8);
  }, [mapData]);

  const handleResetView = () => {
    setSelectedCommune(null);
    mapRef.current?.flyTo({
      center: [-61.55, 16.20],
      zoom: 9.8,
      pitch: 55,
      bearing: -15,
      duration: 1500,
    });
  };

  return (
    <main className="h-screen w-full relative overflow-hidden" style={{ background: isDay ? '#e8edf5' : '#060a13' }}>
      {/* ═══ FULLSCREEN MAP ═══ */}
      <div ref={mapContainer} className="absolute inset-0 z-0" />

      {/* Overlay gradient top */}
      <div className="absolute top-0 left-0 right-0 h-24 z-10 pointer-events-none"
        style={{ background: isDay
          ? 'linear-gradient(to bottom, rgba(232,237,245,0.8) 0%, transparent 100%)'
          : 'linear-gradient(to bottom, rgba(6,10,19,0.8) 0%, transparent 100%)'
        }} />

      {/* ═══ FLOATING HEADER ═══ */}
      <div className="absolute top-3 left-3 right-3 z-20 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className={`text-lg font-bold flex items-center gap-2 ${isDay ? 'text-slate-800' : 'text-white'}`}
            style={{ textShadow: isDay ? '0 1px 3px rgba(255,255,255,0.5)' : '0 2px 8px rgba(0,0,0,0.8)' }}>
            <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
            </svg>
            Carte Média
          </h1>
          {/* Period selector */}
          <div className="flex gap-1">
            {[3, 7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => { setDays(d); setSelectedCommune(null); }}
                className={`px-2.5 py-1 text-[10px] rounded-full transition-all backdrop-blur-md ${
                  days === d
                    ? 'bg-indigo-500/40 text-white border border-indigo-400/40'
                    : isDay
                      ? 'bg-white/60 text-slate-700 border border-slate-200 hover:bg-white/80'
                      : 'bg-black/30 text-white/60 border border-white/10 hover:bg-white/10'
                }`}
              >
                {d}j
              </button>
            ))}
          </div>
        </div>
        <button onClick={handleResetView}
          className={`px-3 py-1.5 text-[10px] rounded-full backdrop-blur-md transition-all ${
            isDay
              ? 'bg-white/60 text-slate-600 border border-slate-200 hover:bg-white/80'
              : 'bg-black/40 text-white/60 border border-white/10 hover:bg-white/10'
          }`}>
          Vue globale
        </button>
      </div>

      {/* ═══ FLOATING KPI BAR (bottom left) ═══ */}
      <div className="absolute bottom-16 sm:bottom-4 left-3 z-20 flex gap-1.5 sm:gap-2 flex-wrap">
        {[
          { label: 'Communes', value: globalStats.communes, color: '#6366f1' },
          { label: 'Articles', value: globalStats.articles, color: '#f59e0b' },
          { label: 'Radios', value: globalStats.transcriptions, color: '#06b6d4' },
          { label: 'Affaires', value: globalStats.affairs, color: '#8b5cf6' },
        ].map((kpi) => (
          <div key={kpi.label}
            className="px-2 sm:px-3 py-1.5 sm:py-2 rounded-xl backdrop-blur-md"
            style={{
              background: isDay ? 'rgba(255,255,255,0.8)' : 'rgba(6,10,19,0.75)',
              border: `1px solid ${kpi.color}33`,
            }}>
            <div className="text-sm sm:text-lg font-bold" style={{ color: kpi.color }}>{kpi.value}</div>
            <div className={`text-[9px] uppercase tracking-wider ${isDay ? 'text-slate-500' : 'text-white/40'}`}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* ═══ FLOATING LEFT PANEL — Top communes ═══ */}
      <div className="absolute top-16 left-3 z-20 w-44 sm:w-52 hidden sm:block">
        <div className="rounded-xl backdrop-blur-md p-3"
          style={{ background: isDay ? 'rgba(255,255,255,0.85)' : 'rgba(6,10,19,0.8)', border: '1px solid rgba(99,102,241,0.15)' }}>
          <h3 className={`text-[10px] font-semibold uppercase tracking-wider mb-2 ${isDay ? 'text-slate-500' : 'text-white/50'}`}>
            Top communes
          </h3>
          <div className="space-y-1">
            {topCommunes.map((c, i) => (
              <button key={c.name}
                onClick={() => {
                  setSelectedCommune(c.name);
                  const coords = COMMUNE_COORDS[c.name];
                  if (coords && mapRef.current) {
                    mapRef.current.flyTo({ center: coords, zoom: 12, pitch: 60, duration: 1500 });
                  }
                }}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition-all ${
                  selectedCommune === c.name
                    ? 'bg-indigo-500/25 border border-indigo-500/30'
                    : 'hover:bg-white/5 border border-transparent'
                }`}>
                <span className={`text-[10px] font-mono w-3 ${isDay ? 'text-slate-400' : 'text-white/25'}`}>{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className={`text-[11px] font-medium truncate ${isDay ? 'text-slate-700' : 'text-white/80'}`}>{c.name}</div>
                  <div className={`text-[9px] ${isDay ? 'text-slate-400' : 'text-white/30'}`}>
                    {c.article_count} art · {c.transcription_count} radio
                  </div>
                </div>
                <div className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: getGravityColor(c.max_gravity) }} />
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ═══ FLOATING RIGHT PANEL — Détail commune ═══ */}
      {selectedData && selectedCommune && (
        <div className="absolute top-16 sm:top-16 bottom-16 sm:bottom-auto right-0 sm:right-3 left-0 sm:left-auto z-20 w-full sm:w-80 max-h-[50vh] sm:max-h-[calc(100vh-120px)] overflow-y-auto"
          style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.1) transparent' }}>
          <div className="rounded-xl backdrop-blur-md overflow-hidden"
            style={{ background: isDay ? 'rgba(255,255,255,0.9)' : 'rgba(6,10,19,0.85)', border: '1px solid rgba(99,102,241,0.15)' }}>

            {/* Header */}
            <div className="p-4" style={{
              background: `linear-gradient(135deg, ${getGravityColor(selectedData.stats.max_gravity)}22 0%, transparent 100%)`,
              borderBottom: `1px solid ${getGravityColor(selectedData.stats.max_gravity)}33`,
            }}>
              <div className="flex items-center justify-between">
                <h2 className={`text-base font-bold ${isDay ? 'text-slate-800' : 'text-white'}`}>{selectedCommune}</h2>
                <button onClick={() => { setSelectedCommune(null); handleResetView(); }}
                  className="text-white/30 hover:text-white/60 transition-colors p-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="flex gap-4 mt-2">
                {[
                  { v: selectedData.stats.article_count, l: 'Articles', c: '#f59e0b' },
                  { v: selectedData.stats.transcription_count, l: 'Radios', c: '#06b6d4' },
                  { v: selectedData.stats.affair_count, l: 'Affaires', c: '#8b5cf6' },
                ].map((s) => (
                  <div key={s.l} className="text-center">
                    <div className="text-sm font-bold" style={{ color: s.c }}>{s.v}</div>
                    <div className="text-[8px] text-white/30 uppercase">{s.l}</div>
                  </div>
                ))}
                <div className="text-center">
                  <div className="text-sm font-bold" style={{ color: getGravityColor(selectedData.stats.max_gravity) }}>
                    {Math.round(selectedData.stats.max_gravity * 100)}%
                  </div>
                  <div className="text-[8px] text-white/30 uppercase">Gravité</div>
                </div>
              </div>
            </div>

            {/* Affaires */}
            {selectedData.affairs.length > 0 && (
              <div className="p-3 border-b border-white/5">
                <h3 className="text-[10px] font-semibold text-violet-300 uppercase tracking-wider mb-2">
                  Affaires ({selectedData.affairs.length})
                </h3>
                <div className="space-y-1.5">
                  {selectedData.affairs.map((aff, i) => {
                    const badge = PRIORITY_BADGE[aff.priority || 'minor'];
                    return (
                      <a key={aff.id || i} href={`/affairs/${aff.id}`}
                        className="block p-2 rounded-lg hover:bg-white/5 transition-colors">
                        <div className="flex items-start gap-2">
                          <span className="text-[8px] font-bold px-1 py-0.5 rounded uppercase flex-shrink-0 mt-0.5"
                            style={{ background: `${badge.color}22`, color: badge.color, border: `1px solid ${badge.color}44` }}>
                            {badge.label}
                          </span>
                          <div className="min-w-0">
                            <div className="text-[11px] text-white/80 font-medium leading-tight">{aff.title}</div>
                            <div className="text-[9px] text-white/30 mt-0.5">
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
              <div className="p-3 border-b border-white/5">
                <h3 className="text-[10px] font-semibold text-amber-300 uppercase tracking-wider mb-2">
                  Articles ({selectedData.articles.length})
                </h3>
                <div className="space-y-1">
                  {selectedData.articles.slice(0, 12).map((art, i) => (
                    <div key={art.id || i} className="flex items-start gap-2 py-1">
                      <div className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                        style={{ background: THEME_COLORS[art.theme || 'general'] || '#6b7280' }} />
                      <div className="min-w-0">
                        <div className="text-[10px] text-white/70 leading-tight">{art.title}</div>
                        <div className="text-[8px] text-white/25 mt-0.5">{art.source}</div>
                      </div>
                    </div>
                  ))}
                  {selectedData.articles.length > 12 && (
                    <div className="text-[9px] text-white/20 text-center mt-1">
                      +{selectedData.articles.length - 12} autres articles
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Radio */}
            {selectedData.transcriptions.length > 0 && (
              <div className="p-3">
                <h3 className="text-[10px] font-semibold text-cyan-300 uppercase tracking-wider mb-2">
                  Radio ({selectedData.transcriptions.length})
                </h3>
                <div className="space-y-1">
                  {selectedData.transcriptions.slice(0, 8).map((t, i) => (
                    <div key={i} className="py-1">
                      <div className="text-[10px] text-white/70 leading-tight">{t.title}</div>
                      <div className="text-[8px] text-white/25 mt-0.5">{t.station}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#060a13]/80 backdrop-blur-sm">
          <div className="text-center">
            <div className="w-12 h-12 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin mx-auto mb-3" />
            <p className="text-white/50 text-sm">Chargement des données...</p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-30 px-4 py-2 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-xs backdrop-blur-md">
          Erreur : {error}
        </div>
      )}

      {/* Mapbox popup style override */}
      <style jsx global>{`
        .mapboxgl-popup-content {
          background: transparent !important;
          padding: 0 !important;
          box-shadow: none !important;
          border-radius: 10px !important;
        }
        .mapboxgl-popup-tip {
          border-top-color: rgba(15,23,42,0.95) !important;
        }
        .mapboxgl-popup-close-button {
          display: none !important;
        }
        .mapboxgl-ctrl-group {
          background: rgba(6,10,19,0.8) !important;
          border: 1px solid rgba(99,102,241,0.15) !important;
          border-radius: 12px !important;
          backdrop-filter: blur(8px);
        }
        .mapboxgl-ctrl-group button {
          border: none !important;
        }
        .mapboxgl-ctrl-group button + button {
          border-top: 1px solid rgba(255,255,255,0.08) !important;
        }
        .mapboxgl-ctrl-group button span {
          filter: invert(1) !important;
        }
        .mapboxgl-ctrl-scale {
          background: rgba(6,10,19,0.7) !important;
          color: rgba(255,255,255,0.5) !important;
          border-color: rgba(255,255,255,0.15) !important;
          border-radius: 6px !important;
          font-size: 9px !important;
          backdrop-filter: blur(4px);
        }
      `}</style>
    </main>
  );
}
