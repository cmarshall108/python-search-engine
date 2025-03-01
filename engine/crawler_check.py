#!/usr/bin/env python
import logging
import sys
import time
import traceback
import requests
from urllib.parse import urlparse
import argparse
import threading

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Import our modules
from .search import SearchEngine
from .advanced_crawler import SmartCrawler
from .crawler import Crawler

def verify_url(url):
    """Verify if a URL is accessible"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 CrawlerCheck/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml'
        }
        response = requests.head(url, headers=headers, timeout=5)
        print(f"URL check result: {response.status_code} {response.reason}")
        return response.status_code < 400
    except Exception as e:
        print(f"Error checking URL: {e}")
        return False

def test_crawler(url="https://example.com", use_smart=True):
    """Test if the crawler can successfully process a simple URL"""
    print(f"\n🔍 Testing {'SmartCrawler' if use_smart else 'Crawler'} with {url}")
    
    # First verify if URL is accessible
    print(f"\nVerifying URL accessibility...")
    if not verify_url(url):
        print(f"⚠️ Warning: URL {url} appears to be inaccessible. Continuing anyway...")
    
    # Initialize the search engine
    search_engine = SearchEngine(db_path="search_engine_test.db", use_db=True)
    
    # Create the crawler
    crawler_class = SmartCrawler if use_smart else Crawler
    crawler = crawler_class(search_engine)
    
    # Monitor the crawler queue
    def monitor_queue():
        last_size = -1
        while crawler.is_crawling:
            try:
                current_size = crawler.queue.qsize()
                if current_size != last_size:
                    print(f"Queue size changed: {last_size} → {current_size}")
                    last_size = current_size
                time.sleep(1)
            except:
                break
    
    monitor_thread = threading.Thread(target=monitor_queue)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    # Start crawling
    print(f"Starting crawler with URL: {url}")
    success = crawler.crawl(url, depth=1)
    if not success:
        print("Failed to start crawler")
        return
    
    # Wait for crawling to finish (with timeout)
    max_wait = 60  # seconds
    start_time = time.time()
    
    print("Waiting for crawler to finish...")
    try:
        while crawler.is_crawling:
            elapsed = time.time() - start_time
            if elapsed > max_wait:
                print(f"Crawler still running after {max_wait} seconds, stopping test")
                break
                
            stats = crawler.get_stats()
            print(f"Progress: {stats['crawled']} crawled, {stats['indexed']} indexed, " +
                  f"{stats['errors']} errors, {stats.get('queue_size', '?')} in queue")
            
            if stats['crawled'] > 0 or stats['errors'] > 0:
                print(f"Current URL: {stats['current_url']}")
                
            time.sleep(2)
    except KeyboardInterrupt:
        print("Test interrupted")
    except Exception as e:
        print(f"Error during test: {e}")
        traceback.print_exc()
    
    # Check results
    stats = crawler.get_stats()
    print("\nFinal crawler stats:")
    print(f"Status: {stats['status']}")
    print(f"Pages crawled: {stats['crawled']}")
    print(f"Pages indexed: {stats['indexed']}")
    print(f"Errors: {stats['errors']}")
    print(f"Queue size: {stats.get('queue_size', 'unknown')}")
    
    if stats['crawled'] == 0 and stats['errors'] == 0:
        print("\n⚠️ WARNING: Crawler finished without processing any URLs!")
        
        # Look for recently visited URLs in DB if available
        if hasattr(crawler, 'db') and crawler.db:
            try:
                from datetime import datetime, timedelta
                yesterday = (datetime.now() - timedelta(days=1)).isoformat()
                with crawler.db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT url, visit_date FROM crawler_visits WHERE visit_date > ? LIMIT 5', (yesterday,))
                    recent_visits = cursor.fetchall()
                    if recent_visits:
                        print("\nRecently visited URLs in database:")
                        for row in recent_visits:
                            print(f"- {row['url']} ({row['visit_date']})")
                    else:
                        print("No recently visited URLs found in database")
            except Exception as e:
                print(f"Error checking database: {e}")
    
    # Print additional debug information for SmartCrawler
    if use_smart:
        print("\nAdditional SmartCrawler debug info:")
        print(f"- Domain importance scores: {len(crawler.domain_importance)} entries")
        print(f"- Content fingerprints: {len(crawler.content_fingerprints)} entries")
        print(f"- Robot cache entries: {len(crawler.robots_cache)} entries")
    
    return stats

def test_url_fetching(url):
    """Test just the URL fetching part"""
    print(f"\n🌐 Testing URL fetching for: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 SmartCrawler/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'en-US,en;q=0.9'
        }
        
        print("Sending HTTP request...")
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status code: {response.status_code}")
        print(f"Content type: {response.headers.get('Content-Type', 'unknown')}")
        print(f"Content length: {len(response.text)} characters")
        
        if 'text/html' in response.headers.get('Content-Type', '').lower():
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            
            title = "No title found"
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            
            print(f"Page title: {title}")
            
            links = len(soup.find_all("a", href=True))
            print(f"Found {links} links on the page")
            
            return True
        else:
            print(f"Warning: Content is not HTML")
            return False
    except Exception as e:
        print(f"Error fetching URL: {e}")
        traceback.print_exc()
        return False

def test_queue_operations():
    """Test basic queue operations to verify it's working properly"""
    print("\n🧪 Testing PriorityQueue operations")
    
    from queue import PriorityQueue
    
    # Create a queue
    pq = PriorityQueue()
    
    # Test adding items
    print("Adding items to queue...")
    test_items = [
        (2, ("https://example.com/page2", 1)),
        (1, ("https://example.com/page1", 0)), 
        (3, ("https://example.com/page3", 2))
    ]
    
    for item in test_items:
        pq.put(item)
        print(f"Added: {item}")
    
    print(f"Queue size: {pq.qsize()}")
    
    # Test getting items (should come out in priority order)
    print("\nRetrieving items from queue...")
    while not pq.empty():
        item = pq.get()
        print(f"Got: {item}")
        pq.task_done()
    
    print(f"Queue empty? {pq.empty()}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Test crawler functionality')
    parser.add_argument('--url', default='https://example.com', help='URL to test crawling')
    parser.add_argument('--mode', choices=['crawl', 'fetch', 'queue'], default='crawl', 
                        help='Test mode: crawl, fetch, or queue operations')
    parser.add_argument('--basic', action='store_true', help='Use basic Crawler instead of SmartCrawler')
    args = parser.parse_args()
    
    if args.mode == 'crawl':
        print("===== Testing Crawler =====")
        test_crawler(url=args.url, use_smart=not args.basic)
    elif args.mode == 'fetch':
        print("===== Testing URL Fetching =====")
        test_url_fetching(args.url)
    elif args.mode == 'queue':
        print("===== Testing Queue Operations =====")
        test_queue_operations()
    else:
        print(f"Unknown mode: {args.mode}")

if __name__ == "__main__":
    main()
