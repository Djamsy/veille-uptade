import { redirect } from 'next/navigation'

// L'espace Publications a sa propre adresse, hors menu : /publications
export default function AdminPublicationsRedirect() {
  redirect('/publications')
}
