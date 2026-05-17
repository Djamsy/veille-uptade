# Design System — Veille Média Guadeloupe

> **LOGIC:** Avant de coder une page, vérifier `design-system/veille-media-guadeloupe/pages/[page-name].md`.
> Si ce fichier existe, ses règles **remplacent** celles ci-dessous.
> Sinon, suivre strictement ce Master.

---

**Projet :** Veille Média Guadeloupe 971
**Validé :** 2026-05-16 (v2 — pivot)
**Catégorie :** News / Media Monitoring / Political Watch
**Direction :** **Crème & encre — light editorial** (pivot depuis "press éditoriale dark")

---

## 1. Identité visuelle

**Mood :** journal en papier, salle de rédaction haut de gamme. Référence : The New York Times, Bloomberg print, FT Weekend. Hiérarchie typographique forte, blancs neutres zinc, encre noire, accents sémantiques mute.

**Pourquoi light et pas dark :** un dashboard sombre c'est partout. Un produit qui ressemble à un journal en papier est immédiatement identifiable, plus distinctif pour une app de veille institutionnelle (cible élus + presse + comm 971).

**Anti-référence :** dashboard SaaS dark générique, look "AI app" indigo/violet/pink, glassmorphism omniprésent, accents saturés type Linear/Vercel.

---

## 2. Palette de couleurs

### Surfaces — blancs neutres zinc

| Token | Hex | Usage |
|---|---|---|
| `--bg-base` | `#fafafa` | Fond global (zinc 50) |
| `--bg-surface` | `#ffffff` | Cards, panels |
| `--bg-card` | `#ffffff` | Cards |
| `--bg-elevated` | `#f4f4f5` | Sidebar, surfaces de niveau 2 |
| `--bg-hover` | `#f4f4f5` | Hover surfaces |
| `--bg-sidebar` | `#f4f4f5` | Sidebar |

### Bordures

| Token | Hex | Usage |
|---|---|---|
| `--border` | `#e8e8eb` | Standard |
| `--border-subtle` | `#e8e8eb` | Discret |
| `--border-hover` | `#d4d4d8` | Hover |
| `--border-strong` | `#a1a1aa` | Fort |

### Texte — encre noire, gris neutres

| Token | Hex | Usage |
|---|---|---|
| `--text` | `#18181b` | Principal (encre noire = zinc 900) |
| `--text-secondary` | `#3f3f46` | Secondaire (zinc 700) |
| `--text-muted` | `#71717a` | Muted (zinc 500) |
| `--text-disabled` | `#a1a1aa` | Disabled (zinc 400) |

### Accents — sobriété éditoriale

| Token | Hex | Usage |
|---|---|---|
| `--accent-press` | `#18181b` | **CTA principal = encre noire** (boutons primary, focus, active) |
| `--accent-press-light` | `#27272a` | Hover |
| `--accent-alert` | `#b8632a` | Warning ambré désaturé (alertes BMG, urgences) |
| `--accent-link` | `#3e6fa3` | Liens, info |

### Tokens sémantiques (désaturés pour lecture sur fond clair)

| Token | Hex | Usage |
|---|---|---|
| `--sentiment-positive` | `#4f8b56` | Sentiment + |
| `--sentiment-negative` | `#c43850` | Sentiment - |
| `--sentiment-neutral` | `#71717a` | Sentiment neutre |
| `--sentiment-mixed` | `#b8632a` | Sentiment mixte |
| `--bmg-low` | `#4f8b56` | Gravité faible |
| `--bmg-medium` | `#a88820` | Gravité moyenne |
| `--bmg-high` | `#b8632a` | Gravité haute |
| `--bmg-critical` | `#c43850` | Gravité critique |

### Soft backgrounds pour tags/badges (très pâle, texte foncé)

| Token | Hex | Texte |
|---|---|---|
| `--crit-soft` | `#fdf2f4` | `#b02939` (crit) |
| `--warn-soft` | `#fdf6f0` | `#9d551f` (warn) |
| `--caution-soft` | `#fdfaf0` | `#8a7218` (caution) |
| `--ok-soft` | `#f0f8f1` | `#3d6f44` (ok) |
| `--info-soft` | `#f1f5fa` | `#2f5680` (info) |

