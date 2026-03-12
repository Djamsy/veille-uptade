'use client';

import React, { useState } from 'react';

interface CommuneData {
  count: number;
  maxGravity: number;
}

interface GuadeloupeMapProps {
  communeData?: Record<string, CommuneData>;
  onCommuneClick?: (communeName: string) => void;
}

interface Commune {
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
  wing: 'basse-terre' | 'grande-terre' | 'dependency';
}

interface TooltipState {
  visible: boolean;
  commune: string;
  x: number;
  y: number;
  count: number;
  maxGravity: number;
}

const communes: Commune[] = [
  // Basse-Terre (left wing - elongated vertically)
  { name: 'Deshaies', x: 20, y: 45, width: 35, height: 25, wing: 'basse-terre' },
  { name: 'Sainte-Rose', x: 55, y: 35, width: 35, height: 25, wing: 'basse-terre' },
  { name: 'Lamentin', x: 60, y: 65, width: 30, height: 25, wing: 'basse-terre' },
  { name: 'Baie-Mahault', x: 70, y: 85, width: 30, height: 20, wing: 'basse-terre' },
  { name: 'Pointe-Noire', x: 40, y: 100, width: 30, height: 30, wing: 'basse-terre' },
  { name: 'Bouillante', x: 50, y: 140, width: 35, height: 25, wing: 'basse-terre' },
  { name: 'Vieux-Habitants', x: 50, y: 175, width: 35, height: 25, wing: 'basse-terre' },
  { name: 'Capesterre-Belle-Eau', x: 75, y: 130, width: 35, height: 30, wing: 'basse-terre' },
  { name: 'Petit-Bourg', x: 80, y: 165, width: 30, height: 25, wing: 'basse-terre' },
  { name: 'Goyave', x: 85, y: 100, width: 25, height: 20, wing: 'basse-terre' },
  { name: 'Baillif', x: 65, y: 220, width: 25, height: 25, wing: 'basse-terre' },
  { name: 'Saint-Claude', x: 85, y: 210, width: 30, height: 25, wing: 'basse-terre' },
  { name: 'Basse-Terre', x: 70, y: 250, width: 35, height: 30, wing: 'basse-terre' },
  { name: 'Gourbeyre', x: 55, y: 250, width: 30, height: 30, wing: 'basse-terre' },
  { name: 'Trois-Rivières', x: 45, y: 280, width: 30, height: 30, wing: 'basse-terre' },
  { name: 'Vieux-Fort', x: 35, y: 320, width: 35, height: 35, wing: 'basse-terre' },

  // Grande-Terre (right wing - roughly rectangular)
  { name: 'Port-Louis', x: 120, y: 45, width: 30, height: 25, wing: 'grande-terre' },
  { name: 'Petit-Canal', x: 155, y: 40, width: 35, height: 25, wing: 'grande-terre' },
  { name: 'Anse-Bertrand', x: 200, y: 35, width: 40, height: 30, wing: 'grande-terre' },
  { name: 'Morne-à-l\'Eau', x: 175, y: 75, width: 35, height: 25, wing: 'grande-terre' },
  { name: 'Le Moule', x: 210, y: 65, width: 35, height: 25, wing: 'grande-terre' },
  { name: 'Les Abymes', x: 160, y: 110, width: 40, height: 35, wing: 'grande-terre' },
  { name: 'Pointe-à-Pitre', x: 130, y: 120, width: 35, height: 30, wing: 'grande-terre' },
  { name: 'Le Gosier', x: 145, y: 160, width: 30, height: 25, wing: 'grande-terre' },
  { name: 'Sainte-Anne', x: 175, y: 190, width: 35, height: 30, wing: 'grande-terre' },
  { name: 'Saint-François', x: 215, y: 180, width: 35, height: 35, wing: 'grande-terre' },

  // Dependencies
  { name: 'Grand-Bourg', x: 160, y: 300, width: 25, height: 20, wing: 'dependency' },
  { name: 'Capesterre-de-Marie-Galante', x: 190, y: 310, width: 30, height: 20, wing: 'dependency' },
  { name: 'Saint-Louis', x: 175, y: 335, width: 25, height: 20, wing: 'dependency' },
  { name: 'La Désirade', x: 250, y: 90, width: 20, height: 18, wing: 'dependency' },
  { name: 'Terre-de-Haut', x: 150, y: 360, width: 20, height: 18, wing: 'dependency' },
  { name: 'Terre-de-Bas', x: 175, y: 375, width: 20, height: 18, wing: 'dependency' },
];

const getGravityColor = (maxGravity: number): string => {
  if (maxGravity < 0.3) return '#10b981'; // green
  if (maxGravity < 0.5) return '#eab308'; // yellow
  if (maxGravity < 0.7) return '#f97316'; // orange
  return '#ef4444'; // red
};

