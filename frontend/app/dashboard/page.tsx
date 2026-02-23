'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

// Redirige /dashboard vers / (nouveau dashboard V2)
export default function DashboardRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace('/') }, [router])
  return null
}
