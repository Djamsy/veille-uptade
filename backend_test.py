#!/usr/bin/env python3
"""
Backend API Test Suite for Veille Média Application
Tests all endpoints using the public URL from frontend/.env
"""

import requests
import sys
import json
import tempfile
import os
from datetime import datetime

class VeilleMediaAPITester:
    def __init__(self, base_url="https://dd85e1a4-0c6d-492c-a846-7540ed473817.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 30

    def log_test(self, name, success, details=""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def test_root_endpoint(self):
        """Test root endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/")
            success = response.status_code == 200
            if success:
                data = response.json()
                details = f"- Message: {data.get('message', 'No message')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Root Endpoint", success, details)
        except Exception as e:
            return self.log_test("Root Endpoint", False, f"- Error: {str(e)}")

    def test_dashboard_stats(self):
        """Test dashboard statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/dashboard-stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    details = f"- Articles: {stats.get('total_articles', 0)}, Transcriptions: {stats.get('total_transcriptions', 0)}"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Dashboard Stats", success, details)
        except Exception as e:
            return self.log_test("Dashboard Stats", False, f"- Error: {str(e)}")

    def test_articles_get(self):
        """Test get articles endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    details = f"- Found {len(articles)} articles"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Get Articles", success, details)
        except Exception as e:
            return self.log_test("Get Articles", False, f"- Error: {str(e)}")

    def test_articles_fetch(self):
        """Test fetch articles endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/articles/fetch")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    details = f"- Fetched {len(articles)} articles"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Fetch Articles", success, details)
        except Exception as e:
            return self.log_test("Fetch Articles", False, f"- Error: {str(e)}")

    def test_transcriptions_get(self):
        """Test get transcriptions endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/transcriptions")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    transcriptions = data.get('transcriptions', [])
                    details = f"- Found {len(transcriptions)} transcriptions"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Get Transcriptions", success, details)
        except Exception as e:
            return self.log_test("Get Transcriptions", False, f"- Error: {str(e)}")

    def test_transcribe_audio(self):
        """Test audio transcription endpoint"""
        try:
            # Create a dummy audio file for testing
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                temp_file.write(b"dummy audio content for testing")
                temp_path = temp_file.name

            try:
                with open(temp_path, 'rb') as audio_file:
                    files = {'file': ('test_audio.mp3', audio_file, 'audio/mpeg')}
                    response = self.session.post(f"{self.base_url}/api/transcribe", files=files)
                
                success = response.status_code == 200
                if success:
                    data = response.json()
                    if data.get('success'):
                        transcription = data.get('transcription', {})
                        details = f"- Transcribed: {transcription.get('filename', 'Unknown')}"
                    else:
                        success = False
                        details = "- API returned success=False"
                else:
                    details = f"- Status: {response.status_code}"
                
            finally:
                os.unlink(temp_path)
                
            return self.log_test("Audio Transcription", success, details)
        except Exception as e:
            return self.log_test("Audio Transcription", False, f"- Error: {str(e)}")

    def test_social_posts_get(self):
        """Test get social posts endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/social-posts")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    posts = data.get('posts', [])
                    details = f"- Found {len(posts)} social posts"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Get Social Posts", success, details)
        except Exception as e:
            return self.log_test("Get Social Posts", False, f"- Error: {str(e)}")

    def test_social_posts_fetch(self):
        """Test fetch social posts endpoint"""
        try:
            data = {'keywords': 'test technology'}
            response = self.session.post(f"{self.base_url}/api/social-posts/fetch", data=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    posts = response_data.get('posts', [])
                    details = f"- Fetched {len(posts)} posts for 'test technology'"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Fetch Social Posts", success, details)
        except Exception as e:
            return self.log_test("Fetch Social Posts", False, f"- Error: {str(e)}")

    def test_sentiment_analyses_get(self):
        """Test get sentiment analyses endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment-analyses")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    analyses = data.get('analyses', [])
                    details = f"- Found {len(analyses)} sentiment analyses"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Get Sentiment Analyses", success, details)
        except Exception as e:
            return self.log_test("Get Sentiment Analyses", False, f"- Error: {str(e)}")

    def test_analyze_sentiment(self):
        """Test sentiment analysis endpoint"""
        try:
            data = {'text': 'This is a great application for media monitoring!'}
            response = self.session.post(f"{self.base_url}/api/analyze-sentiment", data=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    analysis = response_data.get('analysis', {})
                    sentiment = analysis.get('sentiment_label', 'Unknown')
                    score = analysis.get('sentiment_score', 0)
                    details = f"- Sentiment: {sentiment} (Score: {score:.2f})"
                else:
                    success = False
                    details = "- API returned success=False"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Analyze Sentiment", success, details)
        except Exception as e:
            return self.log_test("Analyze Sentiment", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Veille Média API Tests")
        print(f"📡 Testing against: {self.base_url}")
        print("=" * 60)

        # Test all endpoints
        self.test_root_endpoint()
        self.test_dashboard_stats()
        self.test_articles_get()
        self.test_articles_fetch()
        self.test_transcriptions_get()
        self.test_transcribe_audio()
        self.test_social_posts_get()
        self.test_social_posts_fetch()
        self.test_sentiment_analyses_get()
        self.test_analyze_sentiment()

        # Print summary
        print("=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! Backend API is working correctly.")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed. Check the issues above.")
            return 1

def main():
    """Main test runner"""
    tester = VeilleMediaAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())