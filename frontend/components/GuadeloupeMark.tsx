/**
 * Signature visuelle — silhouette stylisée du papillon de Guadeloupe.
 *
 * Forme abstraite (pas un tracé géographique exact) :
 * - Basse-Terre = lobe gauche, contour souple
 * - Grande-Terre = lobe droit, plus anguleux
 * - Rivière Salée = pincement central
 *
 * Usage:
 *   <GuadeloupeMark className="absolute right-8 top-4 opacity-[0.04]" />
 *   <GuadeloupeMark size={20} className="opacity-60" />
 */
type Props = {
  className?: string
  size?: number | string
  stroke?: string
  fill?: string
  title?: string
  style?: React.CSSProperties
}

export function GuadeloupeMark({
  className,
  size,
  stroke = 'currentColor',
  fill = 'none',
  title,
  style,
}: Props) {
  return (
    <svg
      viewBox="0 0 200 110"
      width={size}
      height={size != null ? 'auto' : undefined}
      className={className}
      style={style}
      fill={fill}
      stroke={stroke}
      strokeWidth={1.4}
      strokeLinejoin="round"
      strokeLinecap="round"
      role={title ? 'img' : 'presentation'}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      {/* Basse-Terre — left lobe (rounded triangle) */}
      <path d="M 18 56 Q 22 22 50 16 Q 75 12 92 38 Q 98 50 95 60 Q 90 78 70 88 Q 50 96 32 88 Q 18 80 18 56 Z" />
      {/* Grande-Terre — right lobe (kidney) */}
      <path d="M 108 52 Q 110 30 130 22 Q 158 14 178 30 Q 188 42 184 60 Q 178 78 160 86 Q 138 92 122 84 Q 108 76 108 52 Z" />
      {/* Rivière salée — central pinch (thin line) */}
      <path d="M 95 55 Q 100 50 108 55" strokeWidth={1} />
    </svg>
  )
}
