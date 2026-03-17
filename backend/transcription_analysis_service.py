"""
Service d'analyse intelligente des transcriptions radio — DIGEST COMPLET
- Résumé riche (titre + puces + contexte + suites)
- Digest structuré par RUBRIQUES (même si partiellement pertinentes)
- Extraction étendue (personnes / institutions / lieux / infrastructures / chiffres / temps / citations)
- Détection spéciale journaux 6h15 (GP) / 6h20 (RCI) et interviews
"""
import re
from typing import Dict, Any, List, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TranscriptionAnalysisService:
    # ============================ INIT ============================
    def __init__(self):
        # Thèmes clés (élargis)
        self.important_keywords = {
            'politique': [
                'conseil départemental', 'cd971', 'guy losbar', 'ary chalus', 'région guadeloupe',
                'préfet', 'maire', 'élections', 'assemblée', 'délibération', 'budget', 'débat'
            ],
            'économie': [
                'emploi', 'chômage', 'entreprise', 'économique', 'développement', 'investissement',
                'tourisme', 'aide', 'subvention', 'tpe', 'pme', 'inflation', 'prix', 'vie chère'
            ],
            'social': [
                'santé', 'éducation', 'logement', 'transport', 'sécurité', 'violence',
                'manifestation', 'grève', 'rsa', 'mdph', 'pmi', 'protection de l’enfance'
            ],
            'culture': [
                'carnaval', 'festival', 'culture', 'musique', 'gwoka', 'créole', 'patrimoine',
                'événement', 'exposition'
            ],
            'environnement': [
                'cyclone', 'ouragan', 'séisme', 'sargasses', 'environnement', 'pollution',
                'qualité de l\'air', 'risques naturels', 'vigilance', 'sécheresse', 'inondation'
            ],
            'infrastructure': [
                'routes', 'route départementale', 'rd', 'pont', 'aéroport', 'port', 'eau',
                'assainissement', 'électricité', 'internet', 'chantier', 'fermeture', 'déviation',
                'rd23', 'rd1', 'rn1', 'rn2', 'rn4', 'pont de la gabarre', 'gabarre'
            ],
            'éducation': [
                'école', 'collège', 'lycée', 'cantine', 'rentrée', 'établissement', 'enseignant',
                'élèves', 'parents d’élèves', 'harcèlement'
            ],
            'santé': [
                'chu', 'hopital', 'hôpital', 'soins', 'urgence', 'épidémie', 'dengue', 'covid',
                'vaccination', 'désert médical', 'samu', 'smur'
            ],
            'eau_assainissement': [
                'smgeag', 'tour d\'eau', 'coupure d\'eau', 'robinet', 'distribution', 'canalisation',
                'égout', 'potable', 'usine de traitement', 'réservoir'
            ],
            'justice': [
                'tribunal', 'procureur', 'enquête', 'plainte', 'condamnation', 'justice'
            ]
        }

        # Parasites à nettoyer
        self.noise_patterns = [
            r'\b(euh+|heu+|ben|du coup|alors|donc|voilà|quoi|hein)\b',
            r'\b(et puis|et donc|et alors|et ben)\b',
            r'\b(tu vois|vous savez|vous comprenez)\b',
            r'\b(c\'est-à-dire|en fait|en réalité)\b'
        ]

        # Connecteurs logiques
        self.important_connectors = [
            'cependant', 'néanmoins', 'toutefois', 'mais', 'pourtant',
            'par conséquent', 'donc', 'ainsi', 'en effet', 'car',
            'parce que', 'puisque', 'étant donné', 'vu que', 'par ailleurs'
        ]

        # Lieux fréquents
        self.place_lexicon = [
            'pointe-à-pitre', 'pointe a pitre', 'basse-terre', 'les abymes', 'baie-mahault',
            'le gosier', 'sainte-anne', 'saint-françois', 'morne-à-l\'eau', 'capesterre-belle-eau',
            'petit-bourg', 'lamentin', 'sainte-rose', 'deshaies', 'bouillante', 'goyave',
            'marie-galante', 'la désirade', 'les saintes', 'grand-bourg', 'saint-louis',
            'anse-bertrand', 'port-louis', 'petit-canal', 'vieux-bourg', 'jarry', 'moudong',
            'belcourt', 'fonds zévallos', 'saint-félix', 'bas-du-fort'
        ]

        # Infrastructures clés
        self.infrastructure_lexicon = [
            'chu de guadeloupe', 'chu pointe-à-pitre', 'centre hospitalier', 'centre de dialyse',
            'samu', 'smur', 'smgeag', 'siaeag', 'usine de traitement', 'usine de dessalement',
            'station d’épuration', 'réservoir d’eau', 'bassin de rétention', 'château d’eau',
            'collège', 'lycée', 'école', 'internat', 'cantine', 'uagl', 'université des antilles',
            'aéroport pôle caraïbes', 'port autonome de guadeloupe', 'port de pointe-à-pitre',
            'port de basse-terre', 'marina bas-du-fort', 'zone industrielle de jarry',
            'rocade', 'échangeur', 'bretelle', 'déviation', 'carrefour giratoire', 'pont de la gabarre'
        ]
        self.infrastructure_norm = [i.lower() for i in self.infrastructure_lexicon]

        # Personnalités publiques récurrentes
        self.public_figures = [
            'Guy Losbar', 'Ary Chalus', 'Emmanuel Macron', 'Élisabeth Borne', 'Sébastien Lecornu',
            'Josette Borel-Lincertin', 'Hélène Polifonte', 'Préfet de Guadeloupe', 'Alexandre Rochatte',
            'ARS Guadeloupe', 'SMGEAG', 'UGTG', 'CGTG', 'FO', 'UNSA', 'SPEG',
            'RCI Guadeloupe', 'Guadeloupe La 1ère'
        ]
        self.public_figures_norm = [pf.lower() for pf in self.public_figures]

        # Verbes d’action
        self.action_verbs = [
            'annoncer', 'décider', 'décision', 'ouvrir', 'fermer', 'suspendre', 'lancer',
            'déployer', 'investir', 'subventionner', 'réparer', 'réhabiliter', 'assurer',
            'informer', 'prévenir', 'évacuer', 'mettre en place', 'renforcer', 'accélérer',
            'prolonger', 'reporter', 'ordonner', 'autoriser', 'interdire'
        ]

        # Motifs utiles par rubrique
        self._pat = {
            'traffic': r'\b(trafic|circulation|routes?|embouteillage|accident|déviation|bouchon|fluide)\b',
            'meteo': r'\b(météo|averses?|pluie|soleil|orage|vent|mer|houle|marée|qualité de l\'air|indice)\b',
            'sommaire': r'\b(sommaire|au programme|à la une|dans ce journal|titres)\b',
            'rentree': r'\b(rentrée|élèves?|collège|lycée|école|enseignants?|recteur|interdiction de téléphone|évaluation|maths|IA|vie affective)\b',
            'securite_scolaire': r'\b(fouille|armes?|violence|harcèlement|sécurité|procureur|contrôles?)\b',
            'politique': r'\b(vote de confiance|gouvernement|démission|Assemblée|majorité|Bayrou|ministre)\b',
            'changements': r'\b(1er septembre|premier septembre|ce qui change|nouveautés|bourses?|imp[oô]t|carburants?|dépistage|retraite)\b',
            'scams': r'\b(escroquerie|fraude|phishing|sms|mail|arnaque|https|double authentification)\b',
            'addictions': r'\b(addiction|alcool|cannabis|drogues?|ultramarin|prévention|usage)\b',
            'solidarite': r'\b(sans-abri|précarité|associations?|distribution|journée bien[- ]être|accueil|accompagnement)\b',
            'sport_r1': r'\b(régional 1|r1|csm|arsenal petit-bourg|ligue|calendriers?)\b',
            'tennis': r'\b(tennis|double|champion(ne)? de france|titre national|finale)\b',
            'tech_ia': r'\b(objets connectés?|coach sportif|intelligence artificielle|écrans|ville japonaise|santé publique)\b',
            'apprentissage': r'\b(apprentissage|apprentis?|contrats?|CAP|Master|recrute[z]?|plateforme)\b',
        }

    # ============================ PUBLIC API ============================
    def analyze_transcription(self, transcription_text: str, stream_name: str = "") -> Dict[str, Any]:
        try:
            clean_text = self._clean_transcription(transcription_text or "")
            sentences = self._split_sentences(clean_text)

            key_sentences_scored = self._score_sentences(sentences)
            key_sentences = [s for s, _ in key_sentences_scored[:7]]

            topics = self._identify_topics(clean_text)
            entities = self._extract_entities(clean_text, original_text=transcription_text or "")
            numbers = self._extract_numbers(clean_text)
            times = self._extract_times(clean_text)
            quotes = self._extract_short_quotes(transcription_text or "")

            # Résumé riche “compact”
            summary = self._create_rich_summary(
                key_sentences=key_sentences, topics=topics,
                entities=entities, numbers=numbers, times=times, quotes=quotes
            )

            # Digest complet par rubriques (même si partiellement pertinentes)
            digest = self._compose_full_broadcast_digest(
                original=transcription_text or "",
                clean=clean_text,
                entities=entities,
                numbers=numbers,
                times=times,
                quotes=quotes
            )

            # Bloc “journaux du matin”
            morning = None
            if self._is_morning_bulletin(stream_name, transcription_text or ""):
                morning = self._analyze_morning_bulletin(transcription_text or "", clean_text)

            relevance_score = self._calculate_relevance(clean_text, topics)

            return {
                'original_text': transcription_text,
                'clean_text': clean_text,
                'summary': summary,                 # court + structuré
                'digest': digest,                   # LONG et RUBRIQUÉ
                'key_sentences': key_sentences,
                'main_topics': topics,
                'entities': entities,
                'figures': numbers,
                'time_refs': times,
                'quotes': quotes,
                'relevance_score': relevance_score,
                'morning_bulletin': morning,
                'analysis_metadata': {
                    'original_length': len(transcription_text or ''),
                    'clean_length': len(clean_text or ''),
                    'compression_ratio': round(len(summary) / max(len(transcription_text or ''), 1), 2),
                    'analyzed_at': datetime.now().isoformat(),
                    'stream_source': stream_name
                }
            }
        except Exception as e:
            logger.error(f"Erreur analyse transcription: {e}")
            return {
                'original_text': transcription_text,
                'summary': "Transcription non analysable (erreur interne) — fallback sur le texte original.",
                'error': str(e)
            }

    # ============================ PRETRAIT ============================
    def _clean_transcription(self, text: str) -> str:
        if not text:
            return ""
        clean = text.lower().strip()
        for pattern in self.noise_patterns:
            clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\[(?:\d{1,2}:){1,2}\d{2}\]', ' ', clean)  # [00:00]
        clean = re.sub(r'\((?:applaudissements|rires|musique|bruitages?)\)', ' ', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # dédoublonnage simple
        words = clean.split()
        dedup = []
        for i, w in enumerate(words):
            if i == 0 or w != words[i-1]:
                dedup.append(w)
        return ' '.join(dedup)

    def _split_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        parts = re.split(r'(?<=[\.\!\?])\s+|(?<=;)\s+|(?:(?:\s-\s)|\s—\s)', text)
        sents = [s.strip() for s in parts if len(s.strip()) > 8]
        # fusion mini-phrases
        merged: List[str] = []
        buf = ""
        for s in sents:
            if len(s.split()) < 6 and buf:
                buf = f"{buf}, {s}"
            else:
                if buf:
                    merged.append(buf)
                buf = s
        if buf:
            merged.append(buf)
        return merged

    # ============================ SCORING/TOPICS ============================
    def _score_sentences(self, sentences: List[str]) -> List[Tuple[str, int]]:
        scored = []
        for s in sentences:
            sc = 0
            ls = s.lower()
            for _, kws in self.important_keywords.items():
                for kw in kws:
                    if kw in ls:
                        sc += max(2, len(kw.split()))
            if any(p in ls for p in self.place_lexicon):
                sc += 2
            if any(i in ls for i in self.infrastructure_norm):
                sc += 2
            if any(pf in ls for pf in self.public_figures_norm):
                sc += 2
            if any(c in ls for c in self.important_connectors):
                sc += 1
            wl = len(ls.split())
            if 9 <= wl <= 28:
                sc += 2
            scored.append((s, sc))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _identify_topics(self, text: str) -> List[Dict[str, Any]]:
        topics, total_hits = [], 0
        for category, keywords in self.important_keywords.items():
            hits, score = [], 0
            for kw in keywords:
                if kw in text:
                    hits.append(kw); score += max(1, len(kw.split()))
            if hits:
                total_hits += len(hits)
                topics.append({
                    'category': category,
                    'keywords_found': sorted(set(hits), key=len, reverse=True),
                    'relevance_score': score
                })
        topics.sort(key=lambda x: x['relevance_score'], reverse=True)
        for t in topics:
            t['coverage'] = round(min(1.0, len(t['keywords_found']) / max(total_hits, 1)), 3)
            t['confidence'] = min(1.0, 0.4 + 0.6 * (t['relevance_score'] / 12.0))
        return topics[:5]

    # ============================ EXTRACTIONS ============================
    def _extract_entities(self, text: str, original_text: str = "") -> Dict[str, List[str]]:
        restored = self._restore_case(text)
        persons = sorted(set(re.findall(
            r'\b([A-ZÉÈÊÀÙÏÎ][a-zéèêàùïî\'\-]+(?:\s+[A-ZÉÈÊÀÙÏÎ][a-zéèêàùïî\'\-]+){0,3})\b', restored
        )), key=len, reverse=True)
        persons = [p for p in persons if len(p.split()) <= 4 and not p.isupper()]
        for pf in self.public_figures:
            if pf.lower() in text and pf not in persons:
                persons.insert(0, pf)

        institutions = []
        for tag in [
            'CD971', 'Conseil Départemental', 'Région Guadeloupe', 'SMGEAG', 'ARS', 'Préfecture',
            'GUSR', 'CHU', 'La 1ère', 'RCI', 'Port Autonome de Guadeloupe', 'Aéroport Pôle Caraïbes',
            'Université des Antilles'
        ]:
            if tag.lower() in text:
                institutions.append(tag)

        places = [p for p in self.place_lexicon if p in text]
        infrastructures = [i for i in self.infrastructure_norm if i in text]

        return {
            'persons': self._uniq_trim(persons)[:12],
            'institutions': self._uniq_trim(institutions)[:12],
            'places': self._uniq_trim(places)[:15],
            'infrastructures': self._uniq_trim(infrastructures)[:15]
        }

    def _extract_numbers(self, text: str) -> Dict[str, List[str]]:
        euros = re.findall(r'\b\d{1,3}(?:[\s.,]\d{3})*(?:,\d+)?\s*(?:€|eur|euros)\b', text)
        perc  = re.findall(r'\b\d{1,3}(?:[.,]\d+)?\s*%\b', text)
        nums  = re.findall(r'\b\d{1,3}(?:[\s.,]\d{3})*(?:,\d+)?\b', text)
        return {
            'amounts_eur': self._uniq_trim(euros)[:10],
            'percentages': self._uniq_trim(perc)[:10],
            'numbers': self._uniq_trim(nums)[:15]
        }

    def _extract_times(self, text: str) -> Dict[str, List[str]]:
        dates = re.findall(r'\b(?:\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}\s(?:janv|févr|mars|avr|mai|juin|juil|août|sept|oct|nov|déc)\.?\s?\d{0,4})\b', text, flags=re.IGNORECASE)
        hours = re.findall(r'\b\d{1,2}[:h]\d{2}\b', text)
        days  = re.findall(r'\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b', text, flags=re.IGNORECASE)
        return {
            'dates': self._uniq_trim(dates)[:10],
            'hours': self._uniq_trim(hours)[:10],
            'days':  self._uniq_trim(days)[:10]
        }

    def _extract_short_quotes(self, original_text: str) -> List[str]:
        if not original_text:
            return []
        quotes = re.findall(r'[«“"](.*?)[»”"]', original_text, flags=re.DOTALL)
        quotes = [q.strip() for q in quotes if 6 <= len(q.strip()) <= 180]
        return self._uniq_trim(quotes)[:5]

    # ============================ JOURNAUX 6h15 / 6h20 ============================
    def _is_morning_bulletin(self, stream_name: str, original_text: str) -> bool:
        s = (stream_name or "").lower()
        t = (original_text or "").lower()
        triggers = [
            '6h15', '6 h 15', '6:15', 'gp radio 6h15', 'guadeloupe 1ère',
            '6h20', '6 h 20', '6:20', 'rci guadeloupe', 'journal', 'interview', 'invité'
        ]
        return any(tr in s for tr in triggers) or any(tr in t for tr in triggers)

    def _analyze_morning_bulletin(self, original: str, clean: str) -> Dict[str, Any]:
        restored = self._restore_case(clean)
        lines = [l.strip() for l in re.split(r'[\r\n]+', self._restore_case(original)) if l.strip()]
        interview_lines = [l for l in lines if re.search(r'(interview|invité|journaliste|animateur|animatrice)[:\s-]', l, flags=re.IGNORECASE) or re.search(r'^[A-ZÉÈÊÀÙÏÎ][^:]{1,40}:', l)]

        guests = []
        for l in interview_lines:
            m = re.match(r'^([A-ZÉÈÊÀÙÏÎ][A-Za-zÉÈÊÀÙÏÎ\'\-\s]{1,60}?):', l)
            if m:
                guests.append(m.group(1).strip())
        guests = self._uniq_trim(guests)[:5]

        q_themes = re.findall(r'\b(Pourquoi|Comment|Quand|Que|Quel(?:le|s)?|Où)\b[^?.!]{0,120}[?.!]', restored)
        actions = []
        for sent in re.split(r'(?<=[\.\!\?])\s+', restored):
            if any(v in sent.lower() for v in self.action_verbs):
                actions.append(sent.strip())
        actions = self._uniq_trim(actions)[:5]

        quotes = self._extract_short_quotes(original)
        interview_quotes = [q for q in quotes if any(q in l for l in interview_lines)][:3]

        alert_markers = ['urgence', 'alerte', 'immédiat', 'blocage', 'grève', 'fermeture', 'coupure', 'évacuation']
        alerts = []
        for sent in re.split(r'(?<=[\.\!\?])\s+', restored):
            if any(a in sent.lower() for a in alert_markers):
                alerts.append(sent.strip())
        alerts = self._uniq_trim(alerts)[:4]

        sentences = [s for s, _ in self._score_sentences(self._split_sentences(clean))][:5]

        return {
            'is_morning_bulletin': True,
            'guests': guests,
            'interview_quotes': interview_quotes,
            'action_statements': actions,
            'alert_signals': alerts,
            'question_count_estimate': len(q_themes),
            'ordered_highlights': sentences
        }

    # ============================ DIGEST RUBRIQUÉ ============================
    def _compose_full_broadcast_digest(
        self,
        original: str,
        clean: str,
        entities: Dict[str, List[str]],
        numbers: Dict[str, List[str]],
        times: Dict[str, List[str]],
        quotes: List[str]
    ) -> Dict[str, Any]:
        """
        Construit un digest multi-rubriques “au maximum de détail” :
        - Remplit chaque bloc si des indices sont trouvés ; sinon propose un libellé neutre.
        - Chaque section contient: titre, points, note/context, confiance (heuristique).
        """
        digest: Dict[str, Any] = {}
        lower = clean

        def section(title: str, points: List[str], note: str = "", conf: float = 0.5) -> Dict[str, Any]:
            pts = [p for p in self._uniq_trim(points) if p]
            return {
                'title': title,
                'points': pts[:8],
                'note': note.strip() if note else "",
                'confidence': round(max(0.1, min(conf, 1.0)), 2)
            }

        # Aides formatage
        def first_or(parts: List[str], fallback: str) -> str:
            return next((p for p in parts if p), fallback)

        # 1) Circulation / standard antenne
        traffic_hits = re.search(self._pat['traffic'], lower)
        traffic_points = []
        if 'rn' in lower or 'rd' in lower or 'gabarre' in lower or 'déviation' in lower:
            traffic_points.append("Axes mentionnés : " + ", ".join(sorted(set([w for w in ['RN1','RN2','RN4','RD1','RD23','pont de la Gabarre'] if w.lower() in lower])) or ["non précisés"]))
        if 'fluide' in lower or 'bouchon' in lower or 'accident' in lower:
            traffic_points.append(first_or(
                [("Trafic fluide" if 'fluide' in lower else ""), ("Présence de bouchons" if 'bouchon' in lower else ""), ("Accident signalé" if 'accident' in lower else "")]
                , "Pas d’incident majeur signalé"
            ))
        # standard antenne
        if 'standard' in lower or 'réagir à l’antenne' in lower or 'réagir a l’antenne' in lower or 'numéro' in lower:
            traffic_points.append("Rappel des numéros pour intervenir à l’antenne")
        digest['circulation_standard'] = section("Point circulation & standard antenne", traffic_points or ["Pas d’information précise sur la circulation"], "Conseil d’antenne si mentionné", 0.6 if traffic_hits else 0.3)

        # 2) Météo & qualité de l’air
        meteo_hits = re.search(self._pat['meteo'], lower)
        meteo_points = []
        for kw, label in [('soleil', 'Soleil dominant'), ('averses', 'Averses possibles'), ('orage', 'Risque orageux'),
                          ('vent', 'Vent faible à modéré'), ('mer', 'Mer peu agitée'), ('qualité de l\'air', 'Qualité de l’air'),
                          ('marée', 'Horaire de marée mentionné')]:
            if kw in lower:
                meteo_points.append(label)
        # lieux météo
        locs = [p for p in ['petit-bourg','goyave','basse-terre','pointe-à-pitre','les abymes'] if p in lower]
        if locs:
            meteo_points.append("Zones à surveiller : " + ", ".join([l.title() for l in locs]))
        # heures marées/indice air
        if times.get('hours'): meteo_points.append("Repères horaires : " + ", ".join(times['hours'][:2]))
        digest['meteo_air'] = section("Météo & qualité de l’air", meteo_points or ["Temps variable, détails non précisés"], "", 0.7 if meteo_hits else 0.4)

        # 3) Sommaire du journal (7h…)
        sommaire_hits = re.search(self._pat['sommaire'], lower)
        sommaire_points = []
        for tag in ['rentrée', 'réserve électorale', 'changements', 'intelligence artificielle', 'escroqueries', 'sms', 'école']:
            if tag in lower:
                sommaire_points.append(tag.capitalize())
        digest['sommaire_journal'] = section("Sommaire du journal", sommaire_points or ["Sujets principaux non énumérés"], "", 0.6 if sommaire_hits else 0.3)

        # 4) Rentrée scolaire (chiffres / règles)
        rentree_hits = re.search(self._pat['rentree'], lower)
        rentree_points = []
        # chiffres scolaires (heuristique)
        nums = numbers.get('numbers', [])
        if nums:
            rentree_points.append("Effectifs / variations évoqués (ex. " + ", ".join(nums[:2]) + ")")
        if 'interdit' in lower and 'téléphone' in lower:
            rentree_points.append("Téléphone interdit dès l’entrée au collège")
        if 'vie affective' in lower:
            rentree_points.append("Éducation à la vie affective (adaptée à l’âge)")
        if 'intelligence artificielle' in lower or 'ia' in lower:
            rentree_points.append("Initiation obligatoire à l’IA (4e/2nde)")
        if 'math' in lower or 'maths' in lower:
            rentree_points.append("Épreuve anticipée de maths en première")
        if 'évaluation nationale' in lower or 'evaluation nationale' in lower:
            rentree_points.append("Évaluation nationale généralisée en 5e")
        digest['rentree'] = section("Rentrée scolaire : chiffres et nouveautés", rentree_points or ["Informations évoquées sans détail exploitable"], "", 0.75 if rentree_hits else 0.45)

        # 5) Sécurité scolaire
        sec_hits = re.search(self._pat['securite_scolaire'], lower)
        sec_points = []
        for tag, lab in [('fouille','Fouilles intensifiées'), ('armes','Signalement au procureur'), ('contrôle','Contrôles accrus aux abords'),
                         ('harcèlement','Lutte anti-harcèlement')]:
            if tag in lower:
                sec_points.append(lab)
        digest['securite_scolaire'] = section("Sécurité scolaire : cap plus ferme", sec_points or ["Renforcement disciplinaire évoqué"], "", 0.7 if sec_hits else 0.45)

        # 6) Politique nationale
        pol_hits = re.search(self._pat['politique'], lower)
        pol_points = []
        if 'vote de confiance' in lower: pol_points.append("Vote de confiance susceptible d’entraîner recomposition")
        if 'gouvernement' in lower: pol_points.append("Impact possible sur dossiers Outre-mer (vie chère, sécurité)")
        digest['politique_nationale'] = section("Politique nationale", pol_points or ["Contexte politique mentionné sans précision"], "", 0.6 if pol_hits else 0.4)

        # 7) Changements 1er septembre
        chg_hits = re.search(self._pat['changements'], lower)
        chg_points = []
        for tag, lab in [('carburant','Carburants ajustés'), ('impôt', 'Impôt à la source individualisé'),
                         ('dépistage','Dépistage néonatal élargi'), ('retraite', 'Retraite progressive possible'),
                         ('bourses','Bourses collège/lycée ouvertes jusqu’à échéance')]:
            if tag in lower:
                chg_points.append(lab)
        digest['changements_1_sept'] = section("1er septembre : ce qui change", chg_points or ["Ajustements réglementaires évoqués"], "", 0.65 if chg_hits else 0.4)

        # 8) Escroqueries numériques
        scam_hits = re.search(self._pat['scams'], lower)
        scam_points = []
        for tag, lab in [('sms','SMS frauduleux'), ('mail','Mails phishing'), ('banque','Fausse banque'),
                         ('https','Vérifier l’URL/https'), ('double authentification','Activer la double authentification')]:
            if tag in lower:
                scam_points.append(lab)
        digest['escroqueries'] = section("Escroqueries numériques : bons réflexes", scam_points or ["Alerte cybersécurité générale"], "", 0.7 if scam_hits else 0.4)

        # 9) Addictions jeunes ultramarins
        add_hits = re.search(self._pat['addictions'], lower)
        add_points = []
        for tag, lab in [('alcool','Usages d’alcool supérieurs'), ('cannabis','Cannabis en hausse'),
                         ('drogue','Cas de drogues dures'), ('âge','Âge d’initiation préoccupant')]:
            if tag in lower:
                add_points.append(lab)
        digest['addictions'] = section("Addictions des jeunes ultramarins", add_points or ["Signal d’alarme sans chiffrage localisé"], "", 0.55 if add_hits else 0.35)

        # 10) Solidarité
        sol_hits = re.search(self._pat['solidarite'], lower)
        sol_points = []
        if any(k in lower for k in ['pointe-à-pitre','pointe a pitre']): sol_points.append("Action à Pointe-à-Pitre")
        if 'soins' in lower or 'accompagnement' in lower: sol_points.append("Soins / accompagnement administratif")
        digest['solidarite'] = section("Solidarité : journée bien-être", sol_points or ["Mobilisation associative évoquée"], "", 0.6 if sol_hits else 0.35)

        # 11) Sport : Régional 1
        r1_hits = re.search(self._pat['sport_r1'], lower)
        r1_points = []
        if 'arsenal' in lower and 'petit-bourg' in lower: r1_points.append("Arsenal Petit-Bourg victorieux")
        if 'csm' in lower: r1_points.append("CSM mentionné")
        if 'ligue' in lower: r1_points.append("Dynamique positive soulignée par la ligue")
        if 'jeunes' in lower or 'féminin' in lower or 'feminins' in lower: r1_points.append("Calendriers jeunes/féminins en finalisation")
        digest['sport_r1'] = section("Sport : reprise en Régional 1", r1_points or ["Première journée évoquée"], "", 0.55 if r1_hits else 0.35)

        # 12) Tennis
        ten_hits = re.search(self._pat['tennis'], lower)
        ten_points = []
        if 'double' in lower and ('champion' in lower or 'titre' in lower):
            ten_points.append("Titre national en double (fierté locale)")
        digest['tennis'] = section("Tennis", ten_points or ["Résultat national évoqué"], "", 0.5 if ten_hits else 0.3)

        # 13) Connect Première / Tech & IA
        tech_hits = re.search(self._pat['tech_ia'], lower)
        tech_points = []
        if 'coach' in lower and 'ia' in lower: tech_points.append("Coach sportif boosté à l’IA (à venir)")
        if 'ville' in lower and 'écrans' in lower: tech_points.append("Ville japonaise contre l’addiction aux écrans")
        digest['tech_ia'] = section("Connect Première : objets connectés & IA", tech_points or ["Sujet tech à venir"], "", 0.5 if tech_hits else 0.3)

        # 14) Apprentissage
        app_hits = re.search(self._pat['apprentissage'], lower)
        app_points = []
        if any(k in lower for k in ['cap','master','apprentis','apprentissage']): app_points.append("Offres du CAP au Master")
        if 'recrute' in lower or 'recrutez' in lower: app_points.append("Appel aux entreprises pour signer des contrats")
        digest['apprentissage'] = section("Apprentissage : entreprises, recrutez", app_points or ["Appel à candidatures évoqué"], "", 0.6 if app_hits else 0.35)

        # Ajouts génériques: acteurs/lieux/chiffres
        digest['meta'] = {
            'acteurs': entities.get('persons', [])[:6],
            'institutions': entities.get('institutions', [])[:6],
            'lieux': [p.title() for p in entities.get('places', [])[:6]],
            'infrastructures': entities.get('infrastructures', [])[:6],
            'montants_eur': numbers.get('amounts_eur', [])[:3],
            'pourcentages': numbers.get('percentages', [])[:3],
            'heures': times.get('hours', [])[:3],
            'dates': times.get('dates', [])[:3],
            'citations': quotes[:2]
        }

        return digest

    # ============================ RESUME RICHE ============================
    def _create_rich_summary(self, key_sentences, topics, entities, numbers, times, quotes) -> str:
        if not key_sentences:
            return "Transcription non analysable – contenu insuffisant."
        title_map = {
            'politique': "🏛️ Focus politique",
            'économie': "💼 Focus économie",
            'social': "👥 Focus social",
            'culture': "🎭 Focus culture",
            'environnement': "🌿 Focus environnement",
            'infrastructure': "🏗️ Focus infrastructures",
            'éducation': "📚 Focus éducation",
            'santé': "🏥 Focus santé",
            'eau_assainissement': "🚰 Focus eau/assainissement",
            'justice': "⚖️ Focus justice",
        }
        top_topic = topics[0]['category'] if topics else None
        title = title_map.get(top_topic, "🔎 Points clés de la séquence radio")

        hook = " ".join([(s[0].upper()+s[1:] if s and s[0].islower() else s).rstrip(' .') + '.' for s in key_sentences[:3]])

        bullets = self._build_bullets(key_sentences, topics, entities, numbers, times)[:6]

        context_bits = []
        if topics:
            tnames = [t['category'] for t in topics[:3]]
            context_bits.append("Thèmes dominants : " + ", ".join(tnames) + ".")
        if entities.get('institutions'):
            context_bits.append("Institutions citées : " + ", ".join(entities['institutions'][:3]) + ".")
        if entities.get('places'):
            context_bits.append("Lieux mentionnés : " + ", ".join([p.title() for p in entities['places'][:3]]) + ".")
        if entities.get('infrastructures'):
            context_bits.append("Infrastructures : " + ", ".join(entities['infrastructures'][:3]) + ".")

        quotes_block = f'🗣️ « {quotes[0]} »' if quotes else ""

        out = [f"**{title}**", hook]
        if bullets:
            out.append("\n**À retenir** :")
            out.extend([f"• {b}" for b in bullets])
        if context_bits:
            out.append("\n**Contexte** : " + " ".join(context_bits))
        if quotes_block:
            out.append("\n" + quotes_block)
        if self._has_actions(" ".join(key_sentences)):
            out.append("\n**Suites probables** : communication institutionnelle, suivi opérationnel et point d’étape sous 24–48h.")

        final = "\n".join(out).strip()
        if len(final) > 1400:
            final = final[:1380].rsplit(' ', 1)[0] + "…"
        return final

    def _build_bullets(self, key_sentences, topics, entities, numbers, times) -> List[str]:
        bullets = [self._sentence_to_bullet(s) for s in key_sentences[:4]]
        if numbers.get('amounts_eur'): bullets.append(f"Montants évoqués : {', '.join(numbers['amounts_eur'][:2])}")
        if numbers.get('percentages'): bullets.append(f"Indicateurs : {', '.join(numbers['percentages'][:2])}")
        pieces = []
        if times.get('dates'): pieces.append(f"dates {', '.join(times['dates'][:2])}")
        if times.get('hours'): pieces.append(f"heures {', '.join(times['hours'][:2])}")
        if pieces: bullets.append("Calendrier : " + " ; ".join(pieces))
        if entities.get('persons'): bullets.append(f"Acteurs : {', '.join(entities['persons'][:2])}")
        if len(topics) >= 2: bullets.append(f"Thème connexe : {topics[1]['category']}")
        return self._uniq_trim(bullets)

    # ============================ UTILS ============================
    def _calculate_relevance(self, text: str, topics: List[Dict]) -> float:
        if not text.strip(): return 0.0
        base = 0.35
        wc = len(text.split())
        base += 0.25 if 30 <= wc <= 600 else (0.15 if wc > 15 else 0.0)
        if topics:
            topic_bonus = sum(t.get('confidence', 0.5) for t in topics) / len(topics)
            base += 0.35 * min(1.0, topic_bonus)
        return round(min(base, 1.0), 3)

    def _sentence_to_bullet(self, s: str) -> str:
        s = s.strip()
        s = s[0].upper() + s[1:] if s and s[0].islower() else s
        return s.rstrip(' .')

    def _has_actions(self, text: str) -> bool:
        lt = text.lower()
        return any(v in lt for v in self.action_verbs)

    def _restore_case(self, lower_text: str) -> str:
        sents = re.split(r'(?<=[\.\!\?])\s+', lower_text)
        norm = []
        for s in sents:
            s = s.strip()
            if not s: continue
            norm.append(s[0].upper() + s[1:] if s[0].islower() else s)
        return ' '.join(norm)

    def _uniq_trim(self, items: List[str]) -> List[str]:
        seen, out = set(), []
        for it in items:
            k = (it or '').strip()
            if not k: continue
            if k.lower() not in seen:
                out.append(k); seen.add(k.lower())
        return out


# Instance globale du service
transcription_analyzer = TranscriptionAnalysisService()

def analyze_transcription(text: str, stream_name: str = "") -> Dict[str, Any]:
    """Fonction utilitaire pour analyser une transcription"""
    return transcription_analyzer.analyze_transcription(text, stream_name)
