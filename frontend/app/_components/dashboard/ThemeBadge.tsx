import { themeColorParts, themeLabel } from '../../../lib/formatters'

export function ThemeBadge({ theme }: { theme: string }) {
  const [bg, color, border] = themeColorParts(theme)
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-medium"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {themeLabel(theme)}
    </span>
  )
}
