# Design System — Veille Média Guadeloupe

> **LOGIC:** Avant de coder une page, vérifier `design-system/veille-media-guadeloupe/pages/[page-name].md`.
> Si ce fichier existe, ses règles **remplacent** celles ci-dessous.
> Sinon, suivre strictement ce Master.

---

**Projet :** Veille Média Guadeloupe 971
**Validé :** 2026-05-16
**Catégorie :** News / Media Monitoring / Political Watch
**Direction :** Press éditoriale dark (Option A — choisie par le user)

---

## 1. Identité visuelle

**Mood :** salle de rédaction moderne. Référence : Bloomberg Terminal × FT.com dark mode × Reuters Connect. Hiérarchie typographique forte, la donnée respire, sobriété éditoriale.

**Anti-référence :** dashboard SaaS générique (Linear, Vercel-clone), look "AI app" indigo/violet/pink, glassmorphism omniprésent.

---

## 2. Palette de couleurs

### Base (dark layers — conservées de l'existant v3)

| Token | Hex | Usage |
|---|---|---|
| `--bg-base` | `#0a0a0f` | Fond global |
| `--bg-surface` | `#0d0d14` | Sidebar, surfaces de niveau 1 |
| `--bg-card` | `#12121a` | Cards |
| `--bg-elevated` | `#1a1a24` | Cards survolées, dropdowns |
| `--bg-hover` | `#1f1f2e` | Hover surfaces |

### Accents (NOUVEAUX — remplacent indigo/violet)

| Token | Hex | Usage |
|---|---|---|
| `--accent-press` | `#DC2626` | **Breaking / urgent / actif** — rouge presse, accent principal |
| `--accent-alert` | `#F59E0B` | **Alertes, warnings, BMG medium** — ambre |
| `--accent-link` | `#0369A1` | **Liens, CTA secondaires** — bleu lien |
| `--accent-text` | `#F8FAFC` | Texte sur accent (contraste max) |

### Tokens sémantiques (depuis `gpe.*` existants, repositionnés)

| Token | Hex | Usage |
|---|---|---|
| `--sentiment-positive` | `#16a34a` (gpe.green) | Sentiment +, status OK |
| `--sentiment-neutral` | `#94a3b8` | Sentiment neutre |
| `--sentiment-negative` | `#dc2626` (gpe.red) | Sentiment - |
| `--bmg-low` | `#16a34a` | Gravité faible |
| `--bmg-medium` | `#eab308` | Gravité moyenne |
| `--bmg-high` | `#ef4444` | Gravité haute |
| `--bmg-critical` | `#7f1d1d` | Gravité critique |

### Texte

| Token | Hex | Usage |
|---|---|---|
| `--text` | `#f1f5f9` | Principal |
| `--text-secondary` | `#cbd5e1` | Secondaire |
| `--text-muted` | `#64748b` | Muted, labels |

### À retirer (anti-tokens)

- ❌ `#6366f1`, `#818cf8`, `#8b5cf6` (indigo/violet — palette générique)
- ❌ Tous les `linear-gradient(135deg, #6366f1, #8b5cf6)` inline (Sidebar logo, user avatar, etc.)
- ❌ `boxShadow: '0 4px 16px rgba(99,102,241,0.3)'` (glow indigo)

---

## 3. Typographie

### Pairing : News Editorial

