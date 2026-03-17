'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

interface Affair {
  _id: string
  primary_entity: string
  importance_score: number
  article_count: number
  status: string
  created_at: string
}

export default function AffairsPage() {
  const [affairs, setAffairs] = useState<Affair[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchAffairs()
  }, [])

  const fetchAffairs = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/affairs?limit=20')
      const data = await response.json()
      
      if (data.success) {
        setAffairs(data.data?.affairs || [])
      } else {
        setError('Erreur lors du chargement des affaires')
      }
    } catch (err) {
      setError('Erreur de connexion')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        <p className="mt-2">Chargement des affaires...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
        <Link href="/dashboard" className="text-blue-500 hover:underline">
          ← Retour au dashboard
        </Link>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Affaires ({affairs.length})</h1>
        <Link href="/dashboard" className="text-blue-500 hover:underline">
          ← Retour au dashboard
        </Link>
      </div>
      
      <div className="grid gap-4">
        {affairs.length === 0 ? (
          <div className="bg-gray-50 p-8 rounded-lg text-center">
            <p className="text-gray-600 mb-2">Aucune affaire active</p>
            <p className="text-sm text-gray-500">
              Les affaires apparaîtront ici quand le système d'analyse détectera des sujets récurrents
            </p>
          </div>
        ) : (
          affairs.map((affair) => (
            <div key={affair._id} className="bg-white p-4 rounded-lg shadow border">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-semibold text-lg">{affair.primary_entity}</h3>
                <span className={`px-2 py-1 rounded text-sm ${
                  affair.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                }`}>
                  {affair.status}
                </span>
              </div>
              <div className="flex space-x-4 text-sm text-gray-600">
                <span>Score: {(affair.importance_score * 100).toFixed(0)}%</span>
                <span>Articles: {affair.article_count}</span>
                <span>Créé: {new Date(affair.created_at).toLocaleDateString('fr-FR')}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
