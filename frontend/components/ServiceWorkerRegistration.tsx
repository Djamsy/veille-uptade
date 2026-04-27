'use client'

import { useEffect, useState } from 'react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://veille-api-ubrw.onrender.com'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

async function subscribeToPush(registration: ServiceWorkerRegistration) {
  try {
    // Récupérer la clé VAPID depuis le backend
    const res = await fetch(`${API_URL}/api/push/vapid-key`)
    const data = await res.json()
    if (!data.ok || !data.publicKey) {
      console.log('Push: VAPID key not available')
      return
    }

    // S'inscrire au push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(data.publicKey) as BufferSource,
    })

    // Envoyer l'inscription au backend
    await fetch(`${API_URL}/api/push/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON()),
    })

    console.log('✅ Push subscription active')
  } catch (err) {
    console.log('Push subscription failed:', err)
  }
}

export default function ServiceWorkerRegistration() {
  const [pushSupported, setPushSupported] = useState(false)
  const [pushPermission, setPushPermission] = useState<string>('default')

  useEffect(() => {
    if (!('serviceWorker' in navigator)) return
    if (!('PushManager' in window)) return

    setPushSupported(true)
    setPushPermission(Notification.permission)

    // Enregistrer le service worker
    navigator.serviceWorker.register('/sw.js').then(async (registration) => {
      console.log('SW registered')

      // Si la permission est déjà accordée, s'inscrire directement
      if (Notification.permission === 'granted') {
        await subscribeToPush(registration)
      }
    }).catch((err) => {
      console.log('SW registration failed:', err)
    })
  }, [])

  // Demander la permission push (appelé par le bouton dans le dashboard)
  useEffect(() => {
    const handler = async () => {
      if (Notification.permission !== 'default') return

      const permission = await Notification.requestPermission()
      setPushPermission(permission)

      if (permission === 'granted') {
        const registration = await navigator.serviceWorker.ready
        await subscribeToPush(registration)
      }
    }

    // Écouter un événement custom pour déclencher la demande
    window.addEventListener('request-push-permission', handler)
    return () => window.removeEventListener('request-push-permission', handler)
  }, [])

  // Exposer l'état push sur window pour le dashboard
  useEffect(() => {
    (window as any).__pushState = {
      supported: pushSupported,
      permission: pushPermission,
      requestPermission: () => {
        window.dispatchEvent(new Event('request-push-permission'))
      },
    }
  }, [pushSupported, pushPermission])

  return null
}
