/**
 * Root loading.tsx — affiché instantanément pendant le streaming des Server Components.
 *
 * Sans ce fichier, Next.js attend que toute la page soit prête avant de rendre quoi
 * que ce soit. Avec lui, l'utilisateur voit ce skeleton sous 100 ms, puis le contenu
 * s'hydrate progressivement.
 */
export default function RootLoading() {
  return (
    <div
      role="status"
      aria-label="Chargement"
      style={{
        minHeight: '60vh',
        display: 'grid',
        placeItems: 'center',
        opacity: 0.55,
        padding: '24px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: '50%',
            border: '2px solid rgba(241, 245, 249, 0.18)',
            borderTopColor: 'rgba(241, 245, 249, 0.75)',
            animation: 'sw-spin 0.9s linear infinite',
          }}
        />
        <span style={{ fontSize: 13, color: 'rgba(241, 245, 249, 0.65)' }}>
          Chargement…
        </span>
      </div>
      <style>{`
        @keyframes sw-spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
