'use client'

// template.tsx se re-monte à CHAQUE navigation (contrairement à layout.tsx).
// → joue une transition de fondu sur chaque changement de page.
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="route-enter">{children}</div>
}
