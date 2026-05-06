'use client';

import React, { useState, useMemo } from 'react';
import { GUADELOUPE_COMMUNE_PATHS } from './GuadeloupeMap';

/* ────────────────────────────────────────────────────────────
   Carte choropleth de présence d'élus.
   Réutilise les paths SVG de GuadeloupeMap, avec une échelle
   bleue (intensité de présence) plutôt que rouge (gravité).
   ──────────────────────────────────────────────────────────── */

interface PresenceData {
  count: number;
  topEntities?: { entity: string; count: number }[];
  lastSeen?: string | null;
}

interface PresenceMapProps {
  data?: Record<string, PresenceData>;
  onCommuneClick?: (communeName: string) => void;
}

// 5 paliers d'intensité, échelle bleue
const getIntensityFill = (ratio: number): string => {
  if (ratio >= 0.75) return 'rgba(30,64,175,0.78)';
  if (ratio >= 0.5)  return 'rgba(37,99,235,0.6)';
  if (ratio >= 0.25) return 'rgba(59,130,246,0.42)';
  if (ratio > 0)     return 'rgba(96,165,250,0.28)';
  return 'rgba(37,99,235,0.07)';
};
const getIntensityStroke = (ratio: number): string => {
  if (ratio >= 0.75) return '#1e40af';
  if (ratio >= 0.5)  return '#2563eb';
  if (ratio >= 0.25) return '#3b82f6';
  if (ratio > 0)     return '#60a5fa';
  return 'rgba(37,99,235,0.18)';
};

export default function PresenceMap({ data = {}, onCommuneClick }: PresenceMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const maxCount = useMemo(
    () => Math.max(1, ...Object.values(data).map(d => d.count || 0)),
    [data]
  );

  const hoveredData = useMemo(
    () => (hovered ? data[hovered] || null : null),
    [hovered, data]
  );

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  return (
    <div className="relative w-full" onMouseMove={handleMouseMove}>
      <svg viewBox="0 0 340 280" className="w-full h-auto rounded-xl" style={{ background: 'transparent' }}>
        <defs>
          <radialGradient id="presence-ocean" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stopColor="rgba(37,99,235,0.05)" />
            <stop offset="100%" stopColor="rgba(15,23,42,0)" />
          </radialGradient>
          <filter id="presence-glow">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect x="0" y="0" width="340" height="280" fill="url(#presence-ocean)" />

        {/* Rivière Salée */}
        <path
          d="M134,50 C136,58 138,70 140,84 C142,96 140,104 138,108"
          fill="none"
          stroke="rgba(37,99,235,0.12)"
          strokeWidth="1.5"
          strokeDasharray="3,3"
        />

        {/* Communes */}
        {GUADELOUPE_COMMUNE_PATHS.map(c => {
          const d = data[c.name];
          const count = d?.count || 0;
          const ratio = maxCount > 0 ? count / maxCount : 0;
          const isHovered = hovered === c.name;

          return (
            <path
              key={c.name}
              d={c.d}
              fill={getIntensityFill(ratio)}
              stroke={isHovered ? '#fff' : getIntensityStroke(ratio)}
              strokeWidth={isHovered ? 1.6 : 0.6}
              strokeLinejoin="round"
              opacity={isHovered ? 1 : 0.9}
              style={{
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                filter: isHovered && count > 0 ? 'url(#presence-glow)' : 'none',
              }}
              onMouseEnter={() => setHovered(c.name)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onCommuneClick?.(c.name)}
            />
          );
        })}

        {/* Légende */}
        <g transform="translate(10, 258)">
          <rect x="0" y="0" width="320" height="16" rx="3" fill="rgba(15,23,42,0.7)" stroke="rgba(37,99,235,0.12)" strokeWidth="0.5" />
          <circle cx="16" cy="9" r="3.5" fill="rgba(96,165,250,0.5)" stroke="#60a5fa" strokeWidth="0.5" />
          <text x="24" y="12" fill="rgba(255,255,255,0.5)" fontSize="6.5" fontFamily="system-ui">Faible</text>
          <circle cx="76" cy="9" r="3.5" fill="rgba(59,130,246,0.6)" stroke="#3b82f6" strokeWidth="0.5" />
          <text x="84" y="12" fill="rgba(255,255,255,0.5)" fontSize="6.5" fontFamily="system-ui">Modérée</text>
          <circle cx="146" cy="9" r="3.5" fill="rgba(37,99,235,0.7)" stroke="#2563eb" strokeWidth="0.5" />
          <text x="154" y="12" fill="rgba(255,255,255,0.5)" fontSize="6.5" fontFamily="system-ui">Forte</text>
          <circle cx="206" cy="9" r="3.5" fill="rgba(30,64,175,0.85)" stroke="#1e40af" strokeWidth="0.5" />
          <text x="214" y="12" fill="rgba(255,255,255,0.5)" fontSize="6.5" fontFamily="system-ui">Très forte</text>
          <text x="280" y="12" fill="rgba(255,255,255,0.4)" fontSize="6" fontFamily="system-ui" fontStyle="italic">Présences relatives</text>
        </g>
      </svg>

      {/* Tooltip */}
      {hovered && (
        <div
          className="pointer-events-none absolute z-10 bg-gray-950/95 border border-gray-700 rounded-lg p-2 text-xs"
          style={{ left: tooltipPos.x + 14, top: tooltipPos.y + 14, minWidth: 180 }}
        >
          <div className="font-semibold text-white">{hovered}</div>
          {hoveredData && hoveredData.count > 0 ? (
            <>
              <div className="text-blue-300 mt-1">
                {hoveredData.count} présence{hoveredData.count > 1 ? 's' : ''}
              </div>
              {hoveredData.topEntities && hoveredData.topEntities.length > 0 && (
                <div className="text-gray-400 mt-1 leading-snug">
                  {hoveredData.topEntities.slice(0, 3).map(e => `${e.entity} (${e.count})`).join(' · ')}
                </div>
              )}
              {hoveredData.lastSeen && (
                <div className="text-gray-500 mt-1">Dernière : {hoveredData.lastSeen}</div>
              )}
            </>
          ) : (
            <div className="text-gray-500 mt-1">Aucune présence enregistrée</div>
          )}
        </div>
      )}
    </div>
  );
}
