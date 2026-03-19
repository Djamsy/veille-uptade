'use client'

import AuthGuard from './AuthGuard'
import BottomNav from './BottomNav'

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      {children}
      <BottomNav />
    </AuthGuard>
  )
}
