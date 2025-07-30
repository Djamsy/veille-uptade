#!/usr/bin/env python3
"""
Priority Backend API Test Suite for Guadeloupe Media Monitoring Application
Tests focused on priority areas: 4 News Scrapers, Intelligent Caching, and API Endpoints
"""

import requests
import sys
import json
import time
from datetime import datetime

class GuadeloupeMediaAPITester:
    def __init__(self, base_url="https://a0cf0419-f055-4e25-b209-04f98074de7d.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 60  # Increased timeout for scraping operations
        self.scraper_results = {}
        self.cache_test_results = {}

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

    def test_scrape_now_endpoint(self):
        """Test the scrape-now endpoint that triggers all scrapers"""
        try:
            print("🔍 Testing scrape-now endpoint (this may take 2-3 minutes)...")
            response = self.session.post(f"{self.base_url}/api/articles/scrape-now")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                if data.get('success'):
                    details = f"- Message: {data.get('message', 'Scraping started')}"
                    # Wait a bit and check scrape status
                    time.sleep(5)
                    self.check_scrape_status()
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            
            return self.log_test("Scrape Now Endpoint", success, details)
        except Exception as e:
            return self.log_test("Scrape Now Endpoint", False, f"- Error: {str(e)}")

    def check_scrape_status(self):
        """Check the status of the last scraping operation"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles/scrape-status")
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('result'):
                    result = data['result']
                    print(f"   📊 Scrape Status: {result.get('success', 'Unknown')}")
                    if 'articles_by_site' in result:
                        for site, count in result['articles_by_site'].items():
                            print(f"   📰 {site}: {count} articles")
                    self.scraper_results = result
        except Exception as e:
            print(f"   ⚠️ Could not check scrape status: {e}")

    def test_articles_today_endpoint(self):
        """Test the articles today endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/articles")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                if data.get('success'):
                    articles = data.get('articles', [])
                    count = len(articles)
                    
                    # Check for articles from each expected source
                    sources = {}
                    for article in articles:
                        source = article.get('source', 'Unknown')
                        sources[source] = sources.get(source, 0) + 1
                    
                    details = f"- Total: {count} articles"
                    for source, source_count in sources.items():
                        details += f", {source}: {source_count}"
                    
                    # Success if we have articles from multiple sources
                    if count > 0 and len(sources) > 1:
                        success = True
                    elif count == 0:
                        success = False
                        details += " (No articles found - may need to run scraping first)"
                    else:
                        success = True  # At least some articles found
                        
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            
            return self.log_test("Articles Today Endpoint", success, details)
        except Exception as e:
            return self.log_test("Articles Today Endpoint", False, f"- Error: {str(e)}")

    def test_dashboard_stats_endpoint(self):
        """Test dashboard statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/dashboard-stats")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                if data.get('success'):
                    stats = data.get('stats', {})
                    total_articles = stats.get('total_articles', 0)
                    today_articles = stats.get('today_articles', 0)
                    cache_stats = stats.get('cache_stats', {})
                    
                    details = f"- Total: {total_articles}, Today: {today_articles}"
                    if cache_stats:
                        details += f", Cache: {cache_stats.get('status', 'unknown')}"
                    
                    # Success if we get valid stats structure
                    success = True
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            
            return self.log_test("Dashboard Stats Endpoint", success, details)
        except Exception as e:
            return self.log_test("Dashboard Stats Endpoint", False, f"- Error: {str(e)}")

    def test_cache_functionality(self):
        """Test cache functionality by calling same endpoint twice"""
        try:
            print("🔍 Testing cache functionality with dashboard stats...")
            
            # First call - should compute
            start_time = time.time()
            response1 = self.session.get(f"{self.base_url}/api/dashboard-stats")
            first_call_time = time.time() - start_time
            
            if response1.status_code != 200:
                return self.log_test("Cache Functionality", False, f"- First call failed: {response1.status_code}")
            
            # Second call - should use cache (faster)
            start_time = time.time()
            response2 = self.session.get(f"{self.base_url}/api/dashboard-stats")
            second_call_time = time.time() - start_time
            
            if response2.status_code != 200:
                return self.log_test("Cache Functionality", False, f"- Second call failed: {response2.status_code}")
            
            # Compare response times and data consistency
            data1 = response1.json()
            data2 = response2.json()
            
            # Check if data is consistent
            consistent_data = (data1.get('success') == data2.get('success') and
                             data1.get('stats', {}).get('total_articles') == data2.get('stats', {}).get('total_articles'))
            
            details = f"- First: {first_call_time:.3f}s, Second: {second_call_time:.3f}s, Consistent: {consistent_data}"
            
            # Success if both calls work and data is consistent
            success = consistent_data
            
            self.cache_test_results = {
                'first_call_time': first_call_time,
                'second_call_time': second_call_time,
                'consistent_data': consistent_data
            }
            
            return self.log_test("Cache Functionality", success, details)
        except Exception as e:
            return self.log_test("Cache Functionality", False, f"- Error: {str(e)}")

    def test_cache_stats_endpoint(self):
        """Test cache statistics endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/cache/stats")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                if data.get('success'):
                    cache_stats = data.get('cache_stats', {})
                    total_keys = cache_stats.get('total_cached_keys', 0)
                    valid_keys = cache_stats.get('valid_cached_keys', 0)
                    
                    details = f"- Total keys: {total_keys}, Valid keys: {valid_keys}"
                    success = True
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            
            return self.log_test("Cache Stats Endpoint", success, details)
        except Exception as e:
            return self.log_test("Cache Stats Endpoint", False, f"- Error: {str(e)}")

    def test_health_check_endpoint(self):
        """Test health check endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/api/health")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                if data.get('success'):
                    health = data.get('health', {})
                    services = health.get('services', {})
                    
                    mongodb_status = services.get('mongodb', 'unknown')
                    cache_status = services.get('cache', 'unknown')
                    scraper_status = services.get('scraper', 'unknown')
                    
                    details = f"- MongoDB: {mongodb_status}, Cache: {cache_status}, Scraper: {scraper_status}"
                    
                    # Success if key services are working
                    success = mongodb_status == 'connected' and scraper_status == 'ready'
                else:
                    success = False
                    details = f"- API returned success=False: {data.get('error', 'Unknown error')}"
            else:
                details = f"- Status: {response.status_code}"
            
            return self.log_test("Health Check Endpoint", success, details)
        except Exception as e:
            return self.log_test("Health Check Endpoint", False, f"- Error: {str(e)}")

    def test_individual_scraper_endpoints(self):
        """Test individual scraper endpoints if they exist"""
        scrapers = ['france_antilles', 'rci', 'la1ere', 'karibinfo']
        
        for scraper in scrapers:
            try:
                # Try to find an endpoint for individual scrapers
                # This might not exist in current implementation, so we'll check
                response = self.session.get(f"{self.base_url}/api/scrape/{scraper}")
                
                if response.status_code == 404:
                    # Endpoint doesn't exist, which is fine
                    print(f"   ℹ️ Individual scraper endpoint /api/scrape/{scraper} not implemented")
                    continue
                
                success = response.status_code == 200
                if success:
                    data = response.json()
                    if data.get('success'):
                        articles = data.get('articles', [])
                        details = f"- {scraper}: {len(articles)} articles"
                    else:
                        success = False
                        details = f"- {scraper}: API returned success=False"
                else:
                    details = f"- {scraper}: Status {response.status_code}"
                
                self.log_test(f"Scraper {scraper.title()}", success, details)
                
            except Exception as e:
                self.log_test(f"Scraper {scraper.title()}", False, f"- Error: {str(e)}")

    def run_priority_tests(self):
        """Run priority tests focused on scrapers, cache, and key APIs"""
        print("🚀 Starting Guadeloupe Media Monitoring Priority Tests")
        print(f"📡 Testing against: {self.base_url}")
        print("🎯 Focus: 4 News Scrapers, Intelligent Caching, API Endpoints")
        print("=" * 80)

        # Core functionality tests
        print("\n📋 CORE FUNCTIONALITY TESTS")
        print("-" * 40)
        self.test_root_endpoint()
        self.test_health_check_endpoint()

        # Scraper tests
        print("\n🗞️ NEWS SCRAPER TESTS")
        print("-" * 40)
        self.test_scrape_now_endpoint()
        self.test_articles_today_endpoint()
        self.test_individual_scraper_endpoints()

        # Cache tests
        print("\n💾 INTELLIGENT CACHE TESTS")
        print("-" * 40)
        self.test_cache_functionality()
        self.test_cache_stats_endpoint()

        # API endpoint tests
        print("\n🔌 API ENDPOINT TESTS")
        print("-" * 40)
        self.test_dashboard_stats_endpoint()

        # Print detailed summary
        print("\n" + "=" * 80)
        print("📊 DETAILED TEST RESULTS")
        print("=" * 80)
        
        print(f"Overall: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.scraper_results:
            print("\n🗞️ SCRAPER RESULTS:")
            if self.scraper_results.get('success'):
                total_articles = self.scraper_results.get('total_articles', 0)
                print(f"   Total articles scraped: {total_articles}")
                
                articles_by_site = self.scraper_results.get('articles_by_site', {})
                for site, count in articles_by_site.items():
                    expected_counts = {
                        'france_antilles': 15,
                        'rci': 20,
                        'la1ere': 14,
                        'karibinfo': 15
                    }
                    expected = expected_counts.get(site, 'unknown')
                    status = "✅" if count > 0 else "❌"
                    print(f"   {status} {site}: {count} articles (expected ~{expected})")
            else:
                print(f"   ❌ Scraping failed: {self.scraper_results.get('error', 'Unknown error')}")
        
        if self.cache_test_results:
            print("\n💾 CACHE RESULTS:")
            first_time = self.cache_test_results.get('first_call_time', 0)
            second_time = self.cache_test_results.get('second_call_time', 0)
            consistent = self.cache_test_results.get('consistent_data', False)
            
            print(f"   First call: {first_time:.3f}s")
            print(f"   Second call: {second_time:.3f}s")
            print(f"   Data consistent: {'✅' if consistent else '❌'}")
            
            if second_time < first_time:
                print("   ✅ Cache appears to be working (second call faster)")
            else:
                print("   ⚠️ Cache may not be working optimally")

        print("\n🎯 PRIORITY AREAS STATUS:")
        print("   🗞️ News Scrapers: Testing completed")
        print("   💾 Intelligent Cache: Testing completed") 
        print("   🔌 API Endpoints: Testing completed")
        
        if self.tests_passed == self.tests_run:
            print("\n🎉 All priority tests passed! Backend is working correctly.")
            return 0
        else:
            failed_count = self.tests_run - self.tests_passed
            print(f"\n⚠️ {failed_count} tests failed. Check the issues above.")
            return 1

def main():
    """Main test runner"""
    tester = GuadeloupeMediaAPITester()
    return tester.run_priority_tests()

if __name__ == "__main__":
    sys.exit(main())