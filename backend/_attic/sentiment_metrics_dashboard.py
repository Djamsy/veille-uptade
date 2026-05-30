# backend/sentiment_metrics_dashboard.py
"""
Système de métriques et visualisations pour l'analyse de sentiment
Génère des graphiques, tableaux de bord et rapports
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import seaborn as sns
from pymongo import MongoClient
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

class SentimentMetricsDashboard:
    def __init__(self):
        # MongoDB
        MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017/veille_media")
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        
        # Collections
        self.sentiment_metrics = self.db["sentiment_metrics"]
        self.graph_data = self.db["sentiment_graph_data"]
        self.affaires_collection = self.db["affaires_guadeloupe"]
        self.comments_collection = self.db["social_comments"]
        
        # Configuration graphiques
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        # Configuration couleurs
        self.colors = {
            "positive": "#28a745",  # Vert
            "negative": "#dc3545",  # Rouge
            "neutral": "#6c757d",   # Gris
            "crisis": "#ff6b35",    # Orange foncé
            "engagement": "#007bff" # Bleu
        }

    def generate_affair_sentiment_chart(self, affair_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Génère un graphique de sentiment temporel pour une affaire"""
        
        try:
            # Récupérer données temporelles
            since_date = datetime.now() - timedelta(days=days_back)
            
            graph_data = list(self.graph_data.find({
                "affair_id": affair_id,
                "timestamp": {"$gte": since_date}
            }).sort("timestamp", 1))
            
            if not graph_data:
                return {"error": "Aucune donnée disponible", "chart_url": None}
            
            # Préparer données pour Plotly
            timestamps = [point["timestamp"] for point in graph_data]
            positive_ratios = [point["positive_ratio"] for point in graph_data]
            negative_ratios = [point["negative_ratio"] for point in graph_data]
            engagement_scores = [point["engagement_score"] for point in graph_data]
            
            # Créer graphique avec sous-plots
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Sentiment au fil du temps', 'Score d\'engagement'),
                vertical_spacing=0.1,
                specs=[[{"secondary_y": False}],
                       [{"secondary_y": False}]]
            )
            
            # Graphique sentiment
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=positive_ratios,
                    mode='lines+markers',
                    name='Sentiment positif',
                    line=dict(color=self.colors["positive"], width=3),
                    marker=dict(size=6)
                ),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=negative_ratios,
                    mode='lines+markers',
                    name='Sentiment négatif',
                    line=dict(color=self.colors["negative"], width=3),
                    marker=dict(size=6)
                ),
                row=1, col=1
            )
            
            # Graphique engagement
            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=engagement_scores,
                    mode='lines+markers',
                    name='Engagement',
                    line=dict(color=self.colors["engagement"], width=2),
                    marker=dict(size=5)
                ),
                row=2, col=1
            )
            
            # Configuration layout
            fig.update_layout(
                title=f"Analyse sentiment - Affaire {affair_id}",
                height=600,
                showlegend=True,
                template="plotly_white"
            )
            
            fig.update_xaxes(title_text="Temps", row=2, col=1)
            fig.update_yaxes(title_text="Ratio sentiment", row=1, col=1)
            fig.update_yaxes(title_text="Score engagement", row=2, col=1)
            
            # Sauvegarder graphique
            chart_filename = f"sentiment_{affair_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            chart_path = os.path.join("static", "charts", chart_filename)
            
            # Créer dossier si nécessaire
            os.makedirs(os.path.dirname(chart_path), exist_ok=True)
            
            fig.write_html(chart_path)
            
            return {
                "success": True,
                "chart_url": f"/static/charts/{chart_filename}",
                "data_points": len(graph_data),
                "latest_negative_ratio": negative_ratios[-1] if negative_ratios else 0,
                "trend": self._calculate_trend(negative_ratios)
            }
            
        except Exception as e:
            logger.error(f"Erreur génération graphique sentiment: {e}")
            return {"error": str(e), "chart_url": None}

    def generate_crisis_indicators_chart(self, affair_id: str) -> Dict[str, Any]:
        """Génère un graphique des indicateurs de crise"""
        
        try:
            # Récupérer métriques avec indicateurs de crise
            metrics_data = list(self.sentiment_metrics.find({
                "affair_id": affair_id,
                "metrics.crisis_indicators": {"$exists": True, "$not": {"$size": 0}}
            }).sort("timestamp", 1))
            
            if not metrics_data:
                return {"error": "Aucun indicateur de crise détecté"}
            
            # Compter fréquence des indicateurs
            crisis_counts = {}
            for metric in metrics_data:
                for indicator in metric["metrics"]["crisis_indicators"]:
                    crisis_counts[indicator] = crisis_counts.get(indicator, 0) + 1
            
            # Créer graphique en barres
            fig = go.Figure(data=[
                go.Bar(
                    x=list(crisis_counts.keys()),
                    y=list(crisis_counts.values()),
                    marker_color=self.colors["crisis"],
                    text=list(crisis_counts.values()),
                    textposition='auto'
                )
            ])
            
            fig.update_layout(
                title=f"Indicateurs de crise - Affaire {affair_id}",
                xaxis_title="Indicateurs détectés",
                yaxis_title="Fréquence",
                template="plotly_white",
                height=400
            )
            
            # Sauvegarder
            chart_filename = f"crisis_{affair_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            chart_path = os.path.join("static", "charts", chart_filename)
            fig.write_html(chart_path)
            
            return {
                "success": True,
                "chart_url": f"/static/charts/{chart_filename}",
                "total_indicators": len(crisis_counts),
                "most_frequent": max(crisis_counts.keys(), key=crisis_counts.get) if crisis_counts else None
            }
            
        except Exception as e:
            logger.error(f"Erreur génération graphique crise: {e}")
            return {"error": str(e)}

    def generate_comparative_dashboard(self, days_back: int = 7) -> Dict[str, Any]:
        """Génère un tableau de bord comparatif de toutes les affaires"""
        
        try:
            since_date = datetime.now() - timedelta(days=days_back)
            
            # Récupérer toutes les affaires avec métriques sentiment
            pipeline = [
                {
                    "$match": {
                        "timestamp": {"$gte": since_date.isoformat()}
                    }
                },
                {
                    "$group": {
                        "_id": "$affair_id",
                        "avg_negative_ratio": {"$avg": "$metrics.negative_ratio"},
                        "total_comments": {"$sum": "$metrics.total_posts"},
                        "crisis_indicators": {"$push": "$metrics.crisis_indicators"},
                        "latest_alert_level": {"$last": "$alert_level"}
                    }
                },
                {
                    "$sort": {"avg_negative_ratio": -1}
                }
            ]
            
            affair_metrics = list(self.sentiment_metrics.aggregate(pipeline))
            
            if not affair_metrics:
                return {"error": "Aucune donnée disponible"}
            
            # Préparer données pour graphiques
            affair_ids = [metric["_id"] for metric in affair_metrics]
            negative_ratios = [metric["avg_negative_ratio"] for metric in affair_metrics]
            comment_counts = [metric["total_comments"] for metric in affair_metrics]
            alert_levels = [metric["latest_alert_level"] for metric in affair_metrics]
            
            # Graphique comparatif sentiment
            fig1 = go.Figure(data=[
                go.Bar(
                    x=affair_ids,
                    y=negative_ratios,
                    marker_color=[
                        self.colors["crisis"] if ratio > 0.7 else 
                        self.colors["negative"] if ratio > 0.5 else 
                        self.colors["neutral"]
                        for ratio in negative_ratios
                    ],
                    text=[f"{ratio:.1%}" for ratio in negative_ratios],
                    textposition='auto'
                )
            ])
            
            fig1.update_layout(
                title="Ratio de sentiment négatif par affaire",
                xaxis_title="Affaires",
                yaxis_title="Ratio sentiment négatif",
                template="plotly_white",
                height=400
            )
            
            # Graphique volume de commentaires
            fig2 = go.Figure(data=[
                go.Bar(
                    x=affair_ids,
                    y=comment_counts,
                    marker_color=self.colors["engagement"],
                    text=comment_counts,
                    textposition='auto'
                )
            ])
            
            fig2.update_layout(
                title="Volume de commentaires par affaire",
                xaxis_title="Affaires",
                yaxis_title="Nombre de commentaires",
                template="plotly_white",
                height=400
            )
            
            # Sauvegarder graphiques
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            chart1_filename = f"comparative_sentiment_{timestamp}.html"
            chart2_filename = f"comparative_volume_{timestamp}.html"
            
            chart1_path = os.path.join("static", "charts", chart1_filename)
            chart2_path = os.path.join("static", "charts", chart2_filename)
            
            fig1.write_html(chart1_path)
            fig2.write_html(chart2_path)
            
            return {
                "success": True,
                "charts": {
                    "sentiment_comparison": f"/static/charts/{chart1_filename}",
                    "volume_comparison": f"/static/charts/{chart2_filename}"
                },
                "summary": {
                    "total_affairs_analyzed": len(affair_metrics),
                    "highest_negative_ratio": max(negative_ratios) if negative_ratios else 0,
                    "total_comments_analyzed": sum(comment_counts),
                    "critical_affairs": sum(1 for level in alert_levels if level in ["CRITICAL", "HIGH"])
                }
            }
            
        except Exception as e:
            logger.error(f"Erreur génération dashboard comparatif: {e}")
            return {"error": str(e)}

    def generate_hourly_heatmap(self, affair_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Génère une heatmap d'activité par heure/jour"""
        
        try:
            since_date = datetime.now() - timedelta(days=days_back)
            
            graph_data = list(self.graph_data.find({
                "affair_id": affair_id,
                "timestamp": {"$gte": since_date}
            }))
            
            if not graph_data:
                return {"error": "Données insuffisantes pour heatmap"}
            
            # Créer matrice heure x jour
            df = pd.DataFrame(graph_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = df['timestamp'].dt.date
            df['hour'] = df['timestamp'].dt.hour
            
            # Agréger par date et heure
            heatmap_data = df.groupby(['date', 'hour'])['negative_ratio'].mean().unstack(fill_value=0)
            
            # Créer heatmap avec Plotly
            fig = go.Figure(data=go.Heatmap(
                z=heatmap_data.values,
                x=[f"{h:02d}h" for h in range(24)],
                y=[str(date) for date in heatmap_data.index],
                colorscale=[[0, self.colors["positive"]], [0.5, self.colors["neutral"]], [1, self.colors["negative"]]],
                colorbar=dict(title="Ratio négatif")
            ))
            
            fig.update_layout(
                title=f"Heatmap d'activité sentiment - Affaire {affair_id}",
                xaxis_title="Heure de la journée",
                yaxis_title="Date",
                height=500
            )
            
            # Sauvegarder
            chart_filename = f"heatmap_{affair_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            chart_path = os.path.join("static", "charts", chart_filename)
            fig.write_html(chart_path)
            
            return {
                "success": True,
                "chart_url": f"/static/charts/{chart_filename}",
                "peak_negative_hour": int(heatmap_data.mean(axis=0).idxmax()),
                "peak_negative_day": str(heatmap_data.mean(axis=1).idxmax())
            }
            
        except Exception as e:
            logger.error(f"Erreur génération heatmap: {e}")
            return {"error": str(e)}

    def generate_sentiment_report(self, affair_id: str, days_back: int = 7) -> Dict[str, Any]:
        """Génère un rapport complet d'analyse sentiment"""
        
        try:
            # Récupérer informations affaire
            affair = self.affaires_collection.find_one({"affaire_id": affair_id})
            if not affair:
                return {"error": "Affaire non trouvée"}
            
            # Récupérer métriques période
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            metrics_data = list(self.sentiment_metrics.find({
                "affair_id": affair_id,
                "date": {"$gte": since_date}
            }).sort("timestamp", 1))
            
            if not metrics_data:
                return {"error": "Aucune donnée de sentiment disponible"}
            
            # Calculs statistiques
            total_comments = sum(m["metrics"]["total_posts"] for m in metrics_data)
            avg_negative = sum(m["metrics"]["negative_ratio"] for m in metrics_data) / len(metrics_data)
            avg_positive = sum(m["metrics"]["positive_ratio"] for m in metrics_data) / len(metrics_data)
            
            # Évolution temporelle
            first_negative = metrics_data[0]["metrics"]["negative_ratio"]
            last_negative = metrics_data[-1]["metrics"]["negative_ratio"]
            trend = "DETERIORATION" if last_negative > first_negative + 0.1 else "AMELIORATION" if first_negative > last_negative + 0.1 else "STABLE"
            
            # Indicateurs de crise
            all_crisis_indicators = []
            for m in metrics_data:
                all_crisis_indicators.extend(m["metrics"]["crisis_indicators"])
            
            crisis_frequency = {}
            for indicator in all_crisis_indicators:
                crisis_frequency[indicator] = crisis_frequency.get(indicator, 0) + 1
            
            # Niveau d'alerte actuel
            current_alert = metrics_data[-1].get("alert_level", "LOW")
            
            # Générer graphiques
            chart_result = self.generate_affair_sentiment_chart(affair_id, days_back)
            crisis_result = self.generate_crisis_indicators_chart(affair_id)
            
            report = {
                "affair_info": {
                    "affair_id": affair_id,
                    "primary_entity": affair.get("primary_entity"),
                    "theme": affair.get("theme"),
                    "importance_score": affair.get("importance_score"),
                    "created_at": affair.get("created_at")
                },
                "analysis_period": {
                    "days_analyzed": days_back,
                    "start_date": since_date,
                    "end_date": datetime.now().strftime("%Y-%m-%d"),
                    "data_points": len(metrics_data)
                },
                "sentiment_summary": {
                    "total_comments_analyzed": total_comments,
                    "average_negative_ratio": round(avg_negative, 3),
                    "average_positive_ratio": round(avg_positive, 3),
                    "current_alert_level": current_alert,
                    "trend": trend,
                    "trend_magnitude": abs(last_negative - first_negative)
                },
                "crisis_analysis": {
                    "total_indicators": len(all_crisis_indicators),
                    "unique_indicators": len(crisis_frequency),
                    "most_frequent_indicators": sorted(crisis_frequency.items(), key=lambda x: x[1], reverse=True)[:5],
                    "escalation_detected": any("ESCALADE" in indicator for indicator in all_crisis_indicators)
                },
                "visualizations": {
                    "sentiment_chart": chart_result.get("chart_url"),
                    "crisis_chart": crisis_result.get("chart_url")
                },
                "recommendations": self._generate_detailed_recommendations(avg_negative, trend, crisis_frequency, current_alert),
                "generated_at": datetime.now().isoformat()
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Erreur génération rapport sentiment: {e}")
            return {"error": str(e)}

    def _calculate_trend(self, values: List[float]) -> str:
        """Calcule la tendance d'une série de valeurs"""
        if len(values) < 2:
            return "INSUFFICIENT_DATA"
        
        first_half = sum(values[:len(values)//2]) / (len(values)//2)
        second_half = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
        
        if second_half > first_half + 0.1:
            return "DETERIORATION"
        elif first_half > second_half + 0.1:
            return "AMELIORATION"
        else:
            return "STABLE"

    def _generate_detailed_recommendations(self, avg_negative: float, trend: str, 
                                         crisis_frequency: Dict[str, int], alert_level: str) -> List[str]:
        """Génère des recommandations détaillées"""
        
        recommendations = []
        
        # Recommandations basées sur le niveau de sentiment négatif
        if avg_negative > 0.8:
            recommendations.append("CRITIQUE: Sentiment majoritairement négatif (>80%). Communication de crise immédiate requise.")
            recommendations.append("Envisager une conférence de presse ou communiqué officiel dans les 24h.")
        elif avg_negative > 0.6:
            recommendations.append("ATTENTION: Sentiment négatif important (>60%). Surveillance renforcée et préparation de réponse.")
        elif avg_negative > 0.4:
            recommendations.append("VIGILANCE: Sentiment modérément négatif. Monitoring continu recommandé.")
        
        # Recommandations basées sur la tendance
        if trend == "DETERIORATION":
            recommendations.append("Tendance négative confirmée. Intervention rapide pour stopper la dégradation.")
            recommendations.append("Analyser les causes spécifiques de la détérioration récente.")
        elif trend == "AMELIORATION":
            recommendations.append("Tendance positive observée. Maintenir la stratégie de communication actuelle.")
        
        # Recommandations basées sur les indicateurs de crise
        if crisis_frequency:
            top_crisis = max(crisis_frequency.keys(), key=crisis_frequency.get)
            recommendations.append(f"Indicateur de crise dominant: '{top_crisis}'. Adapter la communication en conséquence.")
            
            if any("ESCALADE" in indicator for indicator in crisis_frequency.keys()):
                recommendations.append("ALERTE: Signaux d'escalade détectés. Prévoir mesures préventives.")
        
        # Recommandations basées sur le niveau d'alerte
        if alert_level in ["CRITICAL", "HIGH"]:
            recommendations.append("Niveau d'alerte élevé. Activation du protocole de gestion de crise.")
            recommendations.append("Coordonner avec les équipes communication et juridique.")
        
        return recommendations

    def cleanup_old_charts(self, days_to_keep: int = 7):
        """Nettoie les anciens graphiques pour économiser l'espace disque"""
        
        try:
            charts_dir = os.path.join("static", "charts")
            if not os.path.exists(charts_dir):
                return
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            deleted_count = 0
            
            for filename in os.listdir(charts_dir):
                if filename.endswith('.html'):
                    file_path = os.path.join(charts_dir, filename)
                    file_date = datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_date < cutoff_date:
                        os.remove(file_path)
                        deleted_count += 1
            
            logger.info(f"Nettoyage graphiques: {deleted_count} fichiers supprimés")
            
        except Exception as e:
            logger.error(f"Erreur nettoyage graphiques: {e}")


# Instance globale
sentiment_dashboard = SentimentMetricsDashboard()

# Export
__all__ = ['sentiment_dashboard', 'SentimentMetricsDashboard']