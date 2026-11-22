// lib/media.ts — affichage robuste des médias hébergés (Cloudinary) dans les pages Publications.
//
// Deux problèmes réglés ici :
//  1. Un fichier déposé depuis un téléphone peut être un HEIC (iPhone) ou peser 10 Mo : servi tel quel,
//     le navigateur ne l'affiche pas ou très lentement → Cloudinary convertit à la volée (f_jpg, q_auto, w_<px>).
//  2. Certains postes (sécurité réseau) bloquent res.cloudinary.com → les pages affichent les médias via
//     /media-cdn/…, un relais Vercel (next.config.js) sous le domaine du site. L'URL d'origine reste
//     celle stockée : c'est elle que Buffer reçoit.

const CLOUDINARY = /^https:\/\/res\.cloudinary\.com\/([^/]+)\/(image|video)\/upload\/(.*)$/i
const IMG_EXT = /\.(jpe?g|png|gif|webp|avif|heic|heif|bmp|tiff?)(\?|$)/i
const VID_EXT = /\.(mp4|mov|m4v|webm)(\?|$)/i
const RELAY = '/media-cdn/'

export const isVideoUrl = (u: string) => VID_EXT.test(u) || /\/video\/upload\//i.test(u)
export const isImageUrl = (u: string) => !isVideoUrl(u) && (IMG_EXT.test(u) || /\/image\/upload\//i.test(u))

/** URL à mettre dans <img> : relais sous notre domaine + conversion jpg redimensionnée (Cloudinary) ; sinon l'URL telle quelle. */
export function displayUrl(u: string, width = 1200): string {
  const m = u.match(CLOUDINARY)
  if (!m) return u
  const [, cloud, kind, rest] = m
  if (kind === 'video') return `${RELAY}${cloud}/video/upload/${rest}`
  const alreadyTransformed = /^(f_|q_|w_|c_)/.test(rest)
  return `${RELAY}${cloud}/image/upload/${alreadyTransformed ? '' : `f_jpg,q_auto,w_${width}/`}${rest}`
}

/** URL à mettre dans <video> : relais sous notre domaine. */
export const videoUrl = (u: string) => displayUrl(u)

/** Nom lisible d'un média (dernier segment de l'URL). */
export const mediaName = (u: string) => decodeURIComponent(u.split('?')[0].split('/').pop() || u).slice(0, 60)
