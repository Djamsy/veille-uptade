#!/usr/bin/env python3
"""
Script pour tester l'endpoint /api/transcribe et capturer l'erreur exacte
"""
import requests
import tempfile
import os
import sys

# Créer un petit fichier audio de test (silence)
def create_test_audio():
    # Utiliser ffmpeg pour créer un fichier audio de test de 2 secondes
    test_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    test_file.close()
    
    # Créer un fichier audio silencieux de 2 secondes
    cmd = f"ffmpeg -f lavfi -i 'anullsrc=channel_layout=mono:sample_rate=16000' -t 2 -y {test_file.name}"
    result = os.system(cmd)
    
    if result == 0:
        print(f"✅ Fichier audio de test créé: {test_file.name}")
        return test_file.name
    else:
        print("❌ Erreur création fichier audio de test")
        return None

def test_transcribe_endpoint():
    audio_file = create_test_audio()
    if not audio_file:
        return
    
    try:
        # Tester l'endpoint local
        url = "http://localhost:8001/api/transcribe"
        
        with open(audio_file, 'rb') as f:
            files = {'file': ('test.wav', f, 'audio/wav')}
            
            print(f"🔍 Testing {url}...")
            response = requests.post(url, files=files, timeout=30)
            
            print(f"Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                print("✅ SUCCESS!")
                print(f"Response: {response.json()}")
            else:
                print("❌ ERROR!")
                print(f"Response Text: {response.text}")
                
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {e}")
    except Exception as e:
        print(f"❌ General Error: {e}")
    finally:
        # Nettoyer
        if audio_file and os.path.exists(audio_file):
            os.unlink(audio_file)
            print(f"🧹 Cleaned up {audio_file}")

if __name__ == "__main__":
    test_transcribe_endpoint()