"""
Service de capture et transcription des flux radio guadeloupéens
Capture automatique 7H00-7H20 et 7H00-7H30
"""
import os
import subprocess
import tempfile
import whisper
from datetime import datetime, timedelta
import asyncio
import logging
from pymongo import MongoClient
from typing import Dict, Any, Optional, List
import threading
import time

# Configuration logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RadioTranscriptionService:
    def __init__(self):
        # MongoDB connection
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.client = MongoClient(MONGO_URL)
        self.db = self.client.veille_media
        self.transcriptions_collection = self.db.radio_transcriptions
        
        # Configuration des flux radio avec sections pré-nommées
        self.radio_streams = {
            "rci_7h": {
                "name": "7H RCI",
                "description": "RCI Guadeloupe - Journal matinal",
                "url": "http://n01a-eu.rcs.revma.com/v4hf7bwspwzuv?rj-ttl=5&rj-tok=AAABmFgYf1YAGI3rfz2-KTLPnA",
                "duration_minutes": 20,  # 7H00-7H20
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H RCI",
                "priority": 1
            },
            "guadeloupe_premiere_7h": {
                "name": "7H Guadeloupe Première", 
                "description": "Guadeloupe Première - Actualités matinales",
                "url": "http://guadeloupe.ice.infomaniak.ch/guadeloupe-128.mp3",
                "duration_minutes": 30,  # 7H00-7H30
                "start_hour": 7,
                "start_minute": 0,
                "section": "7H Guadeloupe Première",
                "priority": 2
            }
        }
        
        # Charger le modèle Whisper (base pour l'équilibre vitesse/qualité)
        try:
            logger.info("📱 Chargement du modèle Whisper...")
            self.whisper_model = whisper.load_model("base")
            logger.info("✅ Modèle Whisper chargé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur chargement Whisper: {e}")
            self.whisper_model = None
        
        # Statuts de transcription en cours
        self.transcription_status = {
            "rci_7h": {"in_progress": False, "started_at": None, "estimated_completion": None},
            "guadeloupe_premiere_7h": {"in_progress": False, "started_at": None, "estimated_completion": None}
        }

    def capture_radio_stream(self, stream_key: str, duration_seconds: int) -> Optional[str]:
        """Capturer un flux radio pendant une durée donnée"""
        config = self.radio_streams[stream_key]
        
        try:
            logger.info(f"🎵 Début capture {config['name']} pendant {duration_seconds}s...")
            
            # Créer un fichier temporaire pour l'audio
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Commande FFmpeg pour capturer le flux
            cmd = [
                'ffmpeg',
                '-i', config['url'],
                '-t', str(duration_seconds),
                '-acodec', 'mp3',
                '-ar', '16000',  # Fréquence d'échantillonnage pour Whisper
                '-ac', '1',      # Mono
                '-y',            # Overwrite
                temp_path
            ]
            
            # Exécuter la capture
            process = subprocess.run(
                cmd,
                capture_output=True,
                timeout=duration_seconds + 30,  # Timeout de sécurité
                check=True
            )
            
            # Vérifier que le fichier existe et n'est pas vide
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
                logger.info(f"✅ Capture terminée: {os.path.getsize(temp_path)} bytes")
                return temp_path
            else:
                logger.error("❌ Fichier audio vide ou inexistant")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"❌ Timeout lors de la capture de {config['name']}")
            return None
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Erreur FFmpeg pour {config['name']}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Erreur capture {config['name']}: {e}")
            return None

    def transcribe_audio_file(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """Transcrire un fichier audio avec Whisper"""
        if not self.whisper_model:
            logger.error("❌ Modèle Whisper non disponible")
            return None
        
        try:
            logger.info(f"🎤 Début transcription de {os.path.basename(audio_path)}...")
            
            # Transcription avec Whisper
            result = self.whisper_model.transcribe(
                audio_path,
                language='fr',  # Français
                verbose=False
            )
            
            transcription_data = {
                'text': result['text'].strip(),
                'language': result['language'],
                'segments': [
                    {
                        'start': segment['start'],
                        'end': segment['end'], 
                        'text': segment['text'].strip()
                    }
                    for segment in result.get('segments', [])
                ],
                'duration': result.get('duration', 0)
            }
            
            logger.info(f"✅ Transcription terminée: {len(transcription_data['text'])} caractères")
            return transcription_data
            
        except Exception as e:
            logger.error(f"❌ Erreur transcription: {e}")
            return None

    def capture_and_transcribe_stream(self, stream_key: str) -> Dict[str, Any]:
        """Capturer et transcrire un flux radio"""
        config = self.radio_streams[stream_key]
        duration_seconds = config['duration_minutes'] * 60
        
        result = {
            'success': False,
            'stream_key': stream_key,
            'stream_name': config['name'],
            'timestamp': datetime.now().isoformat(),
            'error': None,
            'transcription': None
        }
        
        try:
            # 1. Capturer le flux
            audio_path = self.capture_radio_stream(stream_key, duration_seconds)
            if not audio_path:
                result['error'] = "Échec de la capture audio"
                return result
            
            try:
                # 2. Transcrire l'audio
                transcription = self.transcribe_audio_file(audio_path)
                if not transcription:
                    result['error'] = "Échec de la transcription"
                    return result
                
                # 3. Sauvegarder en base de données
                transcription_record = {
                    'id': f"{stream_key}_{int(time.time())}",
                    'stream_key': stream_key,
                    'stream_name': config['name'],
                    'stream_url': config['url'],
                    'transcription_text': transcription['text'],
                    'language': transcription['language'],
                    'duration_seconds': transcription['duration'],
                    'segments': transcription['segments'],
                    'captured_at': datetime.now().isoformat(),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'audio_size_bytes': os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
                }
                
                # Insérer en base
                record_for_db = transcription_record.copy()
                insert_result = self.transcriptions_collection.insert_one(record_for_db)
                
                # Le record original n'a pas d'ObjectId ajouté par MongoDB
                result['success'] = True
                result['transcription'] = transcription_record
                
                logger.info(f"✅ Transcription sauvegardée pour {config['name']}")
                
            finally:
                # Nettoyer le fichier temporaire
                if audio_path and os.path.exists(audio_path):
                    os.unlink(audio_path)
                    
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Erreur globale pour {config['name']}: {e}")
        
        return result

    def capture_all_streams(self) -> Dict[str, Any]:
        """Capturer et transcrire tous les flux radio"""
        logger.info("🚀 Début capture de tous les flux radio...")
        
        results = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'streams_processed': 0,
            'streams_success': 0,
            'transcriptions': [],
            'errors': []
        }
        
        # Capturer les flux en parallèle
        threads = []
        stream_results = {}
        
        def capture_stream(stream_key):
            stream_results[stream_key] = self.capture_and_transcribe_stream(stream_key)
        
        # Lancer les captures en parallèle
        for stream_key in self.radio_streams.keys():
            thread = threading.Thread(target=capture_stream, args=(stream_key,))
            threads.append(thread)
            thread.start()
        
        # Attendre la fin de toutes les captures
        for thread in threads:
            thread.join()
        
        # Compiler les résultats
        for stream_key, stream_result in stream_results.items():
            results['streams_processed'] += 1
            
            if stream_result['success']:
                results['streams_success'] += 1
                results['transcriptions'].append(stream_result['transcription'])
            else:
                results['errors'].append(f"{stream_result['stream_name']}: {stream_result['error']}")
        
        results['success'] = results['streams_success'] > 0
        
        logger.info(f"📊 Capture terminée: {results['streams_success']}/{results['streams_processed']} flux réussis")
        
        return results

    def get_todays_transcriptions(self) -> list:
        """Récupérer les transcriptions d'aujourd'hui"""
        today = datetime.now().strftime('%Y-%m-%d')
        transcriptions = list(self.transcriptions_collection.find(
            {'date': today}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        return transcriptions

    def get_transcriptions_by_date(self, date_str: str) -> list:
        """Récupérer les transcriptions d'une date spécifique"""
        transcriptions = list(self.transcriptions_collection.find(
            {'date': date_str}, 
            {'_id': 0}
        ).sort('captured_at', -1))
        
        return transcriptions

# Instance globale du service radio
radio_service = RadioTranscriptionService()

def run_morning_radio_capture():
    """Fonction pour lancer la capture matinale à 7H"""
    logger.info("⏰ Lancement de la capture radio matinale à 7H")
    return radio_service.capture_all_streams()

if __name__ == "__main__":
    # Test du service
    result = radio_service.capture_all_streams()
    print(f"Résultat: {result}")