### Brand gradient (logo uniquement, version mute)

```css
--brand-gradient: linear-gradient(135deg, #4f8b56 0%, #a88820 50%, #c43850 100%);
```
Vert mute → ambré mute → rouge mute. Sobre, pas saturé.

### À retirer

- ❌ Toute la palette dark (indigo/violet déjà retirée, dark base à retirer aussi)
- ❌ Glassmorphism par défaut (la base est solide, pas glass)
- ❌ Glow boxshadows colorés
- ❌ Tokens `--accent-press: #DC2626` (rouge presse) — remplacé par encre noire

---

## 3. Typographie

### Fonts

- **Display (titres éditoriaux H1/H2, gros nombres KPI) :** [Newsreader](https://fonts.google.com/specimen/Newsreader) — serif éditorial, italique pour les sous-titres éditoriaux
- **Body / UI :** [Inter](https://fonts.google.com/specimen/Inter) — conservé pour cohérence UI dense
- **Mono (données / IDs / timestamps / KPI numbers) :** `ui-monospace, SFMono-Regular` (system) — privilégié pour data

```css
--font-sans: var(--font-inter), 'Inter', system-ui, -apple-system, sans-serif;
--font-serif: var(--font-newsreader), 'Newsreader', Georgia, serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, monospace;
```

### Échelle éditoriale

| Usage | Classes | Notes |
|---|---|---|
| Page H1 éditorial (ex: "Édition du 16 mai") | `font-serif text-3xl md:text-4xl font-medium tracking-tight italic` | Style éditorial fort, italique signature |
| Eyebrow (ex: "PILOTAGE / VUE D'ENSEMBLE") | `font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted` | Mono pour signal navigation |
| Section H2 | `font-serif text-xl font-semibold tracking-tight` | Newsreader, hiérarchie forte |
| Section title (widget) | `font-sans text-sm font-semibold` | Inter, UI dense |
| KPI number | `font-serif text-3xl font-semibold tabular-nums` | Gros, lisible en 2s |
| KPI label | `font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted` | Mono pour data |
| Trend delta (↗ +4) | `font-mono text-xs` colored par signal | Mono tabular |
| Body | `font-sans text-sm leading-relaxed` | |
| Timestamp | `font-mono text-xs text-text-muted tabular-nums` | |

---

## 4. Espacements, rayons, ombres

| Token | Valeur | Usage |
|---|---|---|
| `--radius-sm` | 4px | Tags, badges (rayons fins éditoriaux) |
| `--radius` | 6px | Panels, cards |
| `--radius-lg` | 8px | Modals |
| `--shadow-card` | `0 1px 2px rgba(0,0,0,0.04)` | Cards (très subtil sur fond clair) |
| `--shadow-elevated` | `0 4px 12px rgba(0,0,0,0.08)` | Dropdowns, modals |

**Note :** sur fond clair, les ombres doivent être TRÈS subtiles. Privilégier les bordures `#e8e8eb` pour délimiter.

---

## 5. Composants

### Cards / Panels

```css
.panel {
  background: var(--bg-surface);       /* white */
  border: 1px solid var(--border);     /* #e8e8eb */
  border-radius: var(--radius);        /* 6px */
}
```
**Pas d'ombre par défaut**, les bordures suffisent sur fond crème.

### Buttons

```css
.btn-primary {
  background: var(--accent-press);     /* #18181b ink black */
  color: white;
  border: 1px solid var(--accent-press);
}
.btn-secondary {
  background: white;
  border: 1px solid var(--border);
  color: var(--text);
}
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}
```

Focus ring : `outline: 2px solid var(--accent-press); outline-offset: 2px;`
Touch targets : min 44x44px.

### KPI cell (pattern signature)

```jsx
<div className="panel p-3">
  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-muted">BMG moyen</span>
  <div className="flex items-baseline gap-2 mt-1">
    <span className="font-serif text-3xl font-semibold tabular-nums">42</span>
    <span className="font-mono text-xs text-warn">↗ +4 pts</span>
  </div>
</div>
```

### Tags semantic (fond pâle, texte foncé)

```css
.tag-crit    { background: #fdf2f4; color: #b02939; border: 1px solid #f5d4d9; }
.tag-warn    { background: #fdf6f0; color: #9d551f; border: 1px solid #f3dcc5; }
.tag-caution { background: #fdfaf0; color: #8a7218; border: 1px solid #ecdfa9; }
.tag-ok      { background: #f0f8f1; color: #3d6f44; border: 1px solid #cce5d0; }
.tag-info    { background: #f1f5fa; color: #2f5680; border: 1px solid #d3dde9; }
```

---

## 6. Layout signatures (Dashboard `/`)

Le dashboard suit la structure éditoriale **3 colonnes** :

```
┌─ Sidebar (PILOTAGE + SYSTÈME) ─┬─ KPI strip (4 cells) ─────────────┬─ FLUX TEMPS RÉEL ──┐
│                                ├─ Carte concentration 24h ─────────┤  - Personnalités   │
│                                ├─ Barometre médiatique 7j (chart)  │  - Live ticker     │
└────────────────────────────────┴───────────────────────────────────┴────────────────────┘
```

- **KPI strip** : 4 cells horizontales avec gros chiffres serif + trend
- **Carte** : intégrée (pas plein écran), avec clusters annotés
- **FLUX TEMPS RÉEL** : ticker live horodaté par source (RCI, France-Antilles, KaribInfo, etc.)
- **H1 éditorial** au-dessus : "Édition du 16 mai" en serif italique + eyebrow `PILOTAGE / VUE D'ENSEMBLE`

---

## 7. Navigation (architecture simplifiée — 2 sections)

```
PILOTAGE  → Vue d'ensemble | Affaires | Articles | Radio | Réseaux | Carte | Élections | Analytics | Briefing
SYSTÈME   → Alertes | Admin | Paramètres
```

- Sidebar bg : `--bg-elevated` (`#f4f4f5` — un cran plus chaud que les surfaces)
- Sections : eyebrow `font-mono text-[10px] uppercase tracking-[0.18em] text-text-muted`
- Item actif : barre verticale 2px gauche `--accent-press` (encre noire) + bg `--bg-hover`
- Icônes : 17-18px, line-icons (heroicons outline ou similaire)

---

## 8. Anti-patterns

- ❌ Dark mode par défaut
- ❌ Glassmorphism par défaut (gardé seulement pour overlays carte, ou supprimé carrément)
- ❌ Couleurs saturées brand (indigo/violet/rose) — tout passe en mute
- ❌ Emojis comme icônes UI (SVG line uniquement)
- ❌ Gradients colorés au-delà du logo
- ❌ Ombres prononcées (bordures à la place)
- ❌ Couleur seule pour communiquer un état (icône + texte)
- ❌ `cursor: default` sur du cliquable
- ❌ Focus state invisible

---

## 9. Checklist pré-livraison

- [ ] Aucun fond noir/dark introduit
- [ ] Contraste texte ≥ 4.5:1 (encre `#18181b` sur `#fafafa` = 16:1, OK)
- [ ] Icônes SVG line uniquement (pas d'emoji, pas de filled)
- [ ] `cursor-pointer` sur tout cliquable
- [ ] Focus ring visible 2-3px sur tout interactif
- [ ] Touch targets ≥ 44x44px
- [ ] Responsive 375 / 768 / 1024 / 1440
- [ ] Pas de scroll horizontal mobile
- [ ] Newsreader appliqué sur H1/H2 éditoriaux et gros chiffres KPI
- [ ] Mono appliqué sur eyebrows, timestamps, IDs, nombres

---

## 10. Phases de rollout

1. ✅ Direction "Press éditoriale dark" validée puis **pivot vers "Crème & encre"** (2026-05-16)
2. ✅ Découpe `app/page.tsx` (1739 → 956 lignes) — fondation conservée
3. ⏳ Token pivot light cream & ink (`globals.css` + `tailwind.config.js` + `layout.tsx`)
4. ⏸ Refonte Sidebar simplifiée (2 sections PILOTAGE / SYSTÈME) + light
5. ⏸ Refonte Dashboard structurel (KPI strip + carte intégrée + FLUX TEMPS RÉEL rail)
6. ⏸ Pages prioritaires : Articles (comparaison sources) + Radio (waveforms + courbes)
7. ⏸ Le reste : Briefing, Analytics, Affaires (table éditoriale), Social, Élections, Admin, Login
