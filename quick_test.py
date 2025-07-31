#!/usr/bin/env python3
"""
Quick Backend Test for Guadeloupe Media Monitoring
"""

import requests
import json
import time

def test_backend():
    base_url = "https://bb8f662d-6347-4222-9f33-1c130098c9a0.preview.emergentagent.com"
    
    print("🚀 Quick Backend Test for Guadeloupe Media Monitoring")
    print(f"📡 Testing: {base_url}")
    print("=" * 60)
    
    # Test health endpoint
    try:
        print("🔍 Testing /api/health...")
        response = requests.get(f"{base_url}/api/health", timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success', 'Unknown')}")
            if data.get('health'):
                services = data['health'].get('services', {})
                print(f"   MongoDB: {services.get('mongodb', 'Unknown')}")
                print(f"   Cache: {services.get('cache', 'Unknown')}")
                print(f"   Scraper: {services.get('scraper', 'Unknown')}")
        else:
            print(f"   Error: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    print()
    
    # Test dashboard stats
    try:
        print("🔍 Testing /api/dashboard-stats...")
        response = requests.get(f"{base_url}/api/dashboard-stats", timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success', 'Unknown')}")
            if data.get('stats'):
                stats = data['stats']
                print(f"   Total Articles: {stats.get('total_articles', 0)}")
                print(f"   Today Articles: {stats.get('today_articles', 0)}")
        else:
            print(f"   Error: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    print()
    
    # Test articles endpoint
    try:
        print("🔍 Testing /api/articles...")
        response = requests.get(f"{base_url}/api/articles", timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success', 'Unknown')}")
            if data.get('articles'):
                articles = data['articles']
                print(f"   Articles Count: {len(articles)}")
                
                # Count by source
                sources = {}
                for article in articles:
                    source = article.get('source', 'Unknown')
                    sources[source] = sources.get(source, 0) + 1
                
                for source, count in sources.items():
                    print(f"   {source}: {count} articles")
        else:
            print(f"   Error: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {str(e)}")
    
    print()
    
    # Test scrape-now endpoint
    try:
        print("🔍 Testing /api/articles/scrape-now...")
        response = requests.post(f"{base_url}/api/articles/scrape-now", timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success', 'Unknown')}")
            print(f"   Message: {data.get('message', 'No message')}")
        else:
            print(f"   Error: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {str(e)}")

if __name__ == "__main__":
    test_backend()