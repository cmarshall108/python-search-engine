#!/usr/bin/env python
import logging
import sys
import time
import threading
import os
import psutil
import json
from urllib.parse import urlparse

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

def log_system_info():
    """Log system information to help diagnose issues"""
    logging.info("=== System Information ===")
    
    # Python version
    logging.info(f"Python version: {sys.version}")
    
    # Process information
    process = psutil.Process(os.getpid())
    logging.info(f"Process ID: {process.pid}")
    logging.info(f"Process name: {process.name()}")
    logging.info(f"Process create time: {process.create_time()}")
    logging.info(f"Working directory: {os.getcwd()}")
    
    # Memory usage
    mem_info = process.memory_info()
    logging.info(f"Memory usage: {mem_info.rss / (1024 * 1024):.2f} MB")
    
    # Thread information
    logging.info(f"Active threads: {threading.active_count()}")
    logging.info(f"Current thread: {threading.current_thread().name}")
    
    # Thread list
    logging.info("Thread list:")
    for thread in threading.enumerate():
        logging.info(f"  - {thread.name} (daemon: {thread.daemon})")

def log_crawler_state(crawler):
    """Log the crawler state in detail"""
    logging.info("=== Crawler State ===")
    
    # Basic state
    logging.info(f"Is crawling: {crawler.is_crawling}")
    logging.info(f"Queue size: {crawler.queue.qsize()}")
    logging.info(f"Visited URLs: {len(crawler.visited_urls)}")
    
    # Stats
    logging.info(f"Stats: {crawler.crawl_stats}")
    
    # Queue inspection (if possible)
    if hasattr(crawler.queue, 'mutex'):
        try:
            with crawler.queue.mutex:
                queue_items = list(crawler.queue.queue)
                if queue_items:
                    logging.info(f"First 5 queue items: {queue_items[:5]}")
                    
                    # Check URL validity for the first few items
                    for i, item in enumerate(queue_items[:5]):
                        try:
                            priority, (url, depth) = item
                            parsed = urlparse(url)
                            if not parsed.netloc:
                                logging.warning(f"Queue item {i} has invalid URL: {url}")
                        except Exception as e:
                            logging.error(f"Error parsing queue item {i}: {e}")
        except Exception as e:
            logging.error(f"Error inspecting queue: {e}")


def monitor_crawler(crawler, url, depth=1, timeout=60):
    """Monitor a crawler as it runs"""
    log_system_info()
    
    # Log initial state
    log_crawler_state(crawler)
    
    # Start the crawler
    logging.info(f"Starting crawler with URL: {url}, depth: {depth}")
    success = crawler.crawl(url, depth)
    
    if not success:
        logging.error("Failed to start crawler")
        return
    
    logging.info("Crawler started, monitoring...")
    
    # Monitor until completed or timeout
    start_time = time.time()
    last_queue_size = crawler.queue.qsize()
    last_crawled = crawler.crawl_stats["crawled"]
    stalled_count = 0
    
    while crawler.is_crawling:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            logging.warning(f"Monitoring timed out after {timeout} seconds")
            break
        
        # Get current state
        stats = crawler.get_stats()
        current_queue_size = crawler.queue.qsize()
        current_crawled = stats["crawled"]
        
        # Check for stalled state (no progress for multiple checks)
        if current_queue_size == last_queue_size and current_crawled == last_crawled:
            stalled_count += 1
            if stalled_count >= 5:  # 5 checks with no progress
                logging.warning("Crawler appears stalled - no progress detected")
                log_crawler_state(crawler)
                dump_stack_traces()
        else:
            stalled_count = 0
        
        # Update last values
        last_queue_size = current_queue_size
        last_crawled = current_crawled
        
        # Log progress
        logging.info(f"Progress: {stats['crawled']} crawled, {stats['indexed']} indexed, "
                     f"{stats['errors']} errors, {current_queue_size} in queue")
        
        # Sleep before next check
        time.sleep(2)
    
    # Log final state
    logging.info("Crawler finished or stopped")
    log_crawler_state(crawler)

def dump_stack_traces():
    """Dump stack traces of all threads to help debug deadlocks"""
    logging.info("=== Thread Stack Traces ===")
    
    for th in threading.enumerate():
        logging.info(f"Thread {th.name}:")
        try:
            import traceback
            for line in traceback.format_stack():
                logging.info(f"  {line.strip()}")
        except Exception as e:
            logging.info(f"  Error getting stack: {e}")

if __name__ == "__main__":
    # Allows for standalone execution to test system environment
    log_system_info()
    
    # Usage example:
    if len(sys.argv) > 1:
        from search import SearchEngine
        from advanced_crawler import SmartCrawler
        
        url = sys.argv[1]
        depth = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        
        # Initialize the search engine
        search_engine = SearchEngine(db_path="search_engine_test.db", use_db=True)
        
        # Create the crawler
        crawler = SmartCrawler(search_engine)
        
        # Monitor the crawler
        monitor_crawler(crawler, url, depth)
