# backend/media_noise_service.py
"""
Service de calcul du bruit médiatique pour la Guadeloupe
Intégré avec tags_index.py pour une classification cohérente
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter

from pymongo import MongoClient
from pymongo.errors import PyMongoError
import certifi

# Import du système de tags unifié
from backend.tags_index import infer_tags_and_theme, THEME_TAXONOMY, ELECTED_INDEX

# Configuration logging
logger = logging.getLogger("media_noise_service")

class MediaNoiseService:
    """Service de calcul du bruit médiatique unifié avec tags_index"""
    
    def __init__(self):
        self.mongo_client = self._get_mongo_client()
        self.db = self._get_database()
        
        # Utilisation de la taxonomie unifiée de tags_index
        self.themes = THEME_TAXONOMY
        self.elected_index = ELECTED_INDEX
        
        # Zones géographiques de la Guadeloupe (conservées)
        self.guadeloupe_zones = {
            "pointe_a_pitre": ["pointe-à-pitre", "pointe a pitre", "les abymes", "baie-mahault"],
            "basse_terre": ["basse-terre", "basse terre", "saint-claude", "gourbeyre", "trois-rivières"],
            "grande_terre": ["grande-terre", "grande terre", "le gosier", "sainte-anne", "saint-françois"],
            "nord_grande_terre": ["port-louis", "anse-bertrand", "petit-canal", "morne-à-l'eau"],
            "nord_basse_terre": ["lamentin", "petit-bourg", "capesterre-belle-eau", "goyave"],
            "sud_basse_terre": ["vieux-habitants", "bouillante", "pointe-noire", "deshaies"],
            "marie_galante": ["marie-galante", "grand-bourg", "capesterre-de-marie-galante"],
            "les_saintes": ["les saintes", "terre-de-haut", "terre-de-bas"],
            "la_desirade": ["la désirade", "désirade"],
            "saint_martin": ["saint-martin", "marigot", "philipsburg"],
            "saint_barthelemy": ["saint-barthélemy", "saint-barth", "gustavia"]
        }
        
        # Patterns contextuels d'intensité
        self.intensity_patterns = {
            "urgence": ["urgent", "alerte", "emergency", "breaking", "dernière minute"],
            "crise": ["crise", "catastrophe", "drame", "tragédie", "désastre"],
            "conflit": ["grève", "blocage", "manifestation", "conflit", "tension"],
            "celebration": ["festival", "fête", "célébration", "carnaval", "événement"],
            "meteo_extreme": ["cyclone", "tempête", "ouragan", "alerte météo", "vigilance rouge"]
        }
    
    def _get_mongo_client(self) -> Optional[MongoClient]:
        """Connexion MongoDB sécurisée"""
        mongo_url = os.environ.get("MONGO_URL", "").strip()
        if not mongo_url:
            logger.warning("MONGO_URL non défini pour MediaNoiseService")
            return None
        
        try:
            client = MongoClient(
                mongo_url,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=20000,
            )
            client.admin.command("ping")
            return client
        except Exception as e:
            logger.error(f"Erreur connexion MongoDB MediaNoiseService: {e}")
            return None
    
    def _get_database(self):
        """Récupération de la base de données"""
        if self.mongo_client is None:
            return None
        
        db_name = os.environ.get("MONGO_DB_NAME", "").strip()
        return self.mongo_client[db_name] if db_name else self.mongo_client.get_default_database()
    
    def _parse_period(self, period: str) -> Tuple[datetime, datetime]:
        """Parse une période (24h, 7d, 30d) en dates de début/fin"""
        end_date = datetime.now()
        
        if period == "24h":
            start_date = end_date - timedelta(hours=24)
        elif period == "7d":
            start_date = end_date - timedelta(days=7)
        elif period == "30d":
            start_date = end_date - timedelta(days=30)
        else:
            start_date = end_date - timedelta(hours=24)
        
        return start_date, end_date
    
    def _get_content_from_period(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Récupère tout le contenu (articles + transcriptions) d'une période"""
        if self.db is None:  # CORRECTION ICI
            return []
        
        content = []
        
        try:
            # Articles de presse avec classification tags_index
            articles = list(self.db["articles_guadeloupe"].find({
                "scraped_at": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
            }))
            
            for article in articles:
                # Enrichir avec tags_index si pas déjà fait
                if not article.get("theme") or not article.get("_tags"):
                    article = infer_tags_and_theme(article)
                
                content.append({
                    "type": "article",
                    "title": article.get("title", ""),
                    "content": article.get("title", ""),
                    "source": article.get("source", ""),
                    "date": article.get("scraped_at", ""),
                    "url": article.get("url", ""),
                    "theme": article.get("theme"),
                    "theme_score": article.get("theme_score", 0),
                    "elected": article.get("elected", []),
                    "tags": article.get("_tags", []),
                    "sentiment": article.get("sentiment", {})
                })
            
            # Transcriptions radio
            transcriptions = list(self.db["radio_transcriptions"].find({
                "captured_at": {"$gte": start_date, "$lte": end_date}
            }))
            
            for trans in transcriptions:
                # Appliquer tags_index aux transcriptions
                trans_article = {
                    "title": trans.get("segment_title", ""),
                    "content": trans.get("transcription", ""),
                    "source": trans.get("radio_name", "")
                }
                enriched_trans = infer_tags_and_theme(trans_article)
                
                content.append({
                    "type": "transcription",
                    "title": enriched_trans.get("title", ""),
                    "content": enriched_trans.get("content", ""),
                    "source": enriched_trans.get("source", ""),
                    "date": trans.get("captured_at", ""),
                    "theme": enriched_trans.get("theme"),
                    "theme_score": enriched_trans.get("theme_score", 0),
                    "elected": enriched_trans.get("elected", []),
                    "tags": enriched_trans.get("_tags", []),
                    "sentiment": trans.get("sentiment", {})
                })
            
        except Exception as e:
            logger.error(f"Erreur récupération contenu période: {e}")
        
        return content
    
    def _detect_zones(self, content: str) -> List[str]:
        """Détecte les zones géographiques mentionnées"""
        content_lower = content.lower()
        detected_zones = []
        
        for zone, keywords in self.guadeloupe_zones.items():
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    detected_zones.append(zone)
                    break
        
        return detected_zones
    
    def _detect_intensity_patterns(self, content: str) -> List[str]:
        """Détecte des patterns d'intensité dans le contenu"""
        content_lower = content.lower()
        detected_patterns = []
        
        for pattern, keywords in self.intensity_patterns.items():
            for keyword in keywords:
                if keyword.lower() in content_lower:
                    detected_patterns.append(pattern)
                    break
        
        return detected_patterns
    
    def _calculate_content_intensity(self, content_item: Dict[str, Any]) -> float:
        """Calcule l'intensité d'un élément de contenu avec tags_index"""
        intensity = 1.0
        content = content_item.get("content", "")
        
        # Facteurs de base
        if content_item.get("type") == "transcription":
            intensity *= 1.2
        
        # Score thématique de tags_index
        theme_score = content_item.get("theme_score", 0)
        if theme_score > 5:
            intensity *= 1.3
        elif theme_score > 2:
            intensity *= 1.1
        
        # Présence d'élus mentionnés
        elected = content_item.get("elected", [])
        if len(elected) > 0:
            intensity *= 1.2
        if len(elected) > 2:
            intensity *= 1.4
        
        # Sentiment négatif
        sentiment = content_item.get("sentiment", {})
        if sentiment.get("label") == "negative":
            intensity *= 1.4
        elif sentiment.get("label") == "positive":
            intensity *= 0.9
        
        # Patterns d'intensité
        patterns = self._detect_intensity_patterns(content)
        if "urgence" in patterns or "crise" in patterns:
            intensity *= 1.5
        if "conflit" in patterns:
            intensity *= 1.3
        if "meteo_extreme" in patterns:
            intensity *= 1.4
        
        # Longueur du contenu
        if len(content) > 500:
            intensity *= 1.2
        elif len(content) < 100:
            intensity *= 0.8
        
        return min(intensity, 3.0)
    
    def calculate_media_noise(self, period: str = "24h", zone: Optional[str] = None, theme: Optional[str] = None) -> Dict[str, Any]:
        """
        Calcule le score de bruit médiatique avec classification tags_index
        """
        start_date, end_date = self._parse_period(period)
        content = self._get_content_from_period(start_date, end_date)
        
        if not content:
            return self._empty_noise_result(period, zone, theme)
        
        # Filtrage par zone
        if zone:
            filtered_content = []
            for item in content:
                detected_zones = self._detect_zones(item.get("content", ""))
                if zone in detected_zones:
                    filtered_content.append(item)
            content = filtered_content
        
        # Filtrage par thème (utilise la taxonomie tags_index)
        if theme and theme in self.themes:
            content = [item for item in content if item.get("theme") == theme]
        
        if not content:
            return self._empty_noise_result(period, zone, theme)
        
        # Métriques de calcul
        total_items = len(content)
        articles_count = len([c for c in content if c.get("type") == "article"])
        transcriptions_count = len([c for c in content if c.get("type") == "transcription"])
        
        # 1. Score de volume (40%)
        hours_in_period = (end_date - start_date).total_seconds() / 3600
        normalized_volume = (total_items / hours_in_period) * 24
        volume_score = min(normalized_volume * 2, 100)
        
        # 2. Score d'intensité (30%) - intégré avec tags_index
        total_intensity = sum(self._calculate_content_intensity(item) for item in content)
        avg_intensity = total_intensity / total_items if total_items > 0 else 0
        intensity_score = min(avg_intensity * 30, 100)
        
        # 3. Score thématique (20%) - utilise theme_score de tags_index
        theme_scores = [item.get("theme_score", 0) for item in content]
        avg_theme_score = sum(theme_scores) / len(theme_scores) if theme_scores else 0
        thematic_score = min(avg_theme_score * 10, 100)
        
        # 4. Score d'élus (10%) - utilise detected elected de tags_index
        total_elected_mentions = sum(len(item.get("elected", [])) for item in content)
        elected_ratio = total_elected_mentions / total_items if total_items > 0 else 0
        elected_score = min(elected_ratio * 50, 100)
        
        # Score final pondéré
        final_score = (
            volume_score * 0.40 +
            intensity_score * 0.30 +
            thematic_score * 0.20 +
            elected_score * 0.10
        )
        
        # Analyse avec taxonomie tags_index
        theme_counts = Counter([item.get("theme") for item in content if item.get("theme")])
        all_elected = []
        for item in content:
            all_elected.extend(item.get("elected", []))
        elected_counts = Counter(all_elected)
        
        # Analyse des zones
        all_zones = []
        for item in content:
            zones = self._detect_zones(item.get("content", ""))
            all_zones.extend(zones)
        zone_counts = Counter(all_zones)
        
        return {
            "period": period,
            "zone": zone,
            "theme": theme,
            "noise_score": round(final_score, 1),
            "metrics": {
                "volume": round(volume_score, 1),
                "intensity": round(intensity_score, 1),
                "thematic": round(thematic_score, 1),
                "elected": round(elected_score, 1)
            },
            "details": {
                "total_items": total_items,
                "articles": articles_count,
                "transcriptions": transcriptions_count,
                "avg_intensity": round(avg_intensity, 2),
                "avg_theme_score": round(avg_theme_score, 2),
                "total_elected_mentions": total_elected_mentions
            },
            "themes": dict(theme_counts.most_common(10)),
            "elected": dict(elected_counts.most_common(10)),
            "zones": dict(zone_counts.most_common()),
            "classification_method": "tags_index_unified"
        }
    
    def _empty_noise_result(self, period: str, zone: Optional[str], theme: Optional[str]) -> Dict[str, Any]:
        """Résultat vide par défaut"""
        return {
            "period": period,
            "zone": zone,
            "theme": theme,
            "noise_score": 0,
            "metrics": {"volume": 0, "intensity": 0, "thematic": 0, "elected": 0},
            "details": {"total_items": 0, "articles": 0, "transcriptions": 0},
            "themes": {},
            "elected": {},
            "zones": {},
            "classification_method": "tags_index_unified"
        }
    
    def analyze_themes(self, period: str = "7d", limit: int = 10) -> Dict[str, Any]:
        """Analyse détaillée des thèmes avec tags_index"""
        start_date, end_date = self._parse_period(period)
        content = self._get_content_from_period(start_date, end_date)
        
        if not content:
            return {"period": period, "themes": {}, "total_content_analyzed": 0}
        
        # Grouper par thème tags_index
        theme_analysis = {}
        for theme_id in self.themes.keys():
            theme_items = [item for item in content if item.get("theme") == theme_id]
            
            if theme_items:
                total_intensity = sum(self._calculate_content_intensity(item) for item in theme_items)
                theme_scores = [item.get("theme_score", 0) for item in theme_items]
                
                # Analyse des élus mentionnés dans ce thème
                theme_elected = []
                for item in theme_items:
                    theme_elected.extend(item.get("elected", []))
                elected_counts = Counter(theme_elected)
                
                theme_analysis[theme_id] = {
                    "count": len(theme_items),
                    "total_intensity": round(total_intensity, 2),
                    "avg_intensity": round(total_intensity / len(theme_items), 2),
                    "avg_theme_score": round(sum(theme_scores) / len(theme_scores), 2),
                    "dominance_score": round((len(theme_items) / len(content)) * 100, 1),
                    "top_elected": dict(elected_counts.most_common(3)),
                    "recent_items": [
                        {
                            "title": item.get("title", "")[:100],
                            "source": item.get("source", ""),
                            "type": item.get("type", ""),
                            "elected": item.get("elected", [])
                        }
                        for item in sorted(theme_items, key=lambda x: x.get("date", ""), reverse=True)[:3]
                    ]
                }
        
        # Trier par dominance
        sorted_themes = sorted(
            theme_analysis.items(),
            key=lambda x: x[1]["dominance_score"],
            reverse=True
        )[:limit]
        
        return {
            "period": period,
            "total_content_analyzed": len(content),
            "themes": dict(sorted_themes),
            "classification_method": "tags_index_unified"
        }
    
    def get_elected_mentions_analysis(self, period: str = "7d") -> Dict[str, Any]:
        """Analyse des mentions d'élus avec tags_index"""
        start_date, end_date = self._parse_period(period)
        content = self._get_content_from_period(start_date, end_date)
        
        if not content:
            return {"period": period, "elected_mentions": {}, "total_content_analyzed": 0}
        
        # Analyser toutes les mentions d'élus
        elected_analysis = {}
        all_elected = []
        
        for item in content:
            elected_in_item = item.get("elected", [])
            all_elected.extend(elected_in_item)
            
            for elected_name in elected_in_item:
                if elected_name not in elected_analysis:
                    # Récupérer les infos depuis ELECTED_INDEX
                    elected_info = self.elected_index.get(elected_name, {})
                    elected_analysis[elected_name] = {
                        "function": elected_info.get("function", ""),
                        "mentions": [],
                        "themes": [],
                        "intensity_total": 0
                    }
                
                elected_analysis[elected_name]["mentions"].append({
                    "title": item.get("title", "")[:100],
                    "source": item.get("source", ""),
                    "theme": item.get("theme", ""),
                    "date": item.get("date", "")
                })
                
                elected_analysis[elected_name]["themes"].append(item.get("theme", ""))
                elected_analysis[elected_name]["intensity_total"] += self._calculate_content_intensity(item)
        
        # Finaliser l'analyse
        for elected_name, data in elected_analysis.items():
            data["mention_count"] = len(data["mentions"])
            data["avg_intensity"] = round(data["intensity_total"] / data["mention_count"], 2)
            data["top_themes"] = dict(Counter(data["themes"]).most_common(3))
            data["mentions"] = data["mentions"][:5]  # Limiter aux 5 plus récents
        
        # Trier par nombre de mentions
        sorted_elected = sorted(
            elected_analysis.items(),
            key=lambda x: x[1]["mention_count"],
            reverse=True
        )
        
        return {
            "period": period,
            "total_content_analyzed": len(content),
            "total_elected_mentions": len(all_elected),
            "unique_elected_mentioned": len(elected_analysis),
            "elected_mentions": dict(sorted_elected),
            "classification_method": "tags_index_unified"
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Statistiques générales du service unifié"""
        if self.db is None:  # CORRECTION ICI AUSSI
            return {"error": "Database unavailable"}
        
        try:
            total_articles = self.db["articles_guadeloupe"].count_documents({})
            total_transcriptions = self.db["radio_transcriptions"].count_documents({})
            
            # Stats dernières 24h
            yesterday = datetime.now() - timedelta(hours=24)
            recent_articles = self.db["articles_guadeloupe"].count_documents({
                "scraped_at": {"$gte": yesterday.isoformat()}
            })
            recent_transcriptions = self.db["radio_transcriptions"].count_documents({
                "captured_at": {"$gte": yesterday}
            })
            
            return {
                "total_content": total_articles + total_transcriptions,
                "total_articles": total_articles,
                "total_transcriptions": total_transcriptions,
                "recent_24h": {
                    "articles": recent_articles,
                    "transcriptions": recent_transcriptions,
                    "total": recent_articles + recent_transcriptions
                },
                "themes_available": len(self.themes),
                "elected_tracked": len(self.elected_index),
                "zones_tracked": len(self.guadeloupe_zones),
                "classification_system": "tags_index_unified",
                "service_status": "operational"
            }
        except Exception as e:
            logger.error(f"Erreur stats MediaNoiseService: {e}")
            return {"error": str(e), "service_status": "error"}

# Instance globale
media_noise_service = MediaNoiseService()
