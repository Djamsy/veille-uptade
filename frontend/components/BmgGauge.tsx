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
    if (v >= 75) return '#ef4444'  // critical red
    if (v >= 50) return '#f97316'  // high orange
    if (v >= 25) return '#f59e0b'  // medium amber
    return '#10b981'               // low green
  }

  const getGlow = (v: number) => {
    if (v >= 75) return 'rgba(239,68,68,0.4)'
    if (v >= 50) return 'rgba(249,115,22,0.3)'
    if (v >= 25) return 'rgba(245,158,11,0.2)'
    return 'rgba(16,185,129,0.2)'
  }

  const getLevel = (v: number) => {
    if (v >= 75) return 'CRITIQUE'
    if (v >= 55) return 'ÉLEVÉ'
    if (v >= 35) return 'MODÉRÉ'
    if (v >= 15) return 'FAIBLE'
    return 'MINIMAL'
  }

  const color = getColor(clamped)
  const glowColor = getGlow(clamped)
  const isCritical = clamped >= 75

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size}
        viewBox="0 0 80 80"
        className={isCritical ? 'gauge-critical' : ''}
        style={{ filter: `drop-shadow(0 0 8px ${glowColor})` }}
      >
        {/* Background circle */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth="5"
        />
        {/* Value arc */}
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 40 40)"
          style={{
            transition: 'stroke-dashoffset 0.8s ease-out',
            filter: `drop-shadow(0 0 4px ${color})`,
          }}
        />
        {/* Value text */}
        <text
          x="40"
          y="36"
          textAnchor="middle"
          fill="white"
          fontSize="18"
          fontWeight="700"
          style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
        >
          {Math.round(clamped)}
        </text>
        <text
          x="40"
          y="51"
          textAnchor="middle"
          fill="rgba(255,255,255,0.4)"
          fontSize="7"
          fontWeight="600"
          letterSpacing="0.05em"
          style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
        >
          {label || getLevel(clamped)}
        </text>
      </svg>
    </div>
  )
}
