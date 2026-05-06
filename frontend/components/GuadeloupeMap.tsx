'use client';

import React, { useState, useMemo } from 'react';

/* ────────────────────────────────────────────────────────────
   Carte SVG réaliste de la Guadeloupe
   Contours en courbes de Bézier, fidèles à la géographie.
   Pas de noms, seulement les zones colorées par gravité.
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

/* Paths Bézier — positionnement calibré sur la forme papillon.
   Basse-Terre = aile ouest (volcan, montagnes, plus allongée N-S)
   Grande-Terre = aile est (plate, plus large E-O)
   Séparées par la Rivière Salée au centre (~x=130-140)            */
export const GUADELOUPE_COMMUNE_PATHS: { name: string; d: string }[] = [
  // ═══ BASSE-TERRE (aile ouest — du nord au sud) ═══
  { name: 'Deshaies',
    d: 'M52,38 C56,32 64,28 72,30 C78,32 82,36 84,42 C86,48 82,54 76,56 C70,58 62,56 58,52 C54,48 50,44 52,38 Z' },
  { name: 'Sainte-Rose',
    d: 'M76,56 C82,54 86,48 84,42 C88,34 96,26 108,24 C116,23 122,28 126,36 C128,42 126,50 122,56 C116,60 108,60 100,58 C92,56 84,56 76,56 Z' },
  { name: 'Pointe-Noire',
    d: 'M52,52 C58,52 62,56 64,62 C66,70 64,78 60,84 C56,88 50,90 44,86 C40,82 38,74 40,66 C42,58 46,52 52,52 Z' },
  { name: 'Lamentin',
    d: 'M76,56 C84,56 92,56 100,58 C108,60 114,62 116,68 C118,74 112,78 104,80 C96,82 88,80 80,76 C74,72 68,68 66,62 C64,56 70,56 76,56 Z' },
  { name: 'Baie-Mahault',
    d: 'M116,68 C114,62 118,58 122,56 C128,52 134,48 140,50 C146,52 148,58 150,66 C152,74 148,80 142,84 C136,86 128,84 122,80 C118,76 116,72 116,68 Z' },
  { name: 'Petit-Bourg',
    d: 'M104,80 C112,78 118,76 122,80 C128,84 134,90 134,98 C134,106 128,112 120,116 C112,118 106,114 100,108 C96,102 92,94 92,88 C92,82 96,80 104,80 Z' },
  { name: 'Goyave',
    d: 'M80,76 C88,80 92,82 92,88 C92,94 88,100 84,106 C80,110 76,112 72,108 C68,104 66,96 64,88 C62,82 60,84 60,84 C62,78 72,74 80,76 Z' },
  { name: 'Bouillante',
    d: 'M44,86 C50,90 56,88 60,84 C62,82 64,88 66,96 C68,104 66,112 62,118 C58,124 52,126 46,122 C40,118 36,110 34,102 C32,94 36,88 44,86 Z' },
  { name: 'Capesterre-Belle-Eau',
    d: 'M84,106 C88,100 96,102 100,108 C106,114 114,120 118,128 C120,136 116,142 110,146 C104,150 96,148 90,144 C84,140 80,132 78,124 C76,116 80,112 84,106 Z' },
  { name: 'Vieux-Habitants',
    d: 'M34,102 C36,110 40,118 46,122 C50,126 52,132 50,140 C48,146 44,150 38,150 C34,150 30,144 28,136 C26,128 28,118 30,110 C32,106 34,102 34,102 Z' },
  { name: 'Saint-Claude',
    d: 'M62,118 C66,112 68,104 72,108 C76,112 78,118 78,124 C80,132 82,138 78,146 C74,152 68,156 62,154 C56,152 52,146 50,140 C48,134 50,128 54,124 C58,120 62,118 62,118 Z' },
  { name: 'Baillif',
    d: 'M38,150 C44,150 48,146 50,140 C52,146 54,152 54,158 C54,164 50,168 44,168 C40,168 36,164 34,158 C32,152 34,150 38,150 Z' },
  { name: 'Basse-Terre',
    d: 'M44,168 C50,168 54,164 54,158 C56,152 60,150 62,154 C66,158 68,164 66,170 C64,176 58,180 52,180 C46,180 42,176 42,172 C42,170 44,168 44,168 Z' },
  { name: 'Trois-Rivières',
    d: 'M78,146 C82,138 86,140 90,144 C96,150 100,158 98,166 C96,172 92,176 86,178 C80,180 76,176 72,170 C68,164 66,158 68,152 C70,148 74,146 78,146 Z' },
  { name: 'Gourbeyre',
    d: 'M52,180 C58,180 64,176 66,170 C68,176 70,182 68,188 C66,194 60,196 56,194 C52,192 48,188 48,184 C48,182 50,180 52,180 Z' },
  { name: 'Vieux-Fort',
    d: 'M68,188 C70,182 76,176 80,178 C86,180 90,186 88,192 C86,198 80,202 74,202 C68,202 64,198 64,194 C64,190 66,188 68,188 Z' },

  // ═══ GRANDE-TERRE (aile est) ═══
  { name: 'Les Abymes',
    d: 'M150,66 C148,58 146,52 150,48 C156,44 164,42 172,46 C178,48 182,54 184,62 C186,70 184,78 180,84 C186,78 194,68 204,66 C210,64 218,68 222,76 C218,82 210,88 202,92 C196,96 190,98 186,100 C180,96 174,90 170,86 C166,84 158,84 154,82 C150,80 150,74 150,66 Z' },
  { name: 'Pointe-à-Pitre',
    d: 'M142,84 C146,78 150,74 150,66 C150,74 150,80 154,82 C158,84 162,86 164,90 C164,94 160,98 154,100 C148,102 144,98 142,94 C140,90 140,86 142,84 Z' },
  { name: 'Morne-à-l\'Eau',
    d: 'M172,46 C178,42 186,38 196,36 C204,34 210,38 212,44 C214,50 210,58 206,62 C202,66 196,68 190,66 C186,64 182,62 184,56 C184,50 178,48 172,46 Z' },
  { name: 'Port-Louis',
    d: 'M150,48 C156,44 164,42 172,46 C178,42 186,38 196,36 C192,30 184,24 176,22 C168,20 160,24 154,30 C150,36 148,42 150,48 Z' },
  { name: 'Petit-Canal',
    d: 'M196,36 C204,28 214,22 226,24 C234,26 238,32 236,40 C234,46 228,50 222,52 C216,54 212,50 212,44 C212,38 204,34 196,36 Z' },
  { name: 'Anse-Bertrand',
    d: 'M226,24 C232,18 240,14 250,16 C258,18 262,26 260,34 C258,42 252,48 246,50 C240,50 236,46 236,40 C236,32 234,26 226,24 Z' },
  { name: 'Le Moule',
    d: 'M212,44 C216,54 222,52 228,50 C234,46 240,50 246,50 C252,48 258,46 262,52 C266,60 266,70 262,80 C258,88 250,92 242,90 C234,88 226,84 220,78 C214,72 210,66 206,62 C204,56 208,48 212,44 Z' },
  { name: 'Le Gosier',
    d: 'M154,100 C160,98 164,94 168,90 C174,90 180,96 186,100 C190,104 188,112 182,118 C176,124 168,124 162,120 C156,116 152,110 152,104 C152,102 154,100 154,100 Z' },
  { name: 'Sainte-Anne',
    d: 'M182,118 C188,112 190,104 194,100 C200,96 208,98 216,104 C224,110 230,118 232,126 C232,134 226,140 218,142 C210,144 202,140 194,134 C188,128 184,124 182,118 Z' },
  { name: 'Saint-François',
    d: 'M232,126 C230,118 224,110 226,104 C230,98 238,94 248,92 C258,92 266,98 270,106 C272,114 268,124 262,132 C256,138 248,142 240,142 C234,142 232,136 232,126 Z' },

  // ═══ MARIE-GALANTE ═══
  { name: 'Grand-Bourg',
    d: 'M178,226 C182,220 188,218 194,220 C198,222 200,228 198,234 C196,240 190,244 184,244 C178,244 174,238 174,232 C174,228 176,226 178,226 Z' },
  { name: 'Capesterre-de-Marie-Galante',
    d: 'M194,220 C200,218 208,220 214,226 C218,232 218,240 214,246 C210,250 204,252 198,250 C196,246 196,240 198,234 C200,228 198,222 194,220 Z' },
  { name: 'Saint-Louis',
    d: 'M184,244 C190,244 196,246 198,250 C200,254 198,260 192,264 C186,266 180,264 176,258 C174,252 176,246 180,244 C182,244 184,244 184,244 Z' },

  // ═══ LA DÉSIRADE ═══
  { name: 'La Désirade',
    d: 'M280,72 C288,68 298,66 308,68 C316,70 322,76 320,82 C318,88 310,90 300,90 C290,90 282,86 278,80 C276,76 278,72 280,72 Z' },

  // ═══ LES SAINTES ═══
  { name: 'Terre-de-Haut',
    d: 'M116,208 C122,204 128,204 132,208 C136,212 134,218 130,222 C126,224 120,222 116,218 C114,214 114,210 116,208 Z' },
  { name: 'Terre-de-Bas',
    d: 'M96,216 C102,212 108,212 112,216 C116,220 114,226 110,228 C106,230 100,228 96,224 C94,220 94,218 96,216 Z' },
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
  if (g >= 0.3) return 'rgba(234,179,8,0.28)';
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
        <defs>
          <radialGradient id="ocean" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stopColor="rgba(37,99,235,0.05)" />
            <stop offset="100%" stopColor="rgba(15,23,42,0)" />
          </radialGradient>
          <filter id="glow-commune">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          {/* Ombre douce pour l'archipel */}
          <filter id="island-shadow" x="-5%" y="-5%" width="110%" height="110%">
            <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="rgba(0,0,0,0.3)" />
          </filter>
        </defs>
        <rect x="0" y="0" width="340" height="280" fill="url(#ocean)" />

        {/* Rivière Salée (trait entre les deux ailes) */}
        <path d="M134,50 C136,58 138,70 140,84 C142,96 140,104 138,108"
          fill="none" stroke="rgba(37,99,235,0.12)" strokeWidth="1.5" strokeDasharray="3,3" />

        {/* Communes */}
        {GUADELOUPE_COMMUNE_PATHS.map((c) => {
          const data = communeData[c.name];
          const isHovered = hovered === c.name;
          const hasData = !!data && data.count > 0;

          const fill = hasData
            ? getGravityFill(data.maxGravity)
            : 'rgba(37,99,235,0.07)';

          const stroke = hasData
            ? getGravityColor(data.maxGravity)
            : 'rgba(37,99,235,0.18)';

          return (
            <path
              key={c.name}
              d={c.d}
              fill={fill}
              stroke={isHovered ? '#fff' : stroke}
              strokeWidth={isHovered ? 1.6 : 0.6}
              strokeLinejoin="round"
              opacity={isHovered ? 1 : 0.88}
              style={{
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                filter: isHovered && hasData ? 'url(#glow-commune)' : 'none',
              }}
              onMouseEnter={() => setHovered(c.name)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onCommuneClick?.(c.name)}
            />
          );
        })}

        {/* Légende */}
        {!compact && (
          <g transform="translate(10, 258)">
            <rect x="0" y="0" width="320" height="18" rx="4"
              fill="rgba(15,23,42,0.7)" stroke="rgba(37,99,235,0.12)" strokeWidth="0.5" />
            <circle cx="16" cy="9" r="3.5" fill="rgba(16,185,129,0.5)" stroke="#10b981" strokeWidth="0.5" />
            <text x="24" y="12" fill="rgba(255,255,255,0.45)" fontSize="6.5" fontFamily="system-ui">Faible</text>
            <circle cx="80" cy="9" r="3.5" fill="rgba(234,179,8,0.5)" stroke="#eab308" strokeWidth="0.5" />
            <text x="88" y="12" fill="rgba(255,255,255,0.45)" fontSize="6.5" fontFamily="system-ui">Modéré</text>
            <circle cx="148" cy="9" r="3.5" fill="rgba(249,115,22,0.5)" stroke="#f97316" strokeWidth="0.5" />
            <text x="156" y="12" fill="rgba(255,255,255,0.45)" fontSize="6.5" fontFamily="system-ui">Élevé</text>
            <circle cx="212" cy="9" r="3.5" fill="rgba(239,68,68,0.55)" stroke="#ef4444" strokeWidth="0.5" />
            <text x="220" y="12" fill="rgba(255,255,255,0.45)" fontSize="6.5" fontFamily="system-ui">Critique</text>
          </g>
        )}
      </svg>

      {/* Tooltip */}
      {hovered && (
        <div
          className="absolute pointer-events-none z-50"
          style={{
            left: `${tooltipPos.x + 14}px`,
            top: `${tooltipPos.y - 44}px`,
          }}
        >
          <div
            className="px-3 py-2 rounded-lg text-white text-xs whitespace-nowrap"
            style={{
              background: 'rgba(15,23,42,0.94)',
              border: '1px solid rgba(37,99,235,0.25)',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            }}
          >
            <div className="font-semibold text-indigo-200 mb-0.5">{hovered}</div>
            {hoveredData ? (
              <>
                <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.55)' }}>
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
              <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
                Aucune affaire
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
