#!/usr/bin/env python
"""
Direct crawler execution script for testing and debugging
"""

import logging
import sys
import time
import os
import traceback
import signal

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,  # Use DEBUG for most detailed output
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Import our modules
from .search import SearchEngine
from .advanced_crawler import SmartCrawler

def signal_handler(sig, frame):
    print("\nCrawler interrupted. Exiting gracefully...")
    sys.exit(0)

def direct_crawl(url, depth=1, db_path="debug_search_engine.db"):
    """Direct crawl without Tornado event loops or WebSockets"""
    print(f"\n🔍 Direct crawling of {url} with depth {depth}")
    
    # Initialize the search engine with debug DB
    search_engine = SearchEngine(db_path=db_path, use_db=True)
    
    # Create the crawler without WebSockets
    crawler = SmartCrawler(search_engine, [])
    
    # Set up custom debug checking
    def check_progress():
        while crawler.is_crawling:
            stats = crawler.get_stats()
            
            # Print detailed stats every 2 seconds
            print(f"\n--- Crawler Status at {time.strftime('%H:%M:%S')} ---")
            print(f"Status: {stats['status']}")
            print(f"Queue size: {stats['queue_size']}")
            print(f"Pages crawled: {stats['crawled']}")
            print(f"Pages indexed: {stats['indexed']}")
            print(f"Errors: {stats['errors']}")
            
            # Print current processing URL
            if 'current_url' in stats:
                print(f"Current URL: {stats['current_url']}")
            
            # This is a direct script, so using time.sleep is fine
            time.sleep(2)
    
    # Start the crawler
    print(f"Starting crawler with URL: {url}")
    success = crawler.crawl(url, depth)
    
    if not success:
        print("Failed to start crawler")
        return False
    
    # Monitor the crawling process in the main thread
    try:
        check_progress()
    except KeyboardInterrupt:
        print("\nCrawler interrupted by user")
    
    # Wait for completion
    while crawler.is_crawling:
        time.sleep(0.5)
    
    # Final stats
    final_stats = crawler.get_stats()
    print("\nFinal crawler stats:")
    print(f"Status: {final_stats['status']}")
    print(f"Pages crawled: {final_stats['crawled']}")
    print(f"Pages indexed: {final_stats['indexed']}")
    print(f"Errors: {final_stats['errors']}")
    
    # Test search
    if final_stats['indexed'] > 0:
        print("\nTesting search functionality:")
        results, count = search_engine.search("example")
        print(f"Found {count} results for 'example'")
        for i, result in enumerate(results[:3], 1):
            print(f"{i}. {result['title']} - {result['url']}")
    
    return True

if __name__ == "__main__":
    # Register signal handler for graceful exit
    signal.signal(signal.SIGINT, signal_handler)
    
    # Get URL from command line or use default
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    direct_crawl(url, depth)
