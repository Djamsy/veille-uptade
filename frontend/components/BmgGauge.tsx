'use client'

interface BmgGaugeProps {
  value: number   // 0-100
  size?: number
  label?: string
}

export default function BmgGauge({ value, size = 80, label }: BmgGaugeProps) {
  const clamped = Math.min(100, Math.max(0, value))
  const radius = 35
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (clamped / 100) * circumference

  const getColor = (v: number) => {
    if (v >= 75) return '#dc2626'  // critical red
    if (v >= 50) return '#ef4444'  // high red
    if (v >= 25) return '#f59e0b'  // medium yellow
    return '#10b981'               // low green
  }

  const getLevel = (v: number) => {
    if (v >= 75) return 'Critique'
    if (v >= 50) return 'Élevé'
    if (v >= 25) return 'Modéré'
    return 'Faible'
  }

  const color = getColor(clamped)
  const isCritical = clamped >= 75

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size}
        viewBox="0 0 80 80"
        className={isCritical ? 'gauge-critical' : ''}
      >
        {/* Background circle */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke="#334155"
          strokeWidth="6"
          opacity="0.5"
        />
        {/* Value arc */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 40 40)"
          style={{ transition: 'stroke-dashoffset 0.8s ease-out' }}
        />
        {/* Value text */}
        <text
          x="40"
          y="37"
          textAnchor="middle"
          className="text-xl font-bold"
          fill={color}
          fontSize="18"
        >
          {Math.round(clamped)}
        </text>
        <text
          x="40"
          y="52"
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="8"
          fontWeight="500"
        >
          {label || getLevel(clamped)}
        </text>
      </svg>
    </div>
  )
}