const getColorWithOpacity = (color: string, opacity: number): string => {
  const hex = color.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${opacity})`;
};

export default function GuadeloupeMap({
  communeData = {},
  onCommuneClick,
}: GuadeloupeMapProps) {
  const [tooltip, setTooltip] = useState<TooltipState>({
    visible: false,
    commune: '',
    x: 0,
    y: 0,
    count: 0,
    maxGravity: 0,
  });
  const [hoveredCommune, setHoveredCommune] = useState<string | null>(null);

  const handleMouseEnter = (commune: Commune, e: React.MouseEvent<SVGRectElement>) => {
    const data = communeData[commune.name];
    const rect = e.currentTarget.getBoundingClientRect();

    setHoveredCommune(commune.name);
    setTooltip({
      visible: true,
      commune: commune.name,
      x: rect.left,
      y: rect.top,
      count: data?.count ?? 0,
      maxGravity: data?.maxGravity ?? 0,
    });
  };

  const handleMouseLeave = () => {
    setHoveredCommune(null);
    setTooltip({ ...tooltip, visible: false });
  };

  const handleClick = (communeName: string) => {
    onCommuneClick?.(communeName);
  };

  return (
    <div className="w-full h-full flex flex-col items-center justify-center p-6">
      <style jsx>{`
        @keyframes glow {
          0%, 100% {
            filter: drop-shadow(0 0 8px rgba(99, 102, 241, 0.6));
          }
          50% {
            filter: drop-shadow(0 0 16px rgba(99, 102, 241, 0.9));
          }
        }

        .commune-rect {
          fill: rgba(99, 102, 241, 0.15);
          stroke: rgba(99, 102, 241, 0.3);
          stroke-width: 1.5;
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .commune-rect:hover {
          filter: drop-shadow(0 0 12px rgba(99, 102, 241, 0.8));
          stroke-width: 2;
        }

        .commune-text {
          font-size: 8px;
          font-weight: 500;
          fill: rgba(255, 255, 255, 0.8);
          pointer-events: none;
          text-anchor: middle;
          dominant-baseline: middle;
        }

        .commune-rect.active {
          animation: glow 2s ease-in-out infinite;
          stroke-width: 2.5;
        }
      `}</style>

      <div className="relative w-full max-w-4xl">
        <svg
          viewBox="0 0 500 400"
          className="w-full h-auto bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 rounded-xl border border-indigo-500/30 shadow-2xl"
          style={{
            boxShadow:
              '0 0 40px rgba(99, 102, 241, 0.2), inset 0 0 40px rgba(99, 102, 241, 0.05)',
          }}
        >
          {/* Title background */}
          <rect
            x="0"
            y="0"
            width="500"
            height="25"
            fill="rgba(99, 102, 241, 0.1)"
            stroke="rgba(99, 102, 241, 0.3)"
            strokeWidth="0.5"
          />
          <text
            x="250"
            y="15"
            className="commune-text"
            fontSize="11"
            fontWeight="bold"
          >
            Guadeloupe - 32 Communes
          </text>

          {/* Communes */}
          {communes.map((commune) => {
            const data = communeData[commune.name];
            const gravityColor = data ? getGravityColor(data.maxGravity) : 'rgba(99, 102, 241, 0.3)';
            const isHovered = hoveredCommune === commune.name;

            return (
              <g key={commune.name}>
                <rect
                  className={`commune-rect ${isHovered ? 'active' : ''}`}
                  x={commune.x}
                  y={commune.y}
                  width={commune.width}
                  height={commune.height}
                  rx="3"
                  ry="3"
                  fill={data ? getColorWithOpacity(gravityColor, 0.25) : 'rgba(99, 102, 241, 0.15)'}
                  stroke={data ? getColorWithOpacity(gravityColor, 0.6) : 'rgba(99, 102, 241, 0.3)'}
                  onMouseEnter={(e) => handleMouseEnter(commune, e)}
                  onMouseLeave={handleMouseLeave}
                  onClick={() => handleClick(commune.name)}
                />
                <text
                  x={commune.x + commune.width / 2}
                  y={commune.y + commune.height / 2}
                  className="commune-text"
                  fontSize={commune.width > 30 ? '8' : '7'}
                  pointerEvents="none"
                >
                  {commune.name.split('-').map((part, i) => (
                    <tspan key={i} x={commune.x + commune.width / 2} dy={i === 0 ? 0 : 8}>
                      {part}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}

          {/* Legend */}
          <g>
            <rect
              x="10"
              y="360"
              width="480"
              height="30"
              fill="rgba(15, 23, 42, 0.8)"
              stroke="rgba(99, 102, 241, 0.3)"
              strokeWidth="1"
              rx="4"
            />
            <circle cx="25" cy="375" r="5" fill="#10b981" opacity="0.7" />
            <text x="35" y="378" className="commune-text" fontSize="7">
              Weak (&lt;0.3)
            </text>

            <circle cx="120" cy="375" r="5" fill="#eab308" opacity="0.7" />
            <text x="130" y="378" className="commune-text" fontSize="7">
              Moderate (0.3-0.5)
            </text>

            <circle cx="250" cy="375" r="5" fill="#f97316" opacity="0.7" />
            <text x="260" y="378" className="commune-text" fontSize="7">
              Strong (0.5-0.7)
            </text>

            <circle cx="370" cy="375" r="5" fill="#ef4444" opacity="0.7" />
            <text x="380" y="378" className="commune-text" fontSize="7">
              Very Strong (&gt;0.7)
            </text>
          </g>
        </svg>
      </div>

      {/* Tooltip */}
      {tooltip.visible && (
        <div
          className="fixed pointer-events-none z-50"
          style={{
            left: `${tooltip.x + 10}px`,
            top: `${tooltip.y + 30}px`,
          }}
        >
          <div
            className="px-4 py-2 rounded-lg border border-indigo-400/40 text-white text-sm whitespace-nowrap"
            style={{
              background:
                'linear-gradient(135deg, rgba(99, 102, 241, 0.25) 0%, rgba(99, 102, 241, 0.15) 100%)',
              backdropFilter: 'blur(10px)',
              boxShadow:
                '0 0 20px rgba(99, 102, 241, 0.3), inset 0 0 20px rgba(99, 102, 241, 0.1)',
            }}
          >
            <div className="font-semibold text-indigo-200">{tooltip.commune}</div>
            <div className="text-xs text-indigo-100 opacity-80">
              Affaires: {tooltip.count}
            </div>
            <div className="text-xs text-indigo-100 opacity-80">
              Gravité: {tooltip.maxGravity.toFixed(2)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
