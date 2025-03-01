import threading
import requests
import logging
import time
import json
import re
import hashlib
import gzip
import pickle
import io
import os
import math
import heapq
import queue
import urllib.robotparser
import tornado.ioloop
import traceback
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
from queue import PriorityQueue
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from queue import Empty as QueueEmpty

# Import here - before we disable warnings
from .db import SearchDatabase
import urllib3

from .crawler import Crawler

# Disable insecure request warnings when we need to use verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SmartCrawler(Crawler):
    
    def __init__(self, search_engine, websocket_clients=None):
        self.search_engine = search_engine
        self.websocket_clients = websocket_clients if websocket_clients is not None else []
        self.visited_urls = set()
        self.queue = PriorityQueue()  # Priority queue for importance-based crawling
        self.is_crawling = False
        self.lock = threading.Lock()
        self.crawler_thread = None  # Track the crawler thread
        self.thread_heartbeat = 0   # Heartbeat timestamp to monitor thread health
        
        # Crawler statistics
        self.crawl_stats = {
            "crawled": 0,
            "queued": 0,
            "indexed": 0,
            "errors": 0,
            "skipped_duplicates": 0,
            "start_time": 0,
            "status": "idle",
            "current_url": "",
            "recent_urls": [],
            "domains_crawled": 0,
            "content_types": {},
            "robots_blocked": 0
        }
        
        # Check if using database-backed search engine
        self.use_db = getattr(self.search_engine, 'use_db', False)
        self.db = getattr(self.search_engine, 'db', None) if self.use_db else None
        
        # Rate limiting by domain
        self.domain_access_times = {}
        self.min_crawl_delay = 1.0  # Default 1 second between requests to same domain
        
        # Robot exclusion handling
        self.robots_cache = {}
        self.robots_cache_expiry = {}
        
        # Content fingerprinting for duplicate detection
        self.content_fingerprints = {}
        
        # Domain importance scores (initially empty)
        self.domain_importance = {}
        
        # Configure from settings
        self.load_settings()
        
        # Set up thread monitoring
        self._setup_thread_monitor()

    def _setup_thread_monitor(self):
        """Set up periodic thread health monitoring"""
        interval_ms = 30000  # Check every 30 seconds
        
        def check_thread_health():
            # Only check if we believe we're crawling
            if self.is_crawling:
                # Check if thread is alive
                if not self.crawler_thread or not self.crawler_thread.is_alive():
                    logging.error("Crawler thread died but is_crawling flag is still True")
                    self._reset_crawler_state()
                # Check heartbeat (if no heartbeat for 60 seconds, consider thread stuck)
                elif time.time() - self.thread_heartbeat > 60:
                    logging.error("Crawler thread appears stuck (no heartbeat)")
                    self._broadcast_update({"status": "warning", "message": "Crawler appears stuck"})
            
            # Schedule next check
            tornado.ioloop.IOLoop.current().call_later(interval_ms/1000, check_thread_health)
        
        # Start the monitoring
        tornado.ioloop.IOLoop.current().call_later(interval_ms/1000, check_thread_health)

    def _reset_crawler_state(self):
        """Reset the crawler state when detecting issues"""
        with self.lock:
            logging.warning("Forcibly resetting crawler state")
            self.is_crawling = False
            self.crawl_stats["status"] = "reset"
            self.save_state("crawler_emergency_state.gz")  # Save emergency state
            self._broadcast_update({
                "status": "reset", 
                "message": "Crawler state was reset due to detected issues"
            })

    def load_settings(self):
        """Load crawler settings"""
        try:
            settings_file = os.path.join(os.path.dirname(__file__), 'crawler_settings.json')
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                    
                self.min_crawl_delay = settings.get('min_crawl_delay', 1.0)
                
                # Load domain importance if defined
                if 'domain_importance' in settings:
                    self.domain_importance = settings['domain_importance']
                    
                # Load other settings as needed
        except Exception as e:
            logging.error(f"Error loading crawler settings: {e}")
    
    def save_state(self, filename="crawler_state.gz"):
        """Save crawler state to compressed file for resuming later"""
        try:
            state = {
                "visited_urls": list(self.visited_urls),
                "queue": list(self.queue.queue),
                "crawl_stats": self.crawl_stats,
                "domain_access_times": self.domain_access_times,
                "content_fingerprints": self.content_fingerprints
            }
            
            with gzip.open(filename, 'wb') as f:
                pickle.dump(state, f)
            
            logging.info(f"Crawler state saved to {filename}")
            return True
        except Exception as e:
            logging.error(f"Error saving crawler state: {e}")
            return False
    
    def load_state(self, filename="crawler_state.gz"):
        """Load crawler state for resuming a previous crawl"""
        try:
            if not os.path.exists(filename):
                return False
                
            with gzip.open(filename, 'rb') as f:
                state = pickle.load(f)
            
            self.visited_urls = set(state["visited_urls"])
            
            # Recreate the priority queue
            self.queue = PriorityQueue()
            for item in state["queue"]:
                self.queue.put(item)
            
            # Restore other state
            self.crawl_stats = state["crawl_stats"]
            self.domain_access_times = state["domain_access_times"]
            self.content_fingerprints = state["content_fingerprints"]
            
            logging.info(f"Crawler state loaded from {filename}")
            return True
        except Exception as e:
            logging.error(f"Error loading crawler state: {e}")
            return False
    
    def is_allowed_by_robots(self, url):
        """Check if URL is allowed by robots.txt rules"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Get the root URL for robots.txt
            scheme = parsed_url.scheme
            robots_url = f"{scheme}://{domain}/robots.txt"
            
            # Check cache first
            if domain in self.robots_cache:
                # Check if cache has expired (24 hour cache)
                if domain in self.robots_cache_expiry and datetime.now() < self.robots_cache_expiry[domain]:
                    rp = self.robots_cache[domain]
                else:
                    # Expired, fetch again
                    rp = urllib.robotparser.RobotFileParser()
                    rp.set_url(robots_url)
                    try:
                        rp.read()
                    except urllib.error.URLError as e:
                        logging.warning(f"SSL error reading robots.txt for {domain}: {e}. Assuming allowed.")
                        # Create a permissive parser that allows everything when there's an SSL error
                        rp = urllib.robotparser.RobotFileParser()
                        # Set an empty ruleset (which allows everything by default)
                        rp.parse([])
                    self.robots_cache[domain] = rp
                    self.robots_cache_expiry[domain] = datetime.now() + timedelta(hours=24)
            else:
                # Not in cache, fetch it
                rp = urllib.robotparser.RobotFileParser()
                rp.set_url(robots_url)
                try:
                    rp.read()
                except urllib.error.URLError as e:
                    logging.warning(f"SSL error reading robots.txt for {domain}: {e}. Assuming allowed.")
                    # Create a permissive parser that allows everything when there's an SSL error
                    rp = urllib.robotparser.RobotFileParser()
                    # Set an empty ruleset (which allows everything by default)
                    rp.parse([])
                self.robots_cache[domain] = rp
                self.robots_cache_expiry[domain] = datetime.now() + timedelta(hours=24)
                
            # Get crawl delay
            crawl_delay = rp.crawl_delay("*")
            if crawl_delay:
                self.domain_access_times[domain] = max(
                    self.min_crawl_delay,
                    crawl_delay
                )
            
            # Check if URL is allowed
            return rp.can_fetch("*", url)
        except Exception as e:
            logging.warning(f"Error checking robots.txt for {url}: {e}")
            return True  # Default to allowing if robots.txt check fails
    
    def compute_url_priority(self, url, depth, source_importance=5):
        """Compute priority for URL (lower number = higher priority)"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Base priority is depth
            priority = depth * 10
            
            # Adjust by domain importance if known
            if domain in self.domain_importance:
                priority -= self.domain_importance[domain]
            
            # URLs with fewer query parameters get higher priority
            query_params = len(parsed_url.query.split('&')) if parsed_url.query else 0
            priority += query_params
            
            # URLs with shorter paths get higher priority
            path_segments = len(parsed_url.path.split('/'))
            priority += path_segments // 2
            
            # Adjust by source page importance
            priority -= source_importance
            
            # Clamp to reasonable range
            return max(1, min(100, priority))
        except Exception:
            return 50  # Default middle priority
    
    def compute_content_fingerprint(self, content, title=""):
        """Create a fingerprint of the content to detect duplicates"""
        # Extract meaningful text
        text = re.sub(r'\s+', ' ', content)
        
        # Add title with more weight
        if title:
            text = title + " " + title + " " + text
            
        # Hash the content
        hash_obj = hashlib.md5(text.encode('utf-8'))
        return hash_obj.hexdigest()
    
    def is_duplicate_content(self, fingerprint, url):
        """Check if content is a duplicate"""
        if fingerprint in self.content_fingerprints:
            # It's a duplicate - log the URL it duplicates
            logging.debug(f"Duplicate content detected: {url} matches {self.content_fingerprints[fingerprint]}")
            return True
        
        # Not a duplicate - store the fingerprint
        self.content_fingerprints[fingerprint] = url
        return False
    
    def extract_text_content(self, html, url):
        """Extract meaningful text content from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
        
        # Extract title
        title = url
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        
        # Get main content
        main_content = ""
        
        # Look for main content areas
        main_elements = soup.select("main, article, #content, .content, #main, .main")
        if main_elements:
            for element in main_elements:
                main_content += element.get_text(separator=" ", strip=True) + " "
        else:
            # Fallback to body content
            if soup.body:
                main_content = soup.body.get_text(separator=" ", strip=True)
        
        # Clean up content
        main_content = re.sub(r'\s+', ' ', main_content).strip()
        
        return title, main_content
    
    def extract_metadata(self, html, url):
        """Extract metadata from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        metadata = {
            "url": url,
            "domain": urlparse(url).netloc,
            "crawl_time": datetime.now().isoformat()
        }
        
        # Extract meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name", meta.get("property", ""))
            if name and meta.get("content"):
                metadata[name.lower()] = meta.get("content")
        
        # Extract structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                if script.string:
                    json_data = json.loads(script.string)
                    metadata["structured_data"] = json_data
                    break
            except:
                pass
        
        return metadata
    
    def extract_links(self, html, base_url):
        """Extract and normalize links from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href and not href.startswith(('javascript:', 'mailto:', 'tel:')):
                # Join with base URL and remove fragments
                full_url, _ = urldefrag(urljoin(base_url, href))
                links.append((full_url, a_tag.get_text().strip()))
        
        return links
    
    def crawl(self, start_url, depth=2, resume=False, force_recrawl=False):
        """Start or resume crawling
        
        Args:
            start_url: URL to start crawling from
            depth: Maximum crawl depth
            resume: Whether to resume from a previously saved state
            force_recrawl: Whether to recrawl URLs even if they're in the database
        """
        with self.lock:
            if self.is_crawling:
                logging.warning("Crawler is already running")
                self._broadcast_update({"status": "error", "message": "Crawler is already running"})
                return False
                
            # Store force_recrawl setting
            self.force_recrawl = force_recrawl
            
            if resume and self.load_state():
                logging.info("Resuming previous crawl")
            else:
                # Only reset if not resuming
                if not start_url:
                    logging.error("No start URL provided and not resuming")
                    self._broadcast_update({"status": "error", "message": "No URL provided"})
                    return False
                    
                logging.info(f"Starting new crawl with URL: {start_url}, depth: {depth}, force_recrawl: {force_recrawl}")
                    
                # Reset stats
                self.crawl_stats = {
                    "crawled": 0,
                    "queued": 1,
                    "indexed": 0,
                    "errors": 0,
                    "skipped_duplicates": 0,
                    "start_time": time.time(),
                    "status": "running",
                    "current_url": start_url,
                    "recent_urls": [],
                    "max_depth": depth,
                    "domains_crawled": 0,
                    "content_types": {},
                    "robots_blocked": 0,
                    "force_recrawl": force_recrawl
                }
                
                # Reset state
                self.visited_urls.clear()
                
                # Clear crawler_visits table if force_recrawl is enabled
                if force_recrawl and self.use_db and self.db:
                    logging.info("Force recrawl enabled - clearing previous visit records")
                    self._clear_visit_records()
                
                # Initialize a new queue
                old_queue = self.queue
                self.queue = PriorityQueue()
                
                # Add start URL with highest priority (1)
                logging.info(f"Adding start URL to queue: {start_url}")
                self.queue.put((1, (start_url, 0)))  # (priority, (url, depth))
                logging.info(f"Queue size after adding start URL: {self.queue.qsize()}")
                
                # Verify the queue has the URL
                if self.queue.qsize() == 0:
                    logging.error("Failed to add URL to queue - queue remained empty!")
                    return False
                
                # Update metadata in DB if using it
                if self.use_db and self.db:
                    self.db.update_metadata("last_crawl_time", time.time())
                    self.db.update_metadata("last_crawl_url", start_url)
        
            try:
                # Start crawling in a separate thread
                self.thread_heartbeat = time.time()  # Initialize heartbeat
                self.crawler_thread = threading.Thread(target=self._crawl_thread)
                self.crawler_thread.daemon = True
                self.crawler_thread.start()
                
                # Set state flag after thread started successfully
                self.is_crawling = True
                
                logging.info(f"Crawler thread started with {'resumed state' if resume else start_url}")
                self._broadcast_update({
                    "status": "started", 
                    "url": self.crawl_stats["current_url"], 
                    "depth": self.crawl_stats.get("max_depth", depth)
                })
                return True
            except Exception as e:
                logging.error(f"Failed to start crawler thread: {e}")
                logging.error(traceback.format_exc())
                self.is_crawling = False
                self._broadcast_update({
                    "status": "error",
                    "message": f"Failed to start crawler: {str(e)}"
                })
                return False
    
    def _clear_visit_records(self):
        """Clear crawler visit records for a fresh crawl"""
        if not self.use_db or not self.db:
            return
            
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM crawler_visits')
                conn.commit()
                logging.info("Cleared crawler_visits table for fresh crawl")
        except Exception as e:
            logging.error(f"Error clearing crawler_visits table: {e}")

    def _crawl_thread(self):
        """Main crawling logic"""
        try:
            # Update heartbeat to show thread is running
            self.thread_heartbeat = time.time()
            
            # Track and log thread identity for debugging
            logging.info(f"Crawler thread started: {threading.current_thread().name}")
            logging.info(f"Queue size at start: {self.queue.qsize()}")
            
            if self.queue.qsize() == 0:
                logging.error("Queue is empty! This is unexpected.")
                self._broadcast_update({"status": "error", "message": "Queue was empty at start"})
                self.is_crawling = False  # Reset flag
                return
                
            # Debug: Check queue content
            with self.queue.mutex:
                queue_items = list(self.queue.queue)
                logging.info(f"Queue contents: {queue_items[:5] if queue_items else '(empty)'}")
            
            # Loop through URLs until queue is empty
            urls_processed = 0
            max_urls = 10000  # Safety limit
            last_heartbeat = time.time()
            
            while not self.queue.empty() and urls_processed < max_urls:
                # Update heartbeat periodically (every 10 URLs)
                if urls_processed % 10 == 0:
                    self.thread_heartbeat = time.time()
                
                # Check if we're being asked to stop
                if self.crawl_stats["status"] == "stopping":
                    logging.info("Stopping crawler as requested")
                    break
                
                # Get URL from queue with timeout to prevent blocking forever
                try:
                    priority, (url, depth) = self.queue.get(block=True, timeout=5)
                    urls_processed += 1
                    
                    # Log processing step
                    logging.info(f"Processing URL #{urls_processed}: {url} (depth {depth})")
                    
                    # Skip if already visited in memory
                    if url in self.visited_urls:
                        logging.debug(f"Already visited in memory: {url}")
                        self.queue.task_done()
                        continue
                    
                    # Check database if available (unless force_recrawl is enabled)
                    force_recrawl = getattr(self, 'force_recrawl', False)
                    if not force_recrawl and self.use_db and self.db and self.db.is_url_visited(url):
                        logging.debug(f"URL in database: {url}")
                        self.visited_urls.add(url)
                        self.queue.task_done()
                        continue
                    
                    # Mark URL as current
                    self.crawl_stats["current_url"] = url
                    self._broadcast_update({"status": "crawling", "url": url})
                    
                    # CRITICAL FIX: Force process this URL regardless of any errors
                    logging.info(f"Attempting to fetch URL: {url}")
                    
                    # Check robots.txt
                    try:
                        if not self.is_allowed_by_robots(url):
                            logging.info(f"Blocked by robots.txt: {url}")
                            self.crawl_stats["robots_blocked"] += 1
                            self.visited_urls.add(url)  # Mark as visited even if blocked
                            self.queue.task_done()
                            continue
                    except Exception as e:
                        logging.warning(f"Error checking robots.txt for {url}: {e}")
                        # Continue anyway - non-critical error
                    
                    # Apply rate limiting
                    try:
                        self._apply_rate_limiting(url)
                    except Exception as e:
                        logging.warning(f"Error in rate limiting for {url}: {e}")
                        # Continue anyway - non-critical error
                    
                    # CRITICAL: Directly fetch the page with our own code to bypass errors
                    try:
                        # Add headers to mimic a browser
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8', 
                            'Accept-Language': 'en-US,en;q=0.5'
                        }
                        
                        logging.info(f"Direct fetching URL: {url}")
                        response = requests.get(
                            url, 
                            headers=headers, 
                            timeout=10, 
                            allow_redirects=True, 
                            verify=False
                        )
                        
                        content = response.text
                        status_code = response.status_code
                        headers = dict(response.headers)
                        
                        # Process successful responses
                        if status_code == 200:
                            logging.info(f"Successfully fetched URL: {url} (status: {status_code}, content length: {len(content)})")
                            self.visited_urls.add(url)  # Mark as visited
                            self.crawl_stats["crawled"] += 1
                            
                            # Skip further processing if not HTML
                            content_type = headers.get('Content-Type', '').lower()
                            if not ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                                logging.info(f"Skipping non-HTML content: {content_type}")
                                self.queue.task_done()
                                continue
                                
                            # Process content directly
                            try:
                                title, main_content = self.extract_text_content(content, url)
                                logging.info(f"Extracted title: {title}")
                                
                                # Index the document
                                metadata = self.extract_metadata(content, url)
                                self.search_engine.add_document(url, title, main_content, metadata)
                                self.crawl_stats["indexed"] += 1
                                logging.info(f"Indexed document: {url}")
                                
                                # Extract links if below depth limit
                                if depth < self.crawl_stats.get("max_depth", 2):
                                    links = self.extract_links(content, url)
                                    links_added = self._add_links_to_queue(links, depth)
                                    logging.info(f"Added {links_added} links from {url}")
                            except Exception as e:
                                logging.error(f"Error processing content: {e}")
                                logging.error(traceback.format_exc())
                        else:
                            logging.warning(f"Failed to fetch URL: {url} (status: {status_code})")
                            self.crawl_stats["errors"] += 1
                            # Mark failed URLs as visited to prevent retrying
                            self.visited_urls.add(url)
                            
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Request exception fetching {url}: {e}")
                        self.crawl_stats["errors"] += 1
                        self.visited_urls.add(url)  # Mark as visited to prevent retrying
                    except Exception as e:
                        logging.error(f"Error processing {url}: {e}")
                        logging.error(traceback.format_exc())
                        self.crawl_stats["errors"] += 1
                        self.visited_urls.add(url)  # Mark as visited to prevent retrying
                    
                    # Report progress
                    self._broadcast_update({
                        "status": "progress",
                        "stats": self.crawl_stats,
                        "elapsed": round(time.time() - self.crawl_stats["start_time"], 1)
                    })
                    
                    # Mark queue item as done
                    self.queue.task_done()
                    
                except QueueEmpty:
                    # Queue timeout - log and continue processing
                    logging.info("Queue get timed out, checking if we should continue...")
                    # Check if queue is actually empty now to avoid infinite loops
                    if self.queue.empty():
                        logging.info("Queue is empty, ending crawl loop")
                        break
                    continue
                
                except Exception as e:
                    logging.error(f"Error in crawl loop: {e}")
                    logging.error(traceback.format_exc())
                    self.crawl_stats["errors"] += 1
                    # Mark the queue task as done if appropriate
                    try:
                        self.queue.task_done()
                    except:
                        pass
            
            # Record completion
            if self.crawl_stats["status"] != "stopping":
                if urls_processed >= max_urls:
                    self.crawl_stats["status"] = "terminated"
                    logging.info(f"Reached URL limit of {max_urls}")
                else:
                    self.crawl_stats["status"] = "completed"
                    logging.info("Queue is empty, crawl completed")
            
            # Save final state
            self.save_state("crawler_final_state.gz")
            
            # Update database metadata
            if self.use_db and self.db:
                self.db.update_metadata("last_crawl_completed", time.time())
                self.db.update_metadata("last_crawl_pages", self.crawl_stats["crawled"])
            
            # Send final update
            self._broadcast_update({
                "status": self.crawl_stats["status"],
                "stats": self.crawl_stats,
                "elapsed": round(time.time() - self.crawl_stats["start_time"], 1)
            })
            
        except Exception as e:
            logging.error(f"Crawler thread error: {e}")
            logging.error(traceback.format_exc())
            self.crawl_stats["status"] = "error"
            self._broadcast_update({"status": "error", "message": str(e)})
        
        finally:
            # Always reset crawling flag when thread exits
            self.is_crawling = False
            logging.info(f"Crawl finished: {self.crawl_stats['crawled']} pages, {self.crawl_stats['errors']} errors")

    def _fetch_page(self, url):
        """Fetch a page with caching support"""
        cached_page = None
        if self.use_db and self.db:
            cached_page = self.db.get_cached_page(url)
        
        if cached_page:
            logging.debug(f"Using cached version of {url}")
            content = cached_page['content']
            status_code = cached_page['status_code']
            headers = cached_page['headers']
        else:
            # Add headers to mimic a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Fetch the page
            logging.info(f"Fetching URL: {url}")
            try:
                start_time = time.time()
                response = requests.get(
                    url, 
                    headers=headers, 
                    timeout=15,
                    allow_redirects=True,
                    verify=True  # Set to False only for problematic SSL certificates
                )
                elapsed = time.time() - start_time
                content = response.text
                status_code = response.status_code
                headers = dict(response.headers)
                logging.info(f"Fetched {url} with status {status_code} in {elapsed:.2f}s")
                
                # Get content type and log it
                content_type = headers.get('Content-Type', 'unknown')
                logging.info(f"Content-Type: {content_type}, Content length: {len(content)}")
                
                if content_type not in self.crawl_stats["content_types"]:
                    self.crawl_stats["content_types"][content_type] = 0
                self.crawl_stats["content_types"][content_type] += 1
                
                # Cache the page if it's HTML and using database
                if self.use_db and self.db and status_code == 200:
                    if 'text/html' in content_type.lower():
                        self.db.cache_page(url, content, headers, status_code)
            except requests.exceptions.RequestException as e:
                logging.error(f"Request exception fetching {url}: {e}")
                content = ""
                status_code = 500 if not hasattr(e, 'response') or e.response is None else e.response.status_code 
                headers = {}
                self.crawl_stats["errors"] += 1
        
        # Mark as visited in DB
        domain = urlparse(url).netloc
        if self.use_db and self.db:
            self.db.mark_url_visited(url, 0, success=(status_code == 200))
        
        return content, status_code, headers

    def _process_page(self, url, content, headers, depth):
        """Process a successfully fetched page"""
        # Update domains count if this is a new domain
        domain = urlparse(url).netloc
        domain_key = f"domain:{domain}"
        if domain_key not in self.visited_urls:
            self.visited_urls.add(domain_key)
            self.crawl_stats["domains_crawled"] += 1
        
        # Check content type
        content_type = headers.get('Content-Type', '').lower()
        if not content_type.startswith('text/html'):
            logging.info(f"Skipping non-HTML content: {content_type}")
            return
            
        # Check if content is empty
        if not content or len(content) < 100:
            logging.warning(f"Page content too short or empty: {url} ({len(content)} bytes)")
            return
        
        try:
            # Extract content
            title, main_content = self.extract_text_content(content, url)
            
            # Check for duplicate content
            content_fingerprint = self.compute_content_fingerprint(main_content, title)
            if self.is_duplicate_content(content_fingerprint, url):
                logging.info(f"Skipping duplicate content: {url}")
                self.crawl_stats["skipped_duplicates"] += 1
                return
            
            # Extract metadata and index the page
            metadata = self.extract_metadata(content, url)
            self.search_engine.add_document(url, title, main_content, metadata)
            self.crawl_stats["indexed"] += 1
            
            # Add to recent URLs list
            title_display = title[:50] + "..." if len(str(title)) > 50 else title
            self.crawl_stats["recent_urls"] = ([{
                "url": url, 
                "title": title_display,
                "domain": domain
            }] + self.crawl_stats["recent_urls"])[:5]
            
            # Process links if below depth limit
            if depth < self.crawl_stats.get("max_depth", 2):
                links = self.extract_links(content, url)
                links_added = self._add_links_to_queue(links, current_depth=depth)
                logging.info(f"Added {links_added} links from {url}")
            else:
                logging.info(f"Max depth reached ({depth}), not extracting links from {url}")
        
        except Exception as e:
            logging.error(f"Error processing content from {url}: {e}")
            logging.error(traceback.format_exc())
            self.crawl_stats["errors"] += 1

    def _add_links_to_queue(self, links, current_depth):
        """Add extracted links to the queue with filtering"""
        links_added = 0
        next_depth = current_depth + 1
        
        # Use a conservative limit on links per page
        max_links = min(100, len(links))
        
        for link_url, link_text in links[:max_links]:
            try:
                # Skip already visited URLs
                if link_url in self.visited_urls:
                    continue
                
                # Skip URLs already in DB
                force_recrawl = getattr(self, 'force_recrawl', False)
                if not force_recrawl and self.use_db and self.db and self.db.is_url_visited(link_url):
                    continue
                
                # Skip non-HTTP(S) URLs
                if not link_url.startswith(('http://', 'https://')):
                    continue
                
                # Skip URLs with known problematic file extensions
                parsed_url = urlparse(link_url)
                path = parsed_url.path.lower()
                if path.endswith(('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.exe', '.doc', '.docx')):
                    continue
                
                # Compute priority for this URL
                priority = self.compute_url_priority(link_url, next_depth)
                
                # Log queue action
                logging.debug(f"Adding to queue: {link_url} (depth {next_depth}, priority {priority})")
                
                # Add to queue
                self.queue.put((priority, (link_url, next_depth)))
                links_added += 1
                self.crawl_stats["queued"] += 1
            except Exception as e:
                logging.error(f"Error adding link to queue: {link_url} - {e}")
                
        return links_added

    def _apply_rate_limiting(self, url):
        """Apply rate limiting for a domain to avoid overwhelming servers"""
        domain = urlparse(url).netloc
        
        # Apply delay if needed
        if domain in self.domain_access_times:
            last_access_time = self.domain_access_times.get(domain, 0)
            time_since_last = time.time() - last_access_time
            min_delay = self.min_crawl_delay
            if time_since_last < min_delay:
                delay = min_delay - time_since_last
                logging.debug(f"Rate limiting: Waiting {delay:.2f}s for {domain}")
                time.sleep(delay)
        
        # Update last access time
        self.domain_access_times[domain] = time.time()

    def stop_crawl(self):
        """Stop the crawler and save state for later resuming"""
        with self.lock:
            if not self.is_crawling and not self.crawler_thread:
                return False
            
            # Check if the thread is actually running
            if self.crawler_thread and not self.crawler_thread.is_alive():
                logging.warning("Crawler thread not alive, force resetting state")
                self.is_crawling = False
                self._broadcast_update({"status": "reset", "message": "Crawler state reset"})
                return True
            
            # Set a flag to request stopping
            self.crawl_stats["status"] = "stopping"
            self._broadcast_update({"status": "stopping", "message": "Stopping crawler..."})
            
            # Save state for resuming later
            self.save_state()
            
            # Set a timer to force stop if thread doesn't exit
            def force_stop():
                if self.is_crawling:
                    logging.warning("Forcing crawler to stop after timeout")
                    self.is_crawling = False
                    self._broadcast_update({
                        "status": "force_stopped", 
                        "message": "Crawler was force stopped after timeout"
                    })
            
            # Wait up to 30 seconds, then force stop
            tornado.ioloop.IOLoop.current().call_later(30, force_stop)
            
            return True
            
    def force_stop(self):
        """Force stop the crawler immediately, regardless of state"""
        with self.lock:
            old_status = self.is_crawling
            self.is_crawling = False
            self.crawl_stats["status"] = "force_stopped"
            self._broadcast_update({
                "status": "force_stopped", 
                "message": "Crawler was force stopped"
            })
            return old_status  # Return previous state

    def _broadcast_update(self, message):
        """Send updates to all connected WebSocket clients"""
        if not self.websocket_clients:
            return
        
        try:
            # Add timestamp to each message for debugging
            message["timestamp"] = time.time()
            json_message = json.dumps(message)
            
            # Don't log ping/pong messages to avoid spam
            if message.get('status') not in ['ping', 'pong'] and message.get('type') not in ['ping', 'pong']:
                logging.info(f"Broadcasting update to {len(self.websocket_clients)} clients: {message.get('status')}")
            
            # Use the main event loop to send WebSocket messages
            ioloop = tornado.ioloop.IOLoop.current()
            
            def send_to_clients():
                # Create a copy of the clients list
                clients_to_notify = []
                with self.lock:
                    clients_to_notify = list(self.websocket_clients)
                
                for client in clients_to_notify:
                    try:
                        client_id = id(client)
                        # Check if connection is open
                        if not client.ws_connection or not client.ws_connection.stream or not client.ws_connection.stream.socket:
                            logging.warning(f"Client connection {client_id} appears closed, removing")
                            self.unregister_client(client)
                            continue
                        
                        # Send the message
                        client.write_message(json_message)
                    except Exception as e:
                        if 'closed' in str(e).lower() or 'not open' in str(e).lower():
                            logging.debug(f"WebSocket closed for client {id(client)}")
                        else:
                            logging.error(f"Error sending message to WebSocket client {id(client)}: {e}")
                        # Client might be disconnected, remove it
                        self.unregister_client(client)
            
            # Schedule the sending in the main thread's event loop
            ioloop.add_callback(send_to_clients)
        
        except Exception as e:
            logging.error(f"Error in _broadcast_update: {e}")
            logging.error(traceback.format_exc())
    
    def get_stats(self):
        """Return current crawling statistics"""
        with self.lock:
            stats_copy = self.crawl_stats.copy()
            
            if stats_copy["status"] == "running" or stats_copy["status"] == "stopping":
                stats_copy["elapsed"] = round(time.time() - stats_copy["start_time"], 1)
            
            # Add queue size information
            stats_copy["queue_size"] = self.queue.qsize()
            
            # Add index stats
            if self.use_db and self.db:
                stats_copy["index_stats"] = self.search_engine.get_stats()
            else:
                stats_copy["index_stats"] = {
                    "documents": len(self.search_engine.documents),
                    "keywords": len(self.search_engine.index),
                    "size": "unknown"
                }
            
            return stats_copy
    
    def register_client(self, client):
        """Register a WebSocket client for updates"""
        with self.lock:
            if client not in self.websocket_clients:
                client_id = id(client)
                logging.info(f"Registering new WebSocket client: {client_id}")
                self.websocket_clients.append(client)
                
                # Create a function for safe message sending
                def safe_send_message(msg_data):
                    try:
                        if client not in self.websocket_clients:
                            return False
                        if not client.ws_connection or not client.ws_connection.stream:
                            self.unregister_client(client)
                            return False
                        client.write_message(json.dumps(msg_data))
                        return True
                    except Exception as e:
                        logging.error(f"Error sending message to client {client_id}: {e}")
                        self.unregister_client(client)
                        return False
                
                # Send initial data in a scheduled callback
                def send_initial_data():
                    stats = self.get_stats()
                    initial_data = {
                        "status": "connected",
                        "stats": stats,
                        "message": "Connection established"
                    }
                    if safe_send_message(initial_data):
                        # Send a ping after a short delay
                        tornado.ioloop.IOLoop.current().call_later(
                            1.0,
                            lambda: safe_send_message({
                                "status": "ping",
                                "timestamp": time.time()
                            })
                        )
                
                # Schedule the initial data
                tornado.ioloop.IOLoop.current().add_callback(send_initial_data)
    
    def unregister_client(self, client):
        """Unregister a WebSocket client"""
        with self.lock:
            if client in self.websocket_clients:
                logging.info(f"Unregistering WebSocket client: {id(client)}")
                self.websocket_clients.remove(client)
    
    def generate_site_map(self, domain=None):
        """Generate a site map of crawled pages"""
        domain_pages = defaultdict(list)
        
        # Organize pages by domain
        for url in self.visited_urls:
            if url.startswith("http"):
                try:
                    parsed = urlparse(url)
                    page_domain = parsed.netloc
                    # Filter by domain if specified
                    if domain and domain != page_domain:
                        continue
                    domain_pages[page_domain].append(url)
                except:
                    pass
        
        return dict(domain_pages)
    
    def generate_test_update(self):
        """Generate a test update to verify WebSocket communication"""
        test_message = {
            "status": "test",
            "message": "This is a test message from SmartCrawler",
            "time": time.time(),
            "crawler_type": "SmartCrawler"
        }
        
        logging.info("Sending test WebSocket message")
        self._broadcast_update(test_message)        
        return True
