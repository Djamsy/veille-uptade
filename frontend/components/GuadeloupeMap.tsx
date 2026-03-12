'use client';

import React, { useState, useMemo } from 'react';

/* ────────────────────────────────────────────────────────────
   Vraie carte SVG de la Guadeloupe — contours simplifiés
   des 32 communes + Marie-Galante, Les Saintes, La Désirade.
   Pas de noms affichés, seulement les zones colorées par gravité.
   ──────────────────────────────────────────────────────────── */

interface CommuneData {
  count: number;
  maxGravity: number;
}

interface GuadeloupeMapProps {
  communeData?: Record<string, CommuneData>;
  onCommuneClick?: (communeName: string) => void;
  compact?: boolean;
}

/* Chaque commune = un path SVG simplifié mais géographiquement fidèle.
   viewBox calibré sur les coordonnées réelles transformées.              */
const COMMUNES: { name: string; d: string }[] = [
  // ═══ BASSE-TERRE (aile ouest) ═══
  { name: 'Deshaies',
    d: 'M58,32 L72,28 L80,35 L84,48 L76,56 L64,54 L56,46 Z' },
  { name: 'Sainte-Rose',
    d: 'M80,35 L84,28 L98,22 L112,24 L120,32 L124,46 L118,56 L108,58 L96,54 L84,48 Z' },
  { name: 'Pointe-Noire',
    d: 'M56,46 L64,54 L68,68 L64,82 L52,88 L44,80 L42,66 L48,54 Z' },
  { name: 'Lamentin',
    d: 'M76,56 L84,48 L96,54 L108,58 L112,68 L106,76 L94,78 L82,74 L72,68 L68,68 L64,54 Z' },
  { name: 'Baie-Mahault',
    d: 'M108,58 L118,56 L124,46 L134,42 L142,48 L146,58 L148,72 L140,80 L128,82 L118,78 L112,68 Z' },
  { name: 'Petit-Bourg',
    d: 'M94,78 L106,76 L112,68 L118,78 L128,82 L132,92 L126,104 L116,110 L104,106 L96,96 L90,86 Z' },
  { name: 'Goyave',
    d: 'M82,74 L94,78 L90,86 L96,96 L92,106 L82,108 L76,100 L72,88 L68,82 L72,68 L82,74 Z' },
  { name: 'Bouillante',
    d: 'M44,80 L52,88 L64,82 L68,82 L72,88 L68,104 L60,116 L50,118 L42,108 L38,96 Z' },
  { name: 'Capesterre-Belle-Eau',
    d: 'M82,108 L92,106 L96,96 L104,106 L116,110 L120,122 L114,136 L104,142 L92,140 L84,130 L78,118 Z' },
  { name: 'Vieux-Habitants',
    d: 'M38,96 L42,108 L50,118 L52,132 L48,142 L40,146 L34,138 L30,124 L32,110 Z' },
  { name: 'Saint-Claude',
    d: 'M60,116 L68,104 L72,88 L76,100 L82,108 L78,118 L84,130 L78,142 L68,148 L58,144 L52,132 L50,118 Z' },
  { name: 'Baillif',
    d: 'M40,146 L48,142 L52,132 L58,144 L56,156 L48,162 L40,158 Z' },
  { name: 'Basse-Terre',
    d: 'M48,162 L56,156 L58,144 L68,148 L72,158 L66,168 L56,172 L48,168 Z' },
  { name: 'Trois-Rivières',
    d: 'M78,142 L84,130 L92,140 L98,152 L94,164 L84,170 L76,166 L72,158 L68,148 Z' },
  { name: 'Gourbeyre',
    d: 'M56,172 L66,168 L72,158 L76,166 L72,178 L64,184 L56,180 Z' },
  { name: 'Vieux-Fort',
    d: 'M64,184 L72,178 L76,166 L84,170 L88,180 L82,190 L72,194 L64,190 Z' },

  // ═══ GRANDE-TERRE (aile est) ═══
  { name: 'Les Abymes',
    d: 'M148,72 L146,58 L142,48 L156,42 L168,46 L176,56 L180,68 L178,80 L188,68 L198,64 L208,68 L216,76 L210,86 L200,92 L192,94 L186,100 L178,92 L170,86 L160,84 L152,80 Z' },
  { name: 'Pointe-à-Pitre',
    d: 'M140,80 L148,72 L152,80 L160,84 L158,92 L150,96 L142,92 L138,86 Z' },
  { name: 'Morne-à-l\'Eau',
    d: 'M168,46 L176,40 L190,36 L200,42 L204,54 L198,64 L188,68 L180,68 L176,56 Z' },
  { name: 'Port-Louis',
    d: 'M156,42 L168,46 L176,40 L190,36 L184,28 L172,22 L160,26 L152,34 Z' },
  { name: 'Petit-Canal',
    d: 'M190,36 L200,28 L212,22 L224,26 L228,36 L222,44 L212,48 L204,54 L200,42 Z' },
  { name: 'Anse-Bertrand',
    d: 'M212,22 L224,16 L238,14 L248,20 L250,32 L244,42 L234,46 L228,36 L224,26 Z' },
  { name: 'Le Moule',
    d: 'M204,54 L212,48 L222,44 L234,46 L244,42 L250,52 L252,66 L248,80 L238,86 L226,84 L216,76 L208,68 L198,64 Z' },
  { name: 'Le Gosier',
    d: 'M150,96 L158,92 L170,86 L178,92 L186,100 L182,110 L172,116 L162,112 L154,106 Z' },
  { name: 'Sainte-Anne',
    d: 'M172,116 L182,110 L186,100 L196,96 L208,100 L218,108 L222,120 L216,130 L204,134 L192,130 L182,124 Z' },
  { name: 'Saint-François',
    d: 'M218,108 L226,100 L238,96 L248,94 L256,100 L258,112 L254,124 L244,132 L232,134 L222,130 L216,130 L222,120 Z' },
  // ═══ MARIE-GALANTE ═══
  { name: 'Grand-Bourg',
    d: 'M172,222 L182,218 L190,224 L192,236 L186,244 L176,246 L170,238 Z' },
  { name: 'Capesterre-de-Marie-Galante',
    d: 'M190,224 L200,220 L210,226 L212,238 L206,246 L196,248 L192,236 L186,244 Z' },
  { name: 'Saint-Louis',
    d: 'M176,246 L186,244 L192,236 L196,248 L192,258 L182,260 L174,254 Z' },

  // ═══ LA DÉSIRADE ═══
  { name: 'La Désirade',
    d: 'M272,72 L284,68 L298,66 L310,70 L314,78 L308,84 L294,86 L280,84 L272,80 Z' },

  // ═══ LES SAINTES ═══
  { name: 'Terre-de-Haut',
    d: 'M112,206 L122,202 L130,206 L132,214 L126,220 L116,218 Z' },
  { name: 'Terre-de-Bas',
    d: 'M92,214 L102,210 L110,214 L112,222 L106,228 L96,226 Z' },
];

