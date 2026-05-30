# backend/personalities_service.py
"""
Service d'analyse de sentiment pour les personnalités politiques guadeloupéennes
Version optimisée avec analyse contextuelle améliorée
"""
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class PersonalitiesService:
    """Service pour analyser le sentiment des personnalités politiques"""
    
    def __init__(self, db, sentiment_analyzer=None):
        self.db = db
        self.sentiment_analyzer = sentiment_analyzer
        
        # Personnalités connues de Guadeloupe avec variantes
        self.known_personalities = {
            "Ary Chalus": ["ary chalus", "a. chalus", "président conseil régional"],
            "Guy Losbar": ["guy losbar", "g. losbar", "président conseil départemental"],
            "Sébastien Lecornu": ["sébastien lecornu", "sebastien lecornu", "s. lecornu", "ministre outre-mer"],
            "André ATALLAH": ["andré atallah", "andre atallah", "a. atallah"],
            "Harry Durimel": ["harry durimel", "h. durimel"],
            "Justine Benin": ["justine benin", "j. benin"],
            "Olivier Serva": ["olivier serva", "o. serva"],
            "Max Mathiasin": ["max mathiasin", "m. mathiasin"],
            "Gabrielle Louis-Carabin": ["gabrielle louis-carabin", "gabrielle louis carabin"],
            "Josette Borel-Lincertin": ["josette borel-lincertin", "josette borel"],
            "Elie Califer": ["elie califer", "élie califer", "e. califer"],
            "Sylvie Gustave Dit Duflo": ["sylvie gustave", "gustave dit duflo", "gustave-dit-duflo"],
            "Daniel Daviaud": ["daniel daviaud", "d. daviaud"],
            "Eric Jalton": ["eric jalton", "éric jalton", "e. jalton"],
            "Ferdy Louisy": ["ferdy louisy", "f. louisy"],
            "Jean-Philippe Courtois": ["jean-philippe courtois", "jean philippe courtois", "j-p courtois", "j.p. courtois"],
            "Victorin Lurel": ["victorin lurel", "v. lurel"]
        }
        
        # Mots-clés pour l'analyse contextuelle
        self.positive_keywords = [
            # Actions positives
            "excellent", "bravo", "félicite", "félicitation", "félicitations", 
            "réussite", "réussir", "succès", "victoire", "gagner", "gagné",
            "progrès", "progression", "amélioration", "améliorer", "avancée",
            
            # Qualités positives
            "bien", "bon", "bonne", "meilleur", "mieux", "parfait",
            "efficace", "efficacité", "performant", "performance",
            "positif", "positive", "favorable", "bénéfique",
            
            # Sentiments positifs
            "content", "satisfait", "satisfaction", "heureux", "joie",
            "fier", "fierté", "confiance", "espoir", "optimiste",
            
            # Soutien et accord
            "soutien", "soutenir", "appui", "appuyer", "aide", "aider",
            "accord", "approuve", "approuver", "favorable", "pour",
            
            # Termes spécifiques Guadeloupe
            "développement", "croissance", "emploi", "création", "investissement",
            "modernisation", "innovation", "tourisme", "économie"
        ]
        
        self.negative_keywords = [
            # Échecs et problèmes
            "échec", "échouer", "raté", "rater", "fiasco", "désastre",
            "problème", "problèmes", "problématique", "difficulté", "difficile",
            "crise", "critique", "critiquer", "reprocher", "reproche",
            
            # Manques et insuffisances
            "insuffisant", "insuffisance", "manque", "manquer", "absence",
            "faible", "faiblesse", "inadéquat", "inadapté", "incompétent",
            
            # Opposition et conflit
            "contre", "opposition", "opposer", "refus", "refuser", "rejet",
            "conflit", "tension", "polémique", "controverse", "scandale",
            
            # Sentiments négatifs
            "inquiet", "inquiétude", "inquiétant", "préoccupation", "préoccupant",
            "peur", "crainte", "danger", "dangereux", "menace", "menacer",
            "déçu", "déception", "frustration", "colère", "mécontentement",
            
            # Termes spécifiques négatifs
            "retard", "retarder", "blocage", "bloquer", "obstacle",
            "corruption", "détournement", "gaspillage", "incompétence",
            "chômage", "pauvreté", "insécurité", "violence"
        ]
    
    def get_personalities_ranking(self, days: int = 30, limit: int = 20) -> Dict[str, Any]:
        """Point d'entrée principal pour le classement des personnalités"""
        try:
            logger.info(f"Calcul classement personnalités (période: {days} jours, limit: {limit})")
            
            # 1. Compter les mentions de base
            base_counts = self._count_personality_mentions(days)
            
            # 2. Analyser le sentiment pour chaque personnalité
            personalities_with_sentiment = []
            
            for personality_name, mention_count in base_counts.items():
                if mention_count >= 1:
                    sentiment_data = self._analyze_personality_sentiment(personality_name, days)
                    
                    personality_entry = {
                        "elected": personality_name,
                        "count": mention_count,
                        "sentiment_score": sentiment_data["sentiment_score"],
                        "positive_mentions": sentiment_data["positive_mentions"],
                        "neutral_mentions": sentiment_data["neutral_mentions"], 
                        "negative_mentions": sentiment_data["negative_mentions"],
                        "total_analyzed": sentiment_data["total_analyzed"],
                        "confidence": sentiment_data["confidence"]
                    }
                    
                    personalities_with_sentiment.append(personality_entry)
            
            # 3. Trier par score de sentiment (plus positif en premier)
            personalities_with_sentiment.sort(key=lambda x: x["sentiment_score"], reverse=True)
            
            # 4. Limiter les résultats
            final_personalities = personalities_with_sentiment[:limit]
            
            # 5. Calculer le résumé
            summary = self._calculate_summary(final_personalities)
            
            return {
                "personalities": final_personalities,
                "summary": summary,
                "period": {
                    "days": days,
                    "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
                    "end_date": datetime.now().isoformat()
                },
                "generated_at": datetime.now().isoformat(),
                "analysis_method": "local_economic_contextual" if self.sentiment_analyzer else "keywords_only"
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul classement personnalités: {e}", exc_info=True)
            return self._get_empty_result(days)
    
    def _count_personality_mentions(self, days: int) -> Dict[str, int]:
        """Compter les mentions de chaque personnalité"""
        start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        personality_counts = defaultdict(int)
        
        # Compter dans les articles
        try:
            for personality_name, variants in self.known_personalities.items():
                search_patterns = []
                for variant in variants:
                    search_patterns.extend([
                        {"title": {"$regex": re.escape(variant), "$options": "i"}},
                        {"content": {"$regex": re.escape(variant), "$options": "i"}}
                    ])
                
                query = {
                    "date": {"$gte": start_date_str},
                    "$or": search_patterns
                }
                
                # Essayer articles_guadeloupe puis articles
                try:
                    count = self.db.articles_guadeloupe.count_documents(query)
                except Exception:
                    count = self.db.articles.count_documents(query)
                
                if count > 0:
                    personality_counts[personality_name] = count
                    
        except Exception as e:
            logger.error(f"Erreur comptage mentions articles: {e}")
        
        # Compter dans les transcriptions
        try:
            for personality_name, variants in self.known_personalities.items():
                search_patterns = []
                for variant in variants:
                    search_patterns.append(
                        {"transcription_text": {"$regex": re.escape(variant), "$options": "i"}}
                    )
                
                query = {
                    "date": {"$gte": start_date_str},
                    "$or": search_patterns
                }
                
                count = self.db.radio_transcriptions.count_documents(query)
                if count > 0:
                    personality_counts[personality_name] = personality_counts.get(personality_name, 0) + count
                    
        except Exception as e:
            logger.error(f"Erreur comptage mentions transcriptions: {e}")
        
        logger.info(f"Mentions trouvées: {dict(personality_counts)}")
        return dict(personality_counts)
    
    def _analyze_personality_sentiment(self, personality_name: str, days: int) -> Dict[str, Any]:
        """Analyser le sentiment pour une personnalité spécifique"""
        try:
            start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            variants = self.known_personalities.get(personality_name, [personality_name.lower()])
            
            # Collecter les contextes autour des mentions
            contexts = []
            
            # Recherche dans les articles
            for variant in variants:
                search_patterns = [
                    {"title": {"$regex": re.escape(variant), "$options": "i"}},
                    {"content": {"$regex": re.escape(variant), "$options": "i"}}
                ]
                
                query = {
                    "date": {"$gte": start_date_str},
                    "$or": search_patterns
                }
                
                projection = {
                    "_id": 0,
                    "title": 1,
                    "content": 1
                }
                
                try:
                    articles = list(self.db.articles_guadeloupe.find(query, projection).limit(30))
                except Exception:
                    articles = list(self.db.articles.find(query, projection).limit(30))
                
                for article in articles:
                    title = article.get('title', '')
                    content = article.get('content', '')
                    full_text = f"{title} {content}"
                    
                    # Extraire contexte autour de la mention (300 caractères avant/après)
                    pattern = re.compile(
                        f'(.{{0,300}}{re.escape(variant)}.{{0,300}})',
                        re.IGNORECASE | re.DOTALL
                    )
                    
                    matches = pattern.findall(full_text)
                    for match in matches[:3]:  # Max 3 contextes par article
                        context = ' '.join(match.split())
                        if len(context) > 50:
                            contexts.append(context)
            
            # Recherche dans les transcriptions
            for variant in variants:
                query = {
                    "date": {"$gte": start_date_str},
                    "transcription_text": {"$regex": re.escape(variant), "$options": "i"}
                }
                
                projection = {
                    "_id": 0,
                    "transcription_text": 1
                }
                
                transcriptions = list(self.db.radio_transcriptions.find(query, projection).limit(15))
                
                for trans in transcriptions:
                    text = trans.get("transcription_text", "")
                    
                    pattern = re.compile(
                        f'(.{{0,300}}{re.escape(variant)}.{{0,300}})',
                        re.IGNORECASE | re.DOTALL
                    )
                    
                    matches = pattern.findall(text)
                    for match in matches[:2]:  # Max 2 contextes par transcription
                        context = ' '.join(match.split())
                        if len(context) > 50:
                            contexts.append(context)
            
            # Analyser les contextes
            return self._analyze_contexts(contexts, personality_name)
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment {personality_name}: {e}")
            return self._get_default_sentiment_data()
    
    def _analyze_contexts(self, contexts: List[str], personality_name: str) -> Dict[str, Any]:
        """Analyser le sentiment des contextes avec approche hybride"""
        if not contexts:
            return self._get_default_sentiment_data()
        
        sentiment_scores = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        logger.info(f"Analyse de {len(contexts)} contextes pour {personality_name}")
        
        for context in contexts[:50]:  # Limiter à 50 contextes
            if not context or len(context) < 30:
                continue
            
            context_lower = context.lower()
            
            # 1. Analyse par mots-clés (prioritaire car plus fiable)
            pos_count = sum(1 for word in self.positive_keywords if word in context_lower)
            neg_count = sum(1 for word in self.negative_keywords if word in context_lower)
            
            sentiment_score = 0.0
            
            if pos_count > 0 or neg_count > 0:
                # Score basé sur la différence pondérée
                diff = pos_count - neg_count
                if diff > 0:
                    sentiment_score = min(0.8, 0.15 * diff)
                    positive_count += 1
                elif diff < 0:
                    sentiment_score = max(-0.8, 0.15 * diff)
                    negative_count += 1
                else:
                    sentiment_score = 0.0
                    neutral_count += 1
            
            # 2. Si pas de mots-clés trouvés, utiliser l'analyseur
            elif self.sentiment_analyzer:
                try:
                    result = self.sentiment_analyzer(context)
                    if result and isinstance(result, dict):
                        score = float(result.get("score", 0))
                        polarity = result.get("polarity", "neutral")
                        
                        if polarity == "positive" or score > 0.1:
                            sentiment_score = max(0.2, score)
                            positive_count += 1
                        elif polarity == "negative" or score < -0.1:
                            sentiment_score = min(-0.2, score)
                            negative_count += 1
                        else:
                            sentiment_score = 0.0
                            neutral_count += 1
                except Exception as e:
                    logger.debug(f"Erreur analyseur pour contexte: {e}")
                    neutral_count += 1
            else:
                neutral_count += 1
            
            sentiment_scores.append(sentiment_score)
        
        # Calculer le score moyen pondéré
        if sentiment_scores:
            # Donner plus de poids aux scores non-neutres
            weighted_scores = []
            for score in sentiment_scores:
                if score != 0:
                    weighted_scores.append(score * 1.5)  # Amplifier les sentiments détectés
                else:
                    weighted_scores.append(score)
            
            avg_sentiment = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0
            confidence = min(1.0, len([s for s in sentiment_scores if s != 0]) / 10.0)
        else:
            avg_sentiment = 0.0
            confidence = 0.0
        
        logger.info(f"Résultat {personality_name}: score:{avg_sentiment:.3f}, "
                   f"pos:{positive_count} neut:{neutral_count} neg:{negative_count}")
        
        return {
            "sentiment_score": round(avg_sentiment, 3),
            "positive_mentions": positive_count,
            "neutral_mentions": neutral_count,
            "negative_mentions": negative_count,
            "total_analyzed": len(sentiment_scores),
            "confidence": round(confidence, 2)
        }
    
    def _calculate_summary(self, personalities: List[Dict]) -> Dict[str, Any]:
        """Calculer le résumé du classement"""
        if not personalities:
            return {
                "total_personalities": 0,
                "most_positive": None,
                "most_negative": None,
                "total_mentions": 0,
                "average_sentiment": 0.0
            }
        
        # Identifier les extrêmes
        sorted_by_score = sorted(personalities, key=lambda x: x.get("sentiment_score", 0))
        
        most_positive = sorted_by_score[-1] if sorted_by_score[-1]["sentiment_score"] > 0.1 else None
        most_negative = sorted_by_score[0] if sorted_by_score[0]["sentiment_score"] < -0.1 else None
        
        total_mentions = sum(p.get("count", 0) for p in personalities)
        avg_sentiment = sum(p.get("sentiment_score", 0) for p in personalities) / len(personalities)
        
        return {
            "total_personalities": len(personalities),
            "most_positive": most_positive["elected"] if most_positive else None,
            "most_negative": most_negative["elected"] if most_negative else None,
            "total_mentions": total_mentions,
            "average_sentiment": round(avg_sentiment, 3)
        }
    
    def _get_default_sentiment_data(self) -> Dict[str, Any]:
        """Données de sentiment par défaut"""
        return {
            "sentiment_score": 0.0,
            "positive_mentions": 0,
            "neutral_mentions": 0,
            "negative_mentions": 0,
            "total_analyzed": 0,
            "confidence": 0.0
        }
    
    def _get_empty_result(self, days: int) -> Dict[str, Any]:
        """Résultat vide en cas d'erreur"""
        return {
            "personalities": [],
            "summary": {
                "total_personalities": 0,
                "most_positive": None,
                "most_negative": None,
                "total_mentions": 0,
                "average_sentiment": 0.0
            },
            "period": {
                "days": days,
                "start_date": (datetime.now() - timedelta(days=days)).isoformat(),
                "end_date": datetime.now().isoformat()
            },
            "generated_at": datetime.now().isoformat(),
            "analysis_method": "error"
        }