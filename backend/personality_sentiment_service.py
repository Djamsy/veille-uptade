# backend/personalities_service.py
"""
Service d'analyse de sentiment pour les personnalités politiques guadeloupéennes
Version simplifiée et robuste sans ObjectId
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
            "Ary Chalus": ["ary chalus", "chalus", "président conseil départemental"],
            "Guy Losbar": ["guy losbar", "losbar", "député guadeloupe"],
            "Sébastien Lecornu": ["sébastien lecornu", "lecornu", "ministre outre-mer"],
            "André ATALLAH": ["andré atallah", "atallah", "andre atallah"],
            "Harry Durimel": ["harry durimel", "durimel"],
            "Justine Benin": ["justine benin", "benin"],
            "Olivier Serva": ["olivier serva", "serva"],
            "Max Mathiasin": ["max mathiasin", "mathiasin"],
            "Gabrielle Louis-Carabin": ["gabrielle louis-carabin", "louis-carabin", "carabin"],
            "Josette Borel-Lincertin": ["josette borel", "borel-lincertin", "borel"],
            "Elie Califer": ["elie califer", "califer"],
            "Sylvie Gustave Dit Duflo": ["sylvie gustave", "gustave dit duflo"],
            "Daniel Daviaud": ["daniel daviaud", "daviaud"]
        }
    
    def get_personalities_ranking(self, days: int = 30, limit: int = 20) -> Dict[str, Any]:
        """Point d'entrée principal pour le classement des personnalités"""
        try:
            logger.info(f"Calcul classement personnalités (période: {days} jours, limit: {limit})")
            
            # 1. Compter les mentions de base
            base_counts = self._count_personality_mentions(days)
            
            # 2. Analyser le sentiment pour chaque personnalité
            personalities_with_sentiment = []
            
            for personality_name, mention_count in base_counts.items():
                if mention_count >= 1:  # Au moins 1 mention
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
                "analysis_method": "local_economic" if self.sentiment_analyzer else "count_only"
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul classement personnalités: {e}")
            return self._get_empty_result(days)
    
    def _count_personality_mentions(self, days: int) -> Dict[str, int]:
        """Compter les mentions de chaque personnalité"""
        start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        personality_counts = defaultdict(int)
        
        # Compter dans les articles
        try:
            for personality_name, variants in self.known_personalities.items():
                # Créer la requête de recherche
                search_patterns = []
                for variant in variants:
                    search_patterns.extend([
                        {"title": {"$regex": re.escape(variant), "$options": "i"}},
                        {"content": {"$regex": re.escape(variant), "$options": "i"}},
                        {"elected": variant}
                    ])
                
                query = {
                    "date": {"$gte": start_date_str},
                    "$or": search_patterns
                }
                
                # Compter dans articles_guadeloupe
                try:
                    count = self.db.articles_guadeloupe.count_documents(query)
                except Exception:
                    # Fallback vers articles
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
                    personality_counts[personality_name] += count
                    
        except Exception as e:
            logger.error(f"Erreur comptage mentions transcriptions: {e}")
        
        logger.info(f"Mentions trouvées: {dict(personality_counts)}")
        return dict(personality_counts)
    
    def _analyze_personality_sentiment(self, personality_name: str, days: int) -> Dict[str, Any]:
        """Analyser le sentiment pour une personnalité spécifique"""
        try:
            start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            variants = self.known_personalities.get(personality_name, [personality_name.lower()])
            
            # Collecter les contenus mentionnant cette personnalité
            contents = []
            
            # Articles
            for variant in variants:
                search_patterns = [
                    {"title": {"$regex": re.escape(variant), "$options": "i"}},
                    {"content": {"$regex": re.escape(variant), "$options": "i"}},
                    {"elected": variant}
                ]
                
                query = {
                    "date": {"$gte": start_date_str},
                    "$or": search_patterns
                }
                
                projection = {
                    "_id": 0,
                    "title": 1,
                    "content": 1,
                    "sentiment": 1,
                    "date": 1,
                    "source": 1
                }
                
                try:
                    articles = list(self.db.articles_guadeloupe.find(query, projection).limit(10))
                except Exception:
                    articles = list(self.db.articles.find(query, projection).limit(10))
                
                for article in articles:
                    text = f"{article.get('title', '')} {article.get('content', '')[:300]}"
                    contents.append({
                        "text": text.strip(),
                        "existing_sentiment": article.get("sentiment"),
                        "type": "article",
                        "source": article.get("source", ""),
                        "date": article.get("date", "")
                    })
            
            # Transcriptions
            for variant in variants:
                query = {
                    "date": {"$gte": start_date_str},
                    "transcription_text": {"$regex": re.escape(variant), "$options": "i"}
                }
                
                projection = {
                    "_id": 0,
                    "transcription_text": 1,
                    "sentiment": 1,
                    "date": 1,
                    "section": 1
                }
                
                transcriptions = list(self.db.radio_transcriptions.find(query, projection).limit(5))
                
                for trans in transcriptions:
                    text = trans.get("transcription_text", "")[:300]
                    contents.append({
                        "text": text.strip(),
                        "existing_sentiment": trans.get("sentiment"),
                        "type": "transcription",
                        "source": trans.get("section", ""),
                        "date": trans.get("date", "")
                    })
            
            # Analyser les sentiments
            return self._process_sentiment_analysis(contents, personality_name)
            
        except Exception as e:
            logger.error(f"Erreur analyse sentiment {personality_name}: {e}")
            return self._get_default_sentiment_data()
    
    def _process_sentiment_analysis(self, contents: List[Dict], personality_name: str) -> Dict[str, Any]:
        """Traiter l'analyse de sentiment pour une liste de contenus"""
        sentiment_scores = []
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        
        for content in contents:
            if not content["text"] or len(content["text"].strip()) < 10:
                continue
                
            # Utiliser le sentiment existant si disponible
            existing_sentiment = content.get("existing_sentiment")
            sentiment_score = None
            
            if existing_sentiment and isinstance(existing_sentiment, dict):
                polarity = existing_sentiment.get("polarity")
                score = existing_sentiment.get("score", 0)
                
                if polarity and isinstance(score, (int, float)):
                    if polarity == "positive":
                        sentiment_score = abs(float(score))
                        positive_count += 1
                    elif polarity == "negative":
                        sentiment_score = -abs(float(score))
                        negative_count += 1
                    else:
                        sentiment_score = 0.0
                        neutral_count += 1
            
            # Si pas de sentiment existant, utiliser l'analyseur local
            if sentiment_score is None and self.sentiment_analyzer:
                try:
                    result = self.sentiment_analyzer(content["text"])
                    if result and isinstance(result, dict):
                        polarity = result.get("polarity")
                        score = result.get("score", 0)
                        
                        if polarity and isinstance(score, (int, float)):
                            if polarity == "positive":
                                sentiment_score = abs(float(score))
                                positive_count += 1
                            elif polarity == "negative":
                                sentiment_score = -abs(float(score))
                                negative_count += 1
                            else:
                                sentiment_score = 0.0
                                neutral_count += 1
                except Exception as e:
                    logger.warning(f"Erreur analyseur sentiment pour {personality_name}: {e}")
            
            # Fallback vers neutre si aucune analyse possible
            if sentiment_score is None:
                sentiment_score = 0.0
                neutral_count += 1
            
            sentiment_scores.append(sentiment_score)
        
        # Calculer le score moyen
        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            confidence = min(1.0, len(sentiment_scores) / 10.0)  # Plus de contenus = plus de confiance
        else:
            avg_sentiment = 0.0
            confidence = 0.0
        
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
        
        # Trouver le plus positif et le plus négatif
        most_positive = None
        most_negative = None
        
        for p in personalities:
            score = p.get("sentiment_score", 0)
            if score > 0.1 and (most_positive is None or score > personalities[0]["sentiment_score"]):
                most_positive = p["elected"]
            if score < -0.1 and (most_negative is None):
                most_negative = p["elected"]
        
        total_mentions = sum(p.get("count", 0) for p in personalities)
        avg_sentiment = sum(p.get("sentiment_score", 0) for p in personalities) / len(personalities)
        
        return {
            "total_personalities": len(personalities),
            "most_positive": most_positive,
            "most_negative": most_negative,
            "total_mentions": total_mentions,
            "average_sentiment": round(avg_sentiment, 3)
        }
    
    def _get_default_sentiment_data(self) -> Dict[str, Any]:
        """Données de sentiment par défaut en cas d'erreur"""
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
            "error": "Erreur lors du calcul"
        }