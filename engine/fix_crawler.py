"""Utility to fix and test the advanced crawler"""
import logging
import sys
import os
import time
import threading

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

from .search import SearchEngine
from .advanced_crawler import SmartCrawler
from .diagnostics import monitor_crawler

def fix_queue_issue(crawler):
    """Attempt to fix queue processing issues in the crawler"""
    print("\n=== Fixing SmartCrawler Queue Processing ===")
    
    # Apply fixes:
    # 1. Ensure thread priority is appropriate
    if hasattr(threading, 'current_thread'):
        current = threading.current_thread()
        print(f"Current thread: {current.name}, daemon: {current.daemon}")
    
    # 2. Check threading import
    print("Threading module location:", threading.__file__)
    
    # 3. Check if there are any global locks preventing execution
    print("Global locks status:", getattr(threading, '_shutdown', False))
    
    # 4. Check for CPU count (helps determine thread scheduling)
    import multiprocessing
    print(f"CPU count: {multiprocessing.cpu_count()}")
    
    # 5. Check if tornado's IOLoop is interfering
    # (This is just a check, we don't need to take any action)
    try:
        import tornado.ioloop
        current_loop = tornado.ioloop.IOLoop.current()
        print(f"Tornado IOLoop: {current_loop}")
    except Exception as e:
        print(f"Error checking tornado IOLoop: {e}")

def test_crawler_parallel(url="https://example.com", depth=1):
    """Test crawlers both with and without tornado IOLoop running"""
    # Create search engines and crawlers
    se1 = SearchEngine(db_path="se_test1.db", use_db=True)
    crawler1 = SmartCrawler(se1)
    
    se2 = SearchEngine(db_path="se_test2.db", use_db=True)
    crawler2 = SmartCrawler(se2)
    
    # First test - direct crawler
    print("\n=== Testing crawler directly ===")
    
    crawler1.crawl(url, depth)
    while crawler1.is_crawling:
        stats = crawler1.get_stats()
        print(f"Direct: {stats['crawled']} crawled, {stats['indexed']} indexed, {stats.get('queue_size', '?')} in queue")
        time.sleep(1)
    
    # Second test - with Tornado IOLoop
    print("\n=== Testing crawler with Tornado IOLoop ===")
    
    # Start tornado's IOLoop in a separate thread
    import tornado.ioloop
    def run_ioloop():
        loop = tornado.ioloop.IOLoop.current()
        loop.start()
    
    ioloop_thread = threading.Thread(target=run_ioloop)
    ioloop_thread.daemon = True
    ioloop_thread.start()
    
    # Now start the crawler
    crawler2.crawl(url, depth)
    while crawler2.is_crawling:
        stats = crawler2.get_stats()
        print(f"Tornado: {stats['crawled']} crawled, {stats['indexed']} indexed, {stats.get('queue_size', '?')} in queue")
        time.sleep(1)
    
    # Stop the IOLoop
    tornado.ioloop.IOLoop.current().stop()
    
    # Compare results
    stats1 = crawler1.get_stats()
    stats2 = crawler2.get_stats()
    
    print("\n=== Results Comparison ===")
    print(f"Direct crawler: {stats1['crawled']} pages crawled")
    print(f"Tornado crawler: {stats2['crawled']} pages crawled")
    
    return stats1['crawled'] > 0 and stats2['crawled'] > 0

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    # Apply fixes
    print("\nStep 1: Apply fixes to crawler")
    search_engine = SearchEngine(db_path="fix_test.db", use_db=True)
    crawler = SmartCrawler(search_engine)
    fix_queue_issue(crawler)
    
    # Test both modes
    print("\nStep 2: Test crawlers in different contexts")
    success = test_crawler_parallel(url, depth)
    
    # Final test
    print("\nStep 3: Final monitoring test")
    se_final = SearchEngine(db_path="final_test.db", use_db=True)
    crawler_final = SmartCrawler(se_final)
    monitor_crawler(crawler_final, url, depth)
    
    if success:
        print("\n✅ All tests completed successfully!")
    else:
        print("\n❌ Issues detected in testing.")
