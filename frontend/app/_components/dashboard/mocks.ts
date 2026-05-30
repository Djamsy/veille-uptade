// Mock data shown when backend returns nothing.
// Mirrors the editorial proposal so the dashboard reads as a real newsroom
// preview during dev / when /api endpoints are unavailable.
// Components should render these only when their real prop is empty,
// and surface an "aperçu" indicator so designers don't mistake them for prod data.

import type { Affair, TopEntity, DailyActivity } from '../../../lib/api'

const now = () => new Date()
const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString()
const daysAgo = (d: number) => new Date(Date.now() - d * 86400_000).toISOString()

export const MOCK_AFFAIRS: Affair[] = [
  {
    _id: 'mock-1',
    title: 'Cellule de crise sargasses ouverte demain matin',
    primary_entity: 'Préfecture · Pointe-à-Pitre',
    theme: 'environnement',
    priority: 'hot',
    bmg: 0.78,
    gravity_score: 0.72,
    item_count: 14,
    sentiment: 'négatif',
    last_activity: minutesAgo(6),
    created_at: hoursAgo(8),
    description: 'Le préfet annonce une cellule de crise sargasses ouverte demain matin à 9 h.',
  } as unknown as Affair,
  {
    _id: 'mock-2',
    title: 'CHU urgences saturées · 14 nouveaux articles indexés',
    primary_entity: 'CHU Guadeloupe',
    theme: 'sante',
    priority: 'hot',
    bmg: 0.71,
    gravity_score: 0.69,
    item_count: 28,
    sentiment: 'négatif',
    last_activity: minutesAgo(17),
    created_at: hoursAgo(12),
    description: 'Pic d\'indexation sur la santé publique — couverture massive après la déclaration de la direction.',
  } as unknown as Affair,
  {
    _id: 'mock-3',
    title: 'Fort Delgrès · reconstruction estimée à 4 M€',
    primary_entity: 'Basse-Terre',
    theme: 'culture',
    priority: 'watch',
    bmg: 0.58,
    gravity_score: 0.55,
    item_count: 9,
    sentiment: 'mitigé',
    last_activity: minutesAgo(30),
    created_at: daysAgo(2),
    description: 'Reconstruction Fort Delgrès estimée à 4 M€ par l\'architecte des bâtiments de France.',
  } as unknown as Affair,
  {
    _id: 'mock-4',
    title: 'CMA-CGM ouvre la ligne directe Jarry → Le Havre',
    primary_entity: 'Baie-Mahault',
    theme: 'economie_emploi',
    priority: 'minor',
    bmg: 0.32,
    gravity_score: 0.28,
    item_count: 6,
    sentiment: 'positif',
    last_activity: minutesAgo(49),
    created_at: hoursAgo(6),
    description: 'CMA-CGM ouvre la ligne directe Jarry → Le Havre — sentiment positif.',
  } as unknown as Affair,
  {
    _id: 'mock-5',
    title: 'Quota Groq atteint · 2 captures radio en file',
    primary_entity: 'RCI',
    theme: 'general',
    priority: 'hot',
    bmg: 0.68,
    gravity_score: 0.65,
    item_count: 2,
    sentiment: 'mitigé',
    last_activity: hoursAgo(1),
    created_at: hoursAgo(1),
    description: 'Quota Groq atteint sur la radio · captures en file d\'attente.',
  } as unknown as Affair,
  {
    _id: 'mock-6',
    title: 'Carnaval 2026 · budget communication doublé par la Région',
    primary_entity: 'Région Guadeloupe',
    theme: 'culture_patrimoine',
    priority: 'minor',
    bmg: 0.22,
    gravity_score: 0.18,
    item_count: 11,
    sentiment: 'positif',
    last_activity: hoursAgo(2),
    created_at: daysAgo(1),
    description: 'Carnaval 2026 — budget communication doublé par la Région Guadeloupe.',
  } as unknown as Affair,
  {
    _id: 'mock-7',
    title: 'Homicide village artisanal · enquête ouverte',
    primary_entity: 'Sainte-Anne',
    theme: 'securite_justice',
    priority: 'hot',
    bmg: 0.74,
    gravity_score: 0.78,
    item_count: 8,
    sentiment: 'négatif',
    last_activity: hoursAgo(3),
    created_at: hoursAgo(20),
    description: 'Enquête ouverte après un homicide dans le village artisanal.',
  } as unknown as Affair,
  {
    _id: 'mock-8',
    title: 'Routes N1 · point de blocage permanent',
    primary_entity: 'Petit-Bourg',
    theme: 'infrastructure',
    priority: 'watch',
    bmg: 0.48,
    gravity_score: 0.42,
    item_count: 4,
    sentiment: 'mitigé',
    last_activity: hoursAgo(4),
    created_at: daysAgo(3),
    description: 'Travaux N1 — point de blocage permanent signalé par les usagers.',
  } as unknown as Affair,
]

export const MOCK_ENTITIES: TopEntity[] = [
  { name: 'Ary Chalus', count: 24 },
  { name: 'Guy Losbar', count: 18 },
  { name: 'Harry Durimel', count: 31 },
  { name: 'Josette Borel-Lincertin', count: 9 },
  { name: 'Olivier Nicolas', count: 7 },
  { name: 'Sophie Charles', count: 6 },
]

// Optional role/sentiment hints for richer rendering when entities are mocks.
// Keyed by name — the panel can look these up.
export const MOCK_ENTITY_META: Record<string, { role: string; sentiment: 'positif' | 'mitigé' | 'négatif'; trend: 'up' | 'flat' | 'down' }> = {
  'Ary Chalus':               { role: 'Région Guadeloupe',    sentiment: 'positif', trend: 'up' },
  'Guy Losbar':               { role: 'Département',          sentiment: 'mitigé',  trend: 'flat' },
  'Harry Durimel':            { role: 'Pointe-à-Pitre',       sentiment: 'négatif', trend: 'up' },
  'Josette Borel-Lincertin':  { role: 'Préfecture',           sentiment: 'positif', trend: 'down' },
  'Olivier Nicolas':          { role: 'Basse-Terre',          sentiment: 'mitigé',  trend: 'flat' },
  'Sophie Charles':           { role: 'Sainte-Anne',          sentiment: 'positif', trend: 'up' },
}

export const MOCK_ACTIVITY: DailyActivity[] = [
  { date: daysAgo(6).slice(0, 10), label: 'Lun 10', articles: 38, events: 12 },
  { date: daysAgo(5).slice(0, 10), label: 'Mar 11', articles: 42, events: 14 },
  { date: daysAgo(4).slice(0, 10), label: 'Mer 12', articles: 35, events: 9 },
  { date: daysAgo(3).slice(0, 10), label: 'Jeu 13', articles: 48, events: 18 },
  { date: daysAgo(2).slice(0, 10), label: 'Ven 14', articles: 52, events: 22 },
  { date: daysAgo(1).slice(0, 10), label: 'Sam 15', articles: 41, events: 11 },
  { date: now().toISOString().slice(0, 10), label: 'Dim 16', articles: 39, events: 13 },
]

export const MOCK_SENTIMENT: Record<string, number> = {
  positif: 23,
  neutre: 45,
  mixte: 14,
  négatif: 32,
}

export const MOCK_KPIS = {
  bmg_scaled: 42,
  bmg_delta: 4,
  affairs_active: 100,
  affairs_delta_pct: 12,
  urgents: 19,
  urgents_delta_pct: 3,
  articles_7d: 267,
  articles_delta_pct: 18,
  radio_today: 7,
  radio_total: 12,
}
