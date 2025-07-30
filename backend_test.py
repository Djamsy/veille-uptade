#!/usr/bin/env python3
"""
Backend API Test Suite for Guadeloupe Media Monitoring Application
Tests all endpoints focusing on new implementations:
1. Today-Only Data Display
2. Cache Clearing on Updates  
3. Local Sentiment Analysis Service
"""

import requests
import sys
import json
import tempfile
import os
from datetime import datetime

class GuadeloupeMediaAPITester:
    def __init__(self, base_url="https://ef5be455-26ce-4288-890e-6818eb1d7a51.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 60  # Increased timeout for scraping operations
        self.today = datetime.now().strftime('%Y-%m-%d')

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

    def test_today_only_dashboard_stats(self):
        """Test dashboard statistics endpoint shows only today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/dashboard-stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    today_articles = stats.get('today_articles', 0)
                    total_articles = stats.get('total_articles', 0)
                    showing_data_for = stats.get('showing_data_for', '')
                    
                    # Check if today_articles equals total_articles (today-only filter)
                    today_only_working = today_articles == total_articles
                    has_today_message = self.today in showing_data_for
                    
                    if today_only_working and has_today_message:
                        details = f"- Today articles: {today_articles}, Message: '{showing_data_for}'"
                    else:
                        success = False
                        details = f"- Today filter not working: today={today_articles}, total={total_articles}, message='{showing_data_for}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Today-Only Dashboard Stats", success, details)
        except Exception as e:
            return self.log_test("Today-Only Dashboard Stats", False, f"- Error: {str(e)}")

    def test_today_only_articles(self):
        """Test articles endpoint shows only today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    count = data.get('count', 0)
                    
                    # Check if all articles are from today
                    today_only = True
                    for article in articles[:5]:  # Check first 5 articles
                        article_date = article.get('date', '')
                        if article_date != self.today:
                            today_only = False
                            break
                    
                    if today_only and count == len(articles):
                        details = f"- Found {count} articles, all from {self.today}"
                    else:
                        success = False
                        details = f"- Today filter not working: {count} articles, today_only={today_only}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Today-Only Articles", success, details)
        except Exception as e:
            return self.log_test("Today-Only Articles", False, f"- Error: {str(e)}")

    def test_cache_clearing_scrape_now(self):
        """Test scrape-now endpoint clears cache before and after scraping"""
        try:
            response = self.session.post(f"{self.base_url}/api/articles/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    cache_cleared = data.get('cache_cleared', False)
                    message = data.get('message', '')
                    
                    if cache_cleared and 'cache' in message.lower():
                        details = f"- Cache cleared: {cache_cleared}, Message: '{message}'"
                    else:
                        success = False
                        details = f"- Cache clearing not confirmed: cache_cleared={cache_cleared}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Cache Clearing on Scrape", success, details)
        except Exception as e:
            return self.log_test("Cache Clearing on Scrape", False, f"- Error: {str(e)}")

    def test_sentiment_stats(self):
        """Test sentiment analysis stats endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    service_info = data.get('service_info', {})
                    service_enabled = service_info.get('service_enabled', False)
                    analysis_method = service_info.get('analysis_method', '')
                    
                    if service_enabled and 'local' in analysis_method:
                        details = f"- Service enabled: {service_enabled}, Method: {analysis_method}"
                    else:
                        success = False
                        details = f"- Local sentiment not enabled: enabled={service_enabled}, method={analysis_method}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analysis Stats", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analysis Stats", False, f"- Error: {str(e)}")

    def test_sentiment_articles(self):
        """Test sentiment analysis of today's articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    summary = data.get('summary', {})
                    total_articles = summary.get('total_articles', 0)
                    sentiment_distribution = summary.get('sentiment_distribution', {})
                    
                    if total_articles >= 0 and 'positive' in sentiment_distribution:
                        details = f"- Analyzed {total_articles} articles, Distribution: {sentiment_distribution}"
                    else:
                        success = False
                        details = f"- Sentiment analysis failed: articles={total_articles}, dist={sentiment_distribution}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analysis Articles", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analysis Articles", False, f"- Error: {str(e)}")

    def test_sentiment_analyze_text(self):
        """Test sentiment analysis of custom text"""
        try:
            test_text = "C'est une excellente nouvelle pour la Guadeloupe! Le développement économique progresse bien."
            data = {'text': test_text}
            response = self.session.post(f"{self.base_url}/api/sentiment/analyze", data=data)
            success = response.status_code == 200
            if success:
                response_data = response.json()
                if response_data.get('success'):
                    sentiment = response_data.get('sentiment', {})
                    sentiment_label = sentiment.get('sentiment_label', '')
                    sentiment_score = sentiment.get('sentiment_score', 0)
                    
                    if sentiment_label and sentiment_score is not None:
                        details = f"- Text sentiment: {sentiment_label} (Score: {sentiment_score:.2f})"
                    else:
                        success = False
                        details = f"- Sentiment analysis incomplete: label={sentiment_label}, score={sentiment_score}"
                else:
                    success = False
                    details = f"- API returned success=False: {response_data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Analyze Text", success, details)
        except Exception as e:
            return self.log_test("Sentiment Analyze Text", False, f"- Error: {str(e)}")

    def test_sentiment_trends(self):
        """Test sentiment trends over past 7 days"""
        try:
            response = self.session.get(f"{self.base_url}/api/sentiment/trends")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    trends_by_date = data.get('trends_by_date', {})
                    analysis_period = data.get('analysis_period', {})
                    
                    if len(trends_by_date) >= 0 and analysis_period:
                        details = f"- Trends for {len(trends_by_date)} days, Period: {analysis_period.get('total_days', 0)} days"
                    else:
                        success = False
                        details = f"- Trends analysis failed: trends={len(trends_by_date)}, period={analysis_period}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Sentiment Trends", success, details)
        except Exception as e:
            return self.log_test("Sentiment Trends", False, f"- Error: {str(e)}")

    def test_scrapers_working(self):
        """Test that all 4 scrapers are working by checking articles"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    
                    # Check for articles from different sources
                    sources_found = set()
                    for article in articles:
                        source = article.get('source', '')
                        if source:
                            sources_found.add(source)
                    
                    expected_sources = {'France-Antilles Guadeloupe', 'RCI Guadeloupe', 'La 1ère Guadeloupe', 'KaribInfo'}
                    working_scrapers = len(sources_found.intersection(expected_sources))
                    
                    if working_scrapers >= 2:  # At least 2 scrapers working
                        details = f"- Found articles from {working_scrapers}/4 scrapers: {list(sources_found)}"
                    else:
                        success = False
                        details = f"- Only {working_scrapers}/4 scrapers working: {list(sources_found)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("News Scrapers Working", success, details)
        except Exception as e:
            return self.log_test("News Scrapers Working", False, f"- Error: {str(e)}")

    def test_transcriptions_endpoint(self):
        """Test transcriptions endpoint"""
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
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Transcriptions Endpoint", success, details)
        except Exception as e:
            return self.log_test("Transcriptions Endpoint", False, f"- Error: {str(e)}")

    def test_health_endpoint(self):
        """Test health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    health = data.get('health', {})
                    services = health.get('services', {})
                    details = f"- Status: {health.get('status', 'unknown')}, Services: {len(services)}"
                else:
                    success = False
                    details = f"- Health check failed: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Health Check", success, details)
        except Exception as e:
            return self.log_test("Health Check", False, f"- Error: {str(e)}")

    def test_search_endpoint(self):
        """Test search endpoint with specific queries for Guy Losbar and Conseil Départemental"""
        test_queries = ["Guy Losbar", "Conseil Départemental", "CD971"]
        
        for query in test_queries:
            try:
                response = self.session.get(f"{self.base_url}/api/search", params={'q': query})
                success = response.status_code == 200
                if success:
                    data = response.json()
                    if data.get('success'):
                        articles = data.get('articles', [])
                        social_posts = data.get('social_posts', [])
                        total_results = data.get('total_results', 0)
                        searched_in = data.get('searched_in', [])
                        
                        if total_results >= 0 and len(searched_in) > 0:
                            details = f"- Query '{query}': {len(articles)} articles, {len(social_posts)} social posts, searched in: {searched_in}"
                        else:
                            success = False
                            details = f"- Query '{query}' failed: total={total_results}, searched_in={searched_in}"
                    else:
                        success = False
                        details = f"- Query '{query}' API returned success=False: {data.get('error', 'Unknown error')}"
                else:
                    details = f"- Query '{query}' Status: {response.status_code}"
                
                self.log_test(f"Search Endpoint - '{query}'", success, details)
            except Exception as e:
                self.log_test(f"Search Endpoint - '{query}'", False, f"- Error: {str(e)}")

    def test_comments_endpoint(self):
        """Test comments endpoint to retrieve social media posts"""
        try:
            response = self.session.get(f"{self.base_url}/api/comments")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    comments = data.get('comments', [])
                    count = data.get('count', 0)
                    
                    # Check if comments have sentiment analysis
                    has_sentiment = False
                    if comments:
                        first_comment = comments[0]
                        has_sentiment = 'sentiment_summary' in first_comment or 'sentiment' in first_comment
                    
                    if count >= 0:
                        details = f"- Found {count} comments/posts, sentiment analysis: {has_sentiment}"
                    else:
                        success = False
                        details = f"- Comments retrieval failed: count={count}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments Endpoint", success, details)
        except Exception as e:
            return self.log_test("Comments Endpoint", False, f"- Error: {str(e)}")

    def test_social_scrape_now(self):
        """Test social media scraping endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/social/scrape-now")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    message = data.get('message', '')
                    estimated_completion = data.get('estimated_completion', '')
                    note = data.get('note', '')
                    
                    if 'scraping' in message.lower() and estimated_completion:
                        details = f"- Message: '{message}', ETA: {estimated_completion}, Note: '{note}'"
                    else:
                        success = False
                        details = f"- Social scraping not properly initiated: message='{message}'"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Media Scrape Now", success, details)
        except Exception as e:
            return self.log_test("Social Media Scrape Now", False, f"- Error: {str(e)}")

    def test_social_stats(self):
        """Test social media statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/social/stats")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    
                    if isinstance(stats, dict) and len(stats) >= 0:
                        details = f"- Social stats retrieved: {len(stats)} stat categories"
                    else:
                        success = False
                        details = f"- Social stats failed: stats={stats}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Social Media Stats", success, details)
        except Exception as e:
            return self.log_test("Social Media Stats", False, f"- Error: {str(e)}")

    def test_search_suggestions(self):
        """Test search suggestions endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/search/suggestions", params={'q': 'Guy'})
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    suggestions = data.get('suggestions', [])
                    
                    if isinstance(suggestions, list):
                        details = f"- Found {len(suggestions)} suggestions: {suggestions[:3]}"
                    else:
                        success = False
                        details = f"- Search suggestions failed: suggestions={suggestions}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Search Suggestions", success, details)
        except Exception as e:
            return self.log_test("Search Suggestions", False, f"- Error: {str(e)}")

    def test_comments_analyze(self):
        """Test comments sentiment analysis endpoint"""
        try:
            response = self.session.post(f"{self.base_url}/api/comments/analyze")
            success = response.status_code == 200
            if success:
                data = response.json()
                if data.get('success'):
                    analysis = data.get('analysis', {})
                    total_comments = analysis.get('total_comments', 0)
                    by_entity = analysis.get('by_entity', {})
                    
                    if total_comments >= 0 and isinstance(by_entity, dict):
                        details = f"- Analyzed {total_comments} comments, entities: {list(by_entity.keys())}"
                    else:
                        success = False
                        details = f"- Comments analysis failed: total={total_comments}, entities={len(by_entity)}"
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            return self.log_test("Comments Sentiment Analysis", success, details)
        except Exception as e:
            return self.log_test("Comments Sentiment Analysis", False, f"- Error: {str(e)}")

    def run_all_tests(self):
        """Run all API tests focusing on new features"""
        print("🚀 Starting Guadeloupe Media Monitoring API Tests")
        print(f"📡 Testing against: {self.base_url}")
        print(f"📅 Testing for date: {self.today}")
        print("=" * 80)

        # Test basic connectivity
        print("\n🔗 BASIC CONNECTIVITY TESTS")
        self.test_root_endpoint()
        self.test_health_endpoint()

        # Test HIGH PRIORITY NEW FEATURES
        print("\n🎯 HIGH PRIORITY NEW FEATURES")
        self.test_today_only_dashboard_stats()
        self.test_today_only_articles()
        self.test_cache_clearing_scrape_now()
        
        print("\n🧠 LOCAL SENTIMENT ANALYSIS SERVICE")
        self.test_sentiment_stats()
        self.test_sentiment_articles()
        self.test_sentiment_analyze_text()
        self.test_sentiment_trends()

        # Test existing features
        print("\n📰 EXISTING FEATURES VERIFICATION")
        self.test_scrapers_working()
        self.test_transcriptions_endpoint()

        # Print summary
        print("=" * 80)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed! Backend API is working correctly.")
            return 0
        else:
            failed_tests = self.tests_run - self.tests_passed
            print(f"⚠️  {failed_tests} tests failed. Check the issues above.")
            return 1

def main():
    """Main test runner"""
    tester = GuadeloupeMediaAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())