- **Headings :** [Newsreader](https://fonts.google.com/specimen/Newsreader) — serif éditorial conçu pour la presse digitale. Conserve une vraie identité "news".
- **Body / UI :** [Inter](https://fonts.google.com/specimen/Inter) — déjà en place, on garde pour la cohérence UI dense.
- **Mono (données / IDs / timestamps) :** `ui-monospace, SFMono-Regular` (system) — pour les IDs d'articles, dates précises, métriques.

```css
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=Inter:wght@300;400;500;600;700&display=swap');
```

### Tailwind config

```js
fontFamily: {
  serif: ['Newsreader', 'Georgia', 'serif'],
  sans: ['Inter', 'system-ui', 'sans-serif'],
  mono: ['ui-monospace', 'SFMono-Regular', 'monospace'],
}
```

### Échelle

| Usage | Classes | Notes |
|---|---|---|
| Page H1 | `font-serif text-4xl md:text-5xl font-semibold tracking-tight` | Newsreader, hiérarchie forte |
| Section H2 | `font-serif text-2xl font-semibold` | |
| Card title | `font-sans text-base font-semibold` | Inter, UI dense |
| Body | `font-sans text-sm leading-relaxed` | |
| Label/eyebrow | `font-sans text-[10px] uppercase tracking-[0.15em] text-text-muted` | |
| Data/timestamp | `font-mono text-xs tabular-nums` | |

---

## 4. Espacements, rayons, ombres

| Token | Valeur | Usage |
|---|---|---|
| `--space-xs` → `--space-3xl` | 4 → 64px | Échelle multiplicateur 1.5x |
| `--radius-sm` | 8px | Boutons, badges |
| `--radius` | 12px | Cards, inputs |
| `--radius-lg` | 16px | Modals, hero |
| `--shadow-card` | `0 1px 3px rgba(0,0,0,0.4)` | Cards mates (pas de glow) |
| `--shadow-elevated` | `0 4px 16px rgba(0,0,0,0.5)` | Dropdowns, modals |

---

## 5. Composants

### Cards

**MAT** par défaut — on a abandonné le glassmorphism systématique.

```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
}
.card:hover { background: var(--bg-elevated); border-color: var(--border-hover); }
```

### Buttons

```css
.btn-primary { background: var(--accent-press); color: var(--accent-text); }
.btn-secondary { background: transparent; border: 1px solid var(--border-hover); color: var(--text); }
.btn-ghost { background: transparent; color: var(--text-muted); }
.btn-ghost:hover { background: var(--bg-hover); color: var(--text); }
```

Touch targets : **min 44x44px**. Focus ring : `outline: 2px solid var(--accent-link); outline-offset: 2px;`

### Status dots / badges

Utiliser les tokens sémantiques (`--sentiment-*`, `--bmg-*`) avec un dot 8px + label texte. **Ne jamais utiliser la couleur seule** (a11y).

### Glassmorphism

**Réservé exclusivement aux overlays sur cartes Mapbox** (PresenceMap, GuadeloupeMap, MapboxFullMap). Utiliser `--glass-heavy-bg` (existant). Partout ailleurs : cards mates.

---

## 6. Navigation (architecture validée)

```
VEILLE     → Articles | Radio | Réseaux sociaux
TERRAIN    → Carte | Élus | Affaires
ANALYSE    → Dashboard | Analytics | Briefing
ADMIN      → Admin (role-gated)
```

- Sidebar : sections avec headers `text-[10px] uppercase tracking-widest text-text-muted`
- Actif : barre verticale 2px `--accent-press` à gauche + texte `--text`
- Mobile : `BottomNav` montre les 3 groupes principaux (Veille / Terrain / Analyse)
- Élections : à arbitrer en cours de route (Terrain temporel ou Analyse selon usage)

---

## 7. Anti-patterns (NE PAS faire)

- ❌ Réintroduire l'indigo/violet (`#6366f1`, `#818cf8`, `#8b5cf6`)
- ❌ Glassmorphism hors overlays carte
- ❌ Emojis comme icônes UI (utiliser Heroicons / Lucide en SVG)
- ❌ Gradients "AI" violet/rose/cyan
- ❌ Couleur seule pour communiquer un état (toujours icône + texte)
- ❌ `cursor: default` sur du cliquable
- ❌ Hover qui shift le layout (`scale` sur card cliquable, pad qui bouge)
- ❌ Transitions instantanées ou >300ms sur micro-interactions
- ❌ Focus state invisible

---

## 8. Checklist pré-livraison

- [ ] Aucun indigo/violet réintroduit (`grep -i "6366f1\|818cf8\|8b5cf6"`)
- [ ] Icônes SVG uniquement (pas d'emoji)
- [ ] `cursor-pointer` sur tout cliquable
- [ ] Focus ring visible 2-3px sur tout interactif
- [ ] Contraste texte ≥ 4.5:1
- [ ] `prefers-reduced-motion` respecté
- [ ] Responsive 375 / 768 / 1024 / 1440
- [ ] Pas de scroll horizontal mobile
- [ ] Touch targets ≥ 44x44px

---

## 9. Phases de rollout

1. ✅ Direction validée + design system persisté (2026-05-16)
2. ⏳ Découper `app/page.tsx` (1739 lignes) en sous-composants colocalisés
3. ⏸ Refonte tokens CSS (globals.css) + Tailwind config (fonts, palette)
4. ⏸ Refonte Sidebar + BottomNav (regroupement 4 sections)
5. ⏸ Pages prioritaires : `/`, `/articles`, `/carte`
6. ⏸ Le reste (Briefing, Analytics, Radio, Réseaux, Élections, Affaires, Admin)