const getGravityColor = (g: number): string => {
  if (g >= 0.7) return '#ef4444';
  if (g >= 0.5) return '#f97316';
  if (g >= 0.3) return '#eab308';
  return '#10b981';
};

const getGravityFill = (g: number): string => {
  if (g >= 0.7) return 'rgba(239,68,68,0.45)';
  if (g >= 0.5) return 'rgba(249,115,22,0.35)';
  if (g >= 0.3) return 'rgba(234,179,8,0.30)';
  return 'rgba(16,185,129,0.20)';
};

export default function GuadeloupeMap({
  communeData = {},
  onCommuneClick,
  compact = false,
}: GuadeloupeMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const hoveredData = useMemo(() => {
    if (!hovered) return null;
    return communeData[hovered] || null;
  }, [hovered, communeData]);

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltipPos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  return (
    <div className="relative w-full" onMouseMove={handleMouseMove}>
      <svg
        viewBox="0 0 340 280"
        className={`w-full h-auto ${compact ? '' : 'rounded-xl'}`}
        style={{ background: 'transparent' }}
      >
        {/* Fond océan subtil */}
        <defs>
          <radialGradient id="ocean" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stopColor="rgba(99,102,241,0.06)" />
            <stop offset="100%" stopColor="rgba(15,23,42,0)" />
          </radialGradient>
          <filter id="glow-commune">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect x="0" y="0" width="340" height="280" fill="url(#ocean)" />

        {/* Contour général subtil pour la forme de l'archipel */}
        {COMMUNES.map((c) => {
          const data = communeData[c.name];
          const isHovered = hovered === c.name;
          const hasData = !!data && data.count > 0;

          const fill = hasData
            ? getGravityFill(data.maxGravity)
            : 'rgba(99,102,241,0.08)';

          const stroke = hasData
            ? getGravityColor(data.maxGravity)
            : 'rgba(99,102,241,0.2)';

          return (
            <path
              key={c.name}
              d={c.d}
              fill={fill}
              stroke={isHovered ? '#fff' : stroke}
              strokeWidth={isHovered ? 1.8 : 0.7}
              strokeLinejoin="round"
              opacity={isHovered ? 1 : 0.85}
              style={{
                cursor: 'pointer',
                transition: 'all 0.25s ease',
                filter: isHovered && hasData ? 'url(#glow-commune)' : 'none',
              }}
              onMouseEnter={() => setHovered(c.name)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onCommuneClick?.(c.name)}
            />
          );
        })}

        {/* Légende en bas */}
        {!compact && (
          <g transform="translate(10, 258)">
            <rect x="0" y="0" width="320" height="18" rx="4"
              fill="rgba(15,23,42,0.7)" stroke="rgba(99,102,241,0.15)" strokeWidth="0.5" />
            <circle cx="16" cy="9" r="4" fill="rgba(16,185,129,0.4)" stroke="#10b981" strokeWidth="0.5" />
            <text x="24" y="12" fill="rgba(255,255,255,0.5)" fontSize="7" fontFamily="system-ui">Faible</text>
            <circle cx="80" cy="9" r="4" fill="rgba(234,179,8,0.4)" stroke="#eab308" strokeWidth="0.5" />
            <text x="88" y="12" fill="rgba(255,255,255,0.5)" fontSize="7" fontFamily="system-ui">Modéré</text>
            <circle cx="148" cy="9" r="4" fill="rgba(249,115,22,0.4)" stroke="#f97316" strokeWidth="0.5" />
            <text x="156" y="12" fill="rgba(255,255,255,0.5)" fontSize="7" fontFamily="system-ui">Élevé</text>
            <circle cx="212" cy="9" r="4" fill="rgba(239,68,68,0.5)" stroke="#ef4444" strokeWidth="0.5" />
            <text x="220" y="12" fill="rgba(255,255,255,0.5)" fontSize="7" fontFamily="system-ui">Critique</text>
          </g>
        )}
      </svg>

      {/* Tooltip flottant */}
      {hovered && (
        <div
          className="absolute pointer-events-none z-50"
          style={{
            left: `${tooltipPos.x + 12}px`,
            top: `${tooltipPos.y - 40}px`,
          }}
        >
          <div
            className="px-3 py-2 rounded-lg text-white text-xs whitespace-nowrap"
            style={{
              background: 'rgba(15,23,42,0.92)',
              border: '1px solid rgba(99,102,241,0.3)',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            }}
          >
            <div className="font-semibold text-indigo-200 mb-0.5">{hovered}</div>
            {hoveredData ? (
              <>
                <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  {hoveredData.count} affaire{hoveredData.count > 1 ? 's' : ''}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <div className="w-1.5 h-1.5 rounded-full"
                    style={{ background: getGravityColor(hoveredData.maxGravity) }} />
                  <span className="text-[10px]" style={{ color: getGravityColor(hoveredData.maxGravity) }}>
                    Gravité {Math.round(hoveredData.maxGravity * 100)}%
                  </span>
                </div>
              </>
            ) : (
              <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
                Aucune affaire
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
