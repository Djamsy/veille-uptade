"""
Service d'anticipation de la réaction de la population
Analyse croisée des articles, réseaux sociaux et sentiment pour prédire les réactions
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
import os
from gpt_sentiment_service import gpt_sentiment_analyzer

# Guarded import for the GPT population reaction predictor
try:
    from gpt_sentiment_service import predict_population_reaction as gpt_predict_population_reaction  # type: ignore
except Exception:
    gpt_predict_population_reaction = None  # fallback handled below


# Configuration logging
logger = logging.getLogger(__name__)

# --- Crisis themes & guardrails (evidence-informed) ---
# Sources:
# - Sargasses interventions & ports départementaux (CD971) 2021 & 2025
# - Routes départementales / travaux & fermetures (Routes de Guadeloupe)
# - Eau/assainissement via SMGEAG (compétence indirecte mais image forte)
CRISIS_THEMES = {
    'eau':               {'competence': 'indirect', 'default_gravity': 3, 'keywords': ['eau', 'robinet', 'coupure', 'distribution', 'SMGEAG', "tour d'eau"]},
    'assainissement':    {'competence': 'indirect', 'default_gravity': 3, 'keywords': ['assainissement', 'canalisation', 'égout']},
    'sargasses':         {'competence': 'direct',   'default_gravity': 2, 'keywords': ['sargasse', 'sargasses', 'algues brunes', 'H2S', 'port départemental', 'ramassage']},
    'routes':            {'competence': 'direct',   'default_gravity': 2, 'keywords': ['route départementale', 'RD', 'RN1', 'fermeture', 'déviation', 'chantier']},
    'transport_scolaire':{'competence': 'none',     'default_gravity': 2, 'keywords': ['transport scolaire', 'bus scolaire', 'car scolaire']},
    'colleges':          {'competence': 'direct',   'default_gravity': 2, 'keywords': ['collège', 'cantine', 'rentrée', 'établissement']},
    'social':            {'competence': 'direct',   'default_gravity': 3, 'keywords': ['RSA', 'MDPH', 'PMI', "protection de l'enfance", 'aide sociale']},
    'risques_naturels':  {'competence': 'indirect', 'default_gravity': 2, 'keywords': ['sécheresse', "pollution de l'air", 'sargasses', 'vigilance']},
    # nouveau thème dédié pour affiner les règles
    'cyclone':           {'competence': 'indirect', 'default_gravity': 3, 'keywords': ['cyclone', 'ouragan', 'tempête', 'dépression tropicale', 'vigilance orange', 'vigilance rouge', 'Météo-France', 'houle cyclonique']},
}

# Weight per source to dampen single-source echo-chamber
SOURCE_WEIGHTS = {
    # media brand (regex lowercased) : weight
    'rci': 0.7,
    'france\-antilles': 1.0,
    'la 1ère': 1.0,
    'karibinfo': 0.9,
}

# Thresholds
MIN_DISTINCT_SOURCES_RED = 2  # need >= 2 distinct media in 24h for red-level push
SUSTAINED_DAYS_FOR_SINGLE_SOURCE = 2  # or same source sustained at least N days

def _normalize_source_name(name: str) -> str:
    if not name:
        return 'unknown'
    return name.lower().strip()

class PopulationReactionPredictor:
    def __init__(self):
        """Initialiser le service de prédiction des réactions"""
        
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        try:
            self.client = MongoClient(MONGO_URL)
            self.db = self.client.veille_media
            
            # Collections
            self.articles_collection = self.db.articles_guadeloupe
            self.social_collection = self.db.social_posts
            self.sentiment_cache = self.db.sentiment_analysis_cache
            self.reaction_predictions = self.db.reaction_predictions
            # nouvelle collection (optionnelle) pour signaux externes (ex: météo)
            self.alerts_collection = self.db.external_alerts

            logger.info("✅ Service prédiction réactions initialisé")
        except Exception as e:
            logger.error(f"❌ Erreur connexion MongoDB prédiction: {e}")
            self.client = None

    def analyze_population_reaction(self, text: str, context: Dict = None) -> Dict[str, Any]:
        """Analyser et prédire la réaction de la population pour un texte donné"""
        try:
            if not self.client:
                return {'error': 'Service non disponible'}

            # 1. Analyse de sentiment enrichie du texte principal
            main_sentiment = gpt_sentiment_analyzer.analyze_sentiment(text)

            # Enrich themes with rule-based inference
            inferred_themes = self._infer_themes(text)
            llm_themes = (main_sentiment.get('analysis_details', {}) or {}).get('themes', [])
            all_themes = list({*inferred_themes, *[t for t in llm_themes if isinstance(t, str)]})
            if 'analysis_details' not in main_sentiment:
                main_sentiment['analysis_details'] = {}
            main_sentiment['analysis_details']['themes'] = all_themes

            # 2. Rechercher des contenus similaires dans les articles récents
            similar_articles = self._find_similar_content(text, collection=self.articles_collection, limit=25)
            # 3. Rechercher des contenus similaires dans les réseaux sociaux
            similar_social = self._find_similar_content(text, collection=self.social_collection, limit=25)

            # Distinct source stats (last 24h)
            article_source_stats = self._distinct_source_stats(similar_articles)
            social_source_stats = self._distinct_source_stats(similar_social, field_name='author')

            # 4. Analyser les tendances historiques
            historical_trends = self._analyze_historical_trends(main_sentiment)

            # 5. Identifier les groupes d'influence
            stakeholder_influence = self._analyze_stakeholder_influence(main_sentiment)

            # Guardrails: compute recurrence & multi-source strength
            recurrence = self._compute_recurrence_score(article_source_stats)
            competence = self._map_competence(all_themes)

            # 🔔 Signaux externes (météo, etc.)
            external = self._external_signals()

            # 📈 Escalade auto si thème cyclone + vigilance orange/rouge
            if 'cyclone' in (all_themes or []):
                lvl = (external.get('meteo_alert_level') or external.get('meteo_db_alert', {}).get('level') or 'none').lower()
                if any(x in lvl for x in ['orange', 'rouge']):
                    recurrence = {
                        'level': 'high',
                        'distinct_sources': max(recurrence.get('distinct_sources', 0), 1),
                        'weighted_24h': max(recurrence.get('weighted_24h', 0.0), 2.5),
                        'reason': 'meteo_alert'
                    }

            # 6. Prédire les réactions par segment de population
            reaction_prediction = self._predict_reactions_by_segment(
                main_sentiment, similar_articles, similar_social,
                context={**(context or {}), 'recurrence': recurrence, 'competence': competence}
            )

            # 7. Générer des recommandations/suggestions
            strategic_recommendations = self._generate_strategic_recommendations(
                main_sentiment, reaction_prediction, stakeholder_influence
            )

            # 8. Créer la réponse complète
            result = {
                'text_analyzed': text[:200] + "..." if len(text) > 200 else text,
                'main_sentiment': main_sentiment,
                'population_reaction_forecast': {
                    'overall_reaction': reaction_prediction['overall'],
                    'by_demographic': reaction_prediction['demographics'],
                    'by_region': reaction_prediction['regions'],
                    'intensity_level': reaction_prediction['intensity'],
                    'polarization_risk': reaction_prediction['polarization_risk']
                },
                'supporting_data': {
                    'similar_articles': len(similar_articles),
                    'similar_social_posts': len(similar_social),
                    'articles_sample': similar_articles[:3],
                    'social_sample': similar_social[:5],
                    'distinct_article_sources': article_source_stats,
                    'distinct_social_sources': social_source_stats,
                },
                'historical_context': historical_trends,
                'influence_factors': stakeholder_influence,
                'policy_context': {
                    'themes': all_themes,
                    'department_competence': competence,
                    'recurrence': recurrence,
                    'external_signals': external,  # <-- ajouté
                },
                'suggestions': strategic_recommendations,  # champ préféré
                'strategic_recommendations': strategic_recommendations,
                'confidence_level': self._calculate_confidence(similar_articles, similar_social),
                'analysis_timestamp': datetime.now().isoformat()
            }

            # Confidence adjustment: penalize single-source spikes
            if result['supporting_data'].get('distinct_article_sources', {}).get('distinct_count', 0) < 2:
                result['confidence_level'] = max(0.3, result['confidence_level'] - 0.2)

            # Sauvegarder la prédiction
            self._save_prediction(result)

            logger.info(f"✅ Prédiction réaction générée: {reaction_prediction['overall']} (confiance: {result['confidence_level']})")
            return result

        except Exception as e:
            logger.error(f"❌ Erreur prédiction réaction: {e}")
            return {'error': str(e)}

    def _external_signals(self) -> Dict[str, Any]:
        """Lire les signaux externes (ex: vigilance météo de Météo-France)."""
        signals: Dict[str, Any] = {}
        try:
            # variable d'env prioritaire si présente
            lvl = os.environ.get('METEO_ALERT_LEVEL')
            if lvl:
                signals['meteo_alert_level'] = lvl.lower()

            # lecture en base (document le plus récent type 'meteo' sur 3 jours)
            try:
                if hasattr(self, 'alerts_collection') and self.alerts_collection is not None:
                    since = datetime.now() - timedelta(days=3)
                    doc = self.alerts_collection.find_one(
                        {'type': 'meteo', 'created_at': {'$gte': since}},
                        sort=[('created_at', -1)]
                    )
                    if doc:
                        created = doc.get('created_at')
                        created_iso = created.isoformat() if hasattr(created, 'isoformat') else created
                        signals['meteo_db_alert'] = {
                            'level': (doc.get('level') or '').lower(),
                            'created_at': created_iso,
                            'source': doc.get('source') or 'unknown'
                        }
            except Exception:
                # on ne bloque pas la chaîne si la collection n'existe pas
                pass
        except Exception:
            return signals
        return signals

    def _find_similar_content(self, text: str, collection, limit: int = 5) -> List[Dict]:
        """Trouver du contenu similaire par mots-clés"""
        try:
            # Extraire les mots-clés importants du texte
            keywords = self._extract_keywords(text) or []
            regex = '|'.join([k for k in keywords if isinstance(k, str) and k.strip()])
            if not regex:
                return []

            # Recherche par mots-clés dans les titres/contenus
            query = {
                '$or': [
                    {'title': {'$regex': regex, '$options': 'i'}},
                    {'content': {'$regex': regex, '$options': 'i'}}
                ],
                'date': {'$gte': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}
            }

            results = list(collection.find(query, {'_id': 0}).sort('scraped_at', -1).limit(limit))
            return results

        except Exception as e:
            logger.warning(f"Erreur recherche contenu similaire: {e}")
            return []

    def _distinct_source_stats(self, items: List[Dict], field_name: str = 'source') -> Dict[str, Any]:
        """Compute distinct sources and weighted score over last 24h."""
        try:
            now = datetime.now()
            recent = []
            for it in items:
                # accept several date fields; fallback to scraped_at
                ds = it.get('date') or it.get('published_at') or it.get('scraped_at')
                try:
                    d = datetime.fromisoformat(ds) if isinstance(ds, str) else ds
                except Exception:
                    d = None
                if not d or now - d <= timedelta(days=1):
                    recent.append(it)
            sources = {}
            for it in recent:
                src = _normalize_source_name(it.get(field_name) or it.get('source') or '')
                sources[src] = sources.get(src, 0) + 1
            weighted = 0.0
            for s, n in sources.items():
                w = 1.0
                for key, val in SOURCE_WEIGHTS.items():
                    if key in s:
                        w = val
                        break
                # count first article full, subsequent at 0.5 weight
                if n >= 1:
                    weighted += w  # first one
                    if n > 1:
                        weighted += (n - 1) * 0.5 * w
            return {
                'distinct_count': len(sources),
                'by_source': sources,
                'weighted_score_24h': round(weighted, 2)
            }
        except Exception:
            return {'distinct_count': 0, 'by_source': {}, 'weighted_score_24h': 0.0}

    def _infer_themes(self, text: str) -> List[str]:
        """Infer themes from keyword maps."""
        t = text.lower()
        found = []
        for theme, meta in CRISIS_THEMES.items():
            if any(kw.lower() in t for kw in meta['keywords']):
                found.append(theme)
        return found

    def _map_competence(self, themes: List[str]) -> Dict[str, Any]:
        """Map themes to department competence levels and gravity."""
        out = []
        overall = 'none'
        max_grav = 0
        for th in themes or []:
            meta = CRISIS_THEMES.get(th)
            if not meta:
                continue
            out.append({'theme': th, 'competence': meta['competence'], 'default_gravity': meta['default_gravity']})
            if meta['competence'] == 'direct':
                overall = 'direct'
            elif meta['competence'] == 'indirect' and overall != 'direct':
                overall = 'indirect'
            max_grav = max(max_grav, meta['default_gravity'])
        return {'overall_competence': overall, 'details': out, 'max_default_gravity': max_grav}

    def _compute_recurrence_score(self, src_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Compute recurrence score factoring distinct sources and sustained single-source."""
        distinct = src_stats.get('distinct_count', 0)
        weighted = src_stats.get('weighted_score_24h', 0.0)
        level = 'low'
        if distinct >= MIN_DISTINCT_SOURCES_RED or weighted >= 2.5:
            level = 'high'
        elif distinct == 1 and weighted >= 1.5:
            level = 'medium'
        return {'level': level, 'distinct_sources': distinct, 'weighted_24h': weighted}

    def _extract_keywords(self, text: str) -> List[str]:
        """Extraire les mots-clés importants du texte"""
        # Mots-clés spécifiques à la Guadeloupe + risques météo
        guadeloupe_keywords = [
            'Guy Losbar', 'CD971', 'Conseil Départemental', 'Guadeloupe', 
            'Pointe-à-Pitre', 'Basse-Terre', 'budget', 'route', 'école',
            'collège', 'transport', 'social', 'aide', 'famille', 'jeune',
            'cyclone', 'ouragan', 'tempête', 'Météo-France', 'vigilance', 'houle'
        ]
        
        # Chercher les mots-clés présents dans le texte
        text_lower = text.lower()
        found_keywords = [kw for kw in guadeloupe_keywords if kw.lower() in text_lower]
        
        # Ajouter des mots significatifs (> 4 caractères)
        words = text.split()
        significant_words = [w.strip('.,!?()[]') for w in words if len(w.strip('.,!?()[]')) > 4]
        
        return found_keywords + significant_words[:5]

    def _analyze_historical_trends(self, sentiment: Dict) -> Dict[str, Any]:
        """Analyser les tendances historiques basées sur le sentiment"""
        try:
            # Rechercher des analyses similaires dans l'historique
            similar_sentiments = list(self.sentiment_cache.find({
                'sentiment_result.polarity': sentiment['polarity'],
                'analyzed_at': {'$gte': datetime.now() - timedelta(days=90)}
            }).limit(20))
            
            # Analyser les patterns
            if not similar_sentiments:
                return {'trend': 'insufficient_data', 'message': 'Pas assez de données historiques'}
            
            # Calculer les tendances
            avg_intensity = sum([
                1 if s['sentiment_result']['intensity'] == 'strong' else 
                0.5 if s['sentiment_result']['intensity'] == 'moderate' else 0.2
                for s in similar_sentiments
            ]) / len(similar_sentiments)
            
            return {
                'trend': 'increasing' if avg_intensity > 0.6 else 'stable' if avg_intensity > 0.3 else 'decreasing',
                'similar_cases': len(similar_sentiments),
                'average_intensity': round(avg_intensity, 2),
                'pattern': 'recurring' if len(similar_sentiments) > 10 else 'occasional'
            }
            
        except Exception as e:
            logger.warning(f"Erreur analyse tendances: {e}")
            return {'trend': 'unknown', 'error': str(e)}

    def _analyze_stakeholder_influence(self, sentiment: Dict) -> Dict[str, Any]:
        """Analyser l'influence des parties prenantes mentionnées"""
        try:
            personalities = sentiment['analysis_details'].get('personalities_mentioned', [])
            institutions = sentiment['analysis_details'].get('institutions_mentioned', [])
            
            # Base de données d'influence des personnalités guadeloupéennes
            influence_db = {
                'Guy Losbar': {'level': 'high', 'domains': ['politique', 'économie'], 'polarization': 'moderate'},
                'CD971': {'level': 'high', 'domains': ['administration', 'social'], 'polarization': 'low'},
                'Conseil Départemental': {'level': 'high', 'domains': ['politique', 'administration'], 'polarization': 'moderate'}
            }
            
            influences = []
            total_influence = 0
            
            for entity in personalities + institutions:
                if entity in influence_db:
                    info = influence_db[entity]
                    influences.append({
                        'entity': entity,
                        'influence_level': info['level'],
                        'domains': info['domains'],
                        'polarization_potential': info['polarization']
                    })
                    total_influence += 3 if info['level'] == 'high' else 2 if info['level'] == 'medium' else 1
            
            return {
                'mentioned_stakeholders': influences,
                'total_influence_score': total_influence,
                'high_influence_entities': [inf['entity'] for inf in influences if inf['influence_level'] == 'high'],
                'polarization_risk': 'high' if any(inf['polarization_potential'] == 'high' for inf in influences) else 'moderate'
            }
            
        except Exception as e:
            logger.warning(f"Erreur analyse influence: {e}")
            return {'error': str(e)}

    def _predict_reactions_by_segment(self, sentiment: Dict, articles: List, social: List, context: Dict = None) -> Dict[str, Any]:
        """Prédire les réactions par segment de population"""
        try:
            polarity = sentiment['polarity']
            intensity = sentiment['intensity']
            urgency = sentiment['analysis_details'].get('urgency_level', 'faible')
            recurrence = (context or {}).get('recurrence', {'level': 'low'})
            competence = (context or {}).get('competence', {'overall_competence': 'none'})
            themes = sentiment['analysis_details'].get('themes', [])

            # Calcul simple pour commencer
            base_score = 0.5 if polarity == 'positive' else -0.5 if polarity == 'negative' else 0

            # Segments simplifiés
            segments = {
                'jeunes_18_35': {
                    'reaction_score': base_score * 1.2,
                    'reaction_label': self._score_to_label(base_score * 1.2),
                    'key_concerns': ['emploi', 'formation', 'logement'],
                    'engagement_likelihood': 'élevé'
                },
                'familles': {
                    'reaction_score': base_score * 1.0,
                    'reaction_label': self._score_to_label(base_score * 1.0),
                    'key_concerns': ['éducation', 'santé', 'aide sociale'],
                    'engagement_likelihood': 'modéré'
                },
                'seniors_plus_55': {
                    'reaction_score': base_score * 0.8,
                    'reaction_label': self._score_to_label(base_score * 0.8),
                    'key_concerns': ['santé', 'retraite', 'services publics'],
                    'engagement_likelihood': 'faible'
                }
            }

            # Réactions par région simplifiées
            regions = {
                'pointe_a_pitre': {
                    'reaction_score': base_score,
                    'reaction_label': self._score_to_label(base_score),
                    'specific_concerns': ['économie', 'transport']
                },
                'basse_terre': {
                    'reaction_score': base_score * 0.9,
                    'reaction_label': self._score_to_label(base_score * 0.9),
                    'specific_concerns': ['administration', 'services']
                }
            }

            # Calculer la réaction globale
            overall_scores = [seg['reaction_score'] for seg in segments.values()]
            overall_reaction = sum(overall_scores) / len(overall_scores) if overall_scores else 0

            overall_label = (
                'très positive' if overall_reaction > 0.6 else
                'positive' if overall_reaction > 0.2 else
                'neutre' if overall_reaction > -0.2 else
                'négative' if overall_reaction > -0.6 else
                'très négative'
            )

            # Polarisation
            polarization_risk = 'élevé' if abs(overall_reaction) > 0.5 else 'modéré' if abs(overall_reaction) > 0.2 else 'faible'

            # Escalation/demotion based on recurrence & competence
            if recurrence.get('level') == 'high' and competence.get('overall_competence') in ('direct', 'indirect'):
                if polarity == 'negative' and overall_label in ('neutre', 'positive'):
                    overall_label = 'négative'
            elif recurrence.get('distinct_sources', 0) < 2 and polarity != 'negative':
                # dampen
                if overall_label == 'positive':
                    overall_label = 'neutre'

            return {
                'overall': overall_label,
                'overall_score': round(overall_reaction, 2),
                'demographics': segments,
                'regions': regions,
                'intensity': urgency,
                'polarization_risk': polarization_risk,
                'mobilization_potential': 'élevé' if intensity == 'strong' else 'modéré' if intensity == 'moderate' else 'faible',
                'recurrence': recurrence,
                'competence': competence,
            }

        except Exception as e:
            logger.error(f"Erreur prédiction par segment: {e}")
            return {
                'overall': 'neutre',
                'overall_score': 0.0,
                'demographics': {},
                'regions': {},
                'intensity': 'faible',
                'polarization_risk': 'faible',
                'mobilization_potential': 'faible',
                'recurrence': {'level': 'low', 'distinct_sources': 0, 'weighted_24h': 0.0},
                'competence': {'overall_competence': 'none', 'details': [], 'max_default_gravity': 0},
                'error': str(e)
            }

    def _predict_youth_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des jeunes (18-35 ans)"""
        base_score = 0.5 if polarity == 'positive' else -0.5 if polarity == 'negative' else 0
        
        # Les jeunes sont plus sensibles à l'emploi, l'éducation, l'environnement
        if any(t in themes for t in ['education', 'emploi', 'environnement']):
            base_score += 0.3 if polarity == 'positive' else -0.3
            
        intensity_multiplier = 1.5 if intensity == 'strong' else 1.2 if intensity == 'moderate' else 1.0
        
        return {
            'reaction_score': base_score * intensity_multiplier,
            'reaction_label': self._score_to_label(base_score * intensity_multiplier),
            'key_concerns': ['emploi', 'formation', 'logement', 'transport'],
            'engagement_likelihood': 'élevé' if abs(base_score * intensity_multiplier) > 0.4 else 'modéré'
        }

    def _predict_family_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des familles"""
        base_score = 0.3 if polarity == 'positive' else -0.3 if polarity == 'negative' else 0
        
        # Les familles sont sensibles à l'éducation, la santé, les aides sociales
        if any(t in themes for t in ['education', 'social', 'santé']):
            base_score += 0.4 if polarity == 'positive' else -0.4
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['éducation', 'santé', 'aide sociale', 'sécurité'],
            'engagement_likelihood': 'modéré'
        }

    def _predict_senior_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des seniors (55+ ans)"""
        base_score = 0.2 if polarity == 'positive' else -0.2 if polarity == 'negative' else 0
        
        # Les seniors sont sensibles à la santé, aux services publics
        if any(t in themes for t in ['santé', 'social', 'transport']):
            base_score += 0.3 if polarity == 'positive' else -0.3
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),  
            'key_concerns': ['santé', 'retraite', 'transport', 'services publics'],
            'engagement_likelihood': 'faible à modéré'
        }

    def _predict_business_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des entrepreneurs"""
        base_score = 0.6 if polarity == 'positive' else -0.6 if polarity == 'negative' else 0
        
        # Les entrepreneurs sont sensibles à l'économie, aux investissements
        if any(t in themes for t in ['économie', 'infrastructure', 'tourisme']):
            base_score += 0.4 if polarity == 'positive' else -0.4
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['économie', 'fiscalité', 'infrastructure', 'réglementation'],
            'engagement_likelihood': 'élevé'
        }

    def _predict_civil_servant_reaction(self, polarity: str, intensity: str, themes: List) -> Dict:
        """Prédire la réaction des fonctionnaires"""
        base_score = 0.1 if polarity == 'positive' else -0.1 if polarity == 'negative' else 0
        
        # Les fonctionnaires sont sensibles aux réformes administratives
        if any(t in themes for t in ['administration', 'politique']):
            base_score += 0.2 if polarity == 'positive' else -0.2
            
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'key_concerns': ['emploi public', 'réformes', 'conditions de travail'],
            'engagement_likelihood': 'faible'
        }

    def _predict_regional_reaction(self, region: str, polarity: str, themes: List) -> Dict:
        """Prédire la réaction par région"""
        base_score = 0.3 if polarity == 'positive' else -0.3 if polarity == 'negative' else 0
        
        # Ajustements par région
        if region == 'Pointe-à-Pitre':
            # Plus urbain, plus sensible à l'économie
            if 'économie' in themes:
                base_score += 0.2 if polarity == 'positive' else -0.2
        elif region == 'Rural':
            # Plus sensible à l'agriculture, l'environnement
            if any(t in themes for t in ['environnement', 'agriculture']):
                base_score += 0.3 if polarity == 'positive' else -0.3
                
        return {
            'reaction_score': base_score,
            'reaction_label': self._score_to_label(base_score),
            'specific_concerns': self._get_regional_concerns(region)
        }

    def _get_regional_concerns(self, region: str) -> List[str]:
        """Obtenir les préoccupations spécifiques par région"""
        concerns = {
            'Pointe-à-Pitre': ['économie', 'emploi', 'transport', 'sécurité'],
            'Basse-Terre': ['administration', 'services publics', 'éducation'],
            'Grande-Terre': ['tourisme', 'agriculture', 'infrastructure'],
            'Rural': ['agriculture', 'environnement', 'désenclavement', 'services']
        }
        return concerns.get(region, ['général'])

    def _assess_mobilization_potential(self, intensity: str, urgency: str, themes: List) -> str:
        """Évaluer le potentiel de mobilisation sociale"""
        mobilization_score = 0
        
        # Impact de l'intensité
        if intensity == 'strong':
            mobilization_score += 3
        elif intensity == 'moderate':
            mobilization_score += 2
        else:
            mobilization_score += 1
            
        # Impact de l'urgence
        if urgency == 'élevé':
            mobilization_score += 3
        elif urgency == 'moyen':
            mobilization_score += 2
        else:
            mobilization_score += 1
            
        # Thèmes mobilisateurs
        mobilizing_themes = ['social', 'education', 'emploi', 'transport', 'environnement']
        if any(t in themes for t in mobilizing_themes):
            mobilization_score += 2
            
        if mobilization_score >= 7:
            return 'élevé'
        elif mobilization_score >= 4:
            return 'modéré'
        else:
            return 'faible'

    def _generate_strategic_recommendations(self, sentiment: Dict, reaction: Dict, influence: Dict) -> List[str]:
        """Générer des recommandations stratégiques"""
        recommendations: List[str] = []

        # Guardrails: éviter la surréaction si une seule source et pas de négatif clair
        recurrence = (reaction or {}).get('recurrence') if isinstance(reaction, dict) else None
        polarity = sentiment['polarity']
        if isinstance(recurrence, dict) and recurrence.get('distinct_sources', 0) < 2 and polarity != 'negative':
            recommendations.append("Suggestion : suivi discret, pas de communiqué immédiat (source unique)")

        urgency = sentiment['analysis_details'].get('urgency_level', 'faible')
        polarization_risk = reaction.get('polarization_risk', 'faible')
        themes = sentiment.get('analysis_details', {}).get('themes', []) or []

        # Recommandations basées sur le sentiment
        if polarity == 'negative' and urgency == 'élevé':
            recommendations.append("Alerte : communication de crise recommandée")
            recommendations.append("Activer une cellule de gestion de crise (porte-parole + questions/réponses)")

        if polarization_risk == 'élevé':
            recommendations.append("Organiser un dialogue avec parties prenantes et relais locaux")
            recommendations.append("Adapter le message par segment de population")

        # Recommandations basées sur l'influence
        if influence.get('total_influence_score', 0) > 5:
            recommendations.append("Prise de contact ciblée avec personnalités/institutions influentes")

        # Recommandations basées sur la mobilisation
        if reaction.get('mobilization_potential', 'faible') == 'élevé':
            recommendations.append("Anticiper logistique & sécurité d'éventuels regroupements")
            recommendations.append("Ouvrir des canaux de dialogue additionnels")

        # Bloc spécifique cyclone
        if 'cyclone' in themes:
            recommendations.append("Cyclone : activer la coordination ORSEC locale (Préfecture/SDIS/collectivités)")
            recommendations.append("Pré-crise : messages pratiques (abris, RD ouvertes/fermées, numéros utiles) — MAJ 6h/12h/18h")
            recommendations.append("Post-crise : état des routes départementales, prioriser déblaiement et assistance sociale (PMI/ASE)")

        return recommendations or ["Suivi standard de la situation"]

    def _score_to_label(self, score: float) -> str:
        """Convertir un score en label"""
        if score > 0.5:
            return 'très positive'
        elif score > 0.2:
            return 'positive'
        elif score > -0.2:
            return 'neutre'
        elif score > -0.5:
            return 'négative'
        else:
            return 'très négative'

    def _calculate_confidence(self, articles: List, social: List) -> float:
        """Calculer le niveau de confiance de la prédiction"""
        # Plus il y a de données similaires, plus la confiance est élevée
        data_points = len(articles) + len(social)
        
        if data_points >= 10:
            return 0.9
        elif data_points >= 5:
            return 0.75
        elif data_points >= 2:
            return 0.6
        else:
            return 0.4

    def _save_prediction(self, prediction: Dict):
        """Sauvegarder la prédiction pour analyse future"""
        try:
            if self.client:
                prediction['_prediction_id'] = f"pred_{int(datetime.now().timestamp())}"
                self.reaction_predictions.insert_one(prediction)
        except Exception as e:
            logger.warning(f"Erreur sauvegarde prédiction: {e}")

# Instance globale
population_reaction_predictor = PopulationReactionPredictor()

# Fonction utilitaire (GPT-only si dispo, fallback local)

def predict_population_reaction(text: str, context: Dict = None) -> Dict[str, Any]:
    """Prédire la réaction de la population pour un texte donné.
    Préférence: prédicteur GPT qui compare aux **derniers N articles** (N=150 par défaut).
    Fallback: logique locale `PopulationReactionPredictor.analyze_population_reaction`.
    """
    ctx: Dict[str, Any] = {}
    if isinstance(context, dict):
        ctx.update(context)
    # Contraindre explicitement l'historique aux derniers 150 items
    ctx.setdefault('history_limit', int(ctx.get('history_limit') or 500))
    ctx.setdefault('history_scope', 'recent_articles')

    # Chemin privilégié: GPT predictor si disponible
    if callable(gpt_predict_population_reaction):  # type: ignore
        try:
            return gpt_predict_population_reaction(text, context=ctx)  # type: ignore
        except Exception as e:
            logger.warning(f"GPT predictor failed, fallback to local: {e}")

    # Fallback local (logique existante)
    return population_reaction_predictor.analyze_population_reaction(text, ctx)