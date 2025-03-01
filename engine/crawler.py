import threading
import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from queue import Queue
import time
import json
import tornado.ioloop
import traceback

class Crawler:
    
    def __init__(self, search_engine, websocket_clients=None):
        self.search_engine = search_engine
        self.websocket_clients = websocket_clients if websocket_clients is not None else []
        self.visited_urls = set()
        self.queue = Queue()
        self.is_crawling = False
        self.crawl_stats = {
            "crawled": 0,
            "queued": 0,
            "indexed": 0,
            "errors": 0,
            "start_time": 0,
            "status": "idle",
            "current_url": "",
            "recent_urls": []  # Keep track of recently crawled URLs
        }
        self.lock = threading.Lock()  # Add a lock for thread safety
        
        # Check if using database-backed search engine
        self.use_db = getattr(self.search_engine, 'use_db', False)
        self.db = getattr(self.search_engine, 'db', None) if self.use_db else None

    def crawl(self, start_url, depth=2):
        if self.is_crawling:
            logging.warning("Crawler is already running")
            self._broadcast_update({"status": "error", "message": "Crawler is already running"})
            return False
        
        # Reset stats
        self.crawl_stats = {
            "crawled": 0,
            "queued": 1,  # Start with one URL
            "indexed": 0,
            "errors": 0,
            "start_time": time.time(),
            "status": "running",
            "current_url": start_url,
            "recent_urls": [],
            "max_depth": depth
        }
        
        # Reset the queue and visited set for in-memory tracking
        self.queue = Queue()
        self.visited_urls = set()
        
        # Add the start URL to the queue
        self.queue.put((start_url, 0))  # (url, depth)
        
        # Update metadata in DB if using it
        if self.use_db and self.db:
            self.db.update_metadata("last_crawl_time", time.time())
            self.db.update_metadata("last_crawl_url", start_url)
        
        # Start crawling in a separate thread
        crawler_thread = threading.Thread(target=self._crawl_thread, args=(depth,))
        crawler_thread.daemon = True
        crawler_thread.start()
        
        self._broadcast_update({"status": "started", "url": start_url, "depth": depth})
        return True

    def _crawl_thread(self, max_depth):
        self.is_crawling = True
        
        try:
            while not self.queue.empty():
                # Get the next URL from the queue
                url, depth = self.queue.get()
                
                # Skip if URL has already been visited - check both in-memory and DB if available
                already_visited = url in self.visited_urls
                
                if self.use_db and self.db:
                    already_visited = already_visited or self.db.is_url_visited(url)
                
                if already_visited:
                    self.queue.task_done()
                    continue
                
                # Update the current URL in the stats
                self.crawl_stats["current_url"] = url
                self._broadcast_update({"status": "crawling", "url": url, "depth": depth})
                
                try:
                    # Check cache first if using DB
                    cached_page = None
                    if self.use_db and self.db:
                        cached_page = self.db.get_cached_page(url)
                    
                    if cached_page:
                        # Use cached page data
                        logging.info(f"Using cached version of {url}")
                        content = cached_page['content']
                        status_code = cached_page['status_code']
                        headers = cached_page['headers']
                    else:
                        # Fetch fresh page
                        response = requests.get(url, timeout=5)
                        content = response.text
                        status_code = response.status_code
                        headers = dict(response.headers)
                        
                        # Cache the page if using DB
                        if self.use_db and self.db and status_code == 200:
                            self.db.cache_page(url, content, headers, status_code)
                    
                    # Mark as visited in both in-memory and DB
                    self.visited_urls.add(url)
                    if self.use_db and self.db:
                        self.db.mark_url_visited(url, depth, success=(status_code == 200))
                    
                    if status_code == 200:
                        self.crawl_stats["crawled"] += 1
                        
                        # Parse the content
                        soup = BeautifulSoup(content, "html.parser")
                        
                        # Safely get title - fix for NoneType error
                        title = url  # Default to URL if no title
                        if soup.title and soup.title.string:
                            title = soup.title.string
                        
                        # Safely get content
                        page_content = ""
                        if soup.body:
                            page_content = soup.get_text(separator=" ", strip=True)
                        
                        # Extract domain for metadata
                        domain = urlparse(url).netloc
                        
                        # Add the page to the search index
                        self.search_engine.add_document(url, title, page_content)
                        self.crawl_stats["indexed"] += 1
                        
                        # Keep track of recently crawled URLs (limit to 5)
                        title_display = title[:50] + "..." if len(str(title)) > 50 else title
                        self.crawl_stats["recent_urls"] = ([{
                            "url": url, 
                            "title": title_display,
                            "domain": domain
                        }] + self.crawl_stats["recent_urls"])[:5]
                        
                        # If we haven't reached the maximum depth, add all links to the queue
                        if depth < max_depth:
                            for link in soup.find_all("a", href=True):
                                next_url = urljoin(url, link["href"])
                                
                                # Skip external links, anchors, or non-HTTP(S) links
                                parsed_next_url = urlparse(next_url)
                                if (parsed_next_url.netloc == urlparse(url).netloc and 
                                    parsed_next_url.scheme in ["http", "https"] and 
                                    next_url not in self.visited_urls):
                                    
                                    # Also check DB for already visited URLs
                                    if self.use_db and self.db and self.db.is_url_visited(next_url):
                                        continue
                                        
                                    self.queue.put((next_url, depth + 1))
                                    self.crawl_stats["queued"] += 1
                    else:
                        self.crawl_stats["errors"] += 1
                
                except Exception as e:
                    logging.error(f"Error crawling {url}: {e}")
                    self.crawl_stats["errors"] += 1
                    
                    # Mark failed URL in DB
                    if self.use_db and self.db:
                        self.db.mark_url_visited(url, depth, success=False)
                
                # Broadcast an update after processing each URL
                self._broadcast_update({
                    "status": "progress", 
                    "stats": self.crawl_stats,
                    "elapsed": round(time.time() - self.crawl_stats["start_time"], 1)
                })
                
                # Small delay to not overload servers
                time.sleep(0.5)
                    
                self.queue.task_done()
            
            # Crawling completed
            self.crawl_stats["status"] = "completed"
            
            # Update final stats in DB
            if self.use_db and self.db:
                self.db.update_metadata("last_crawl_completed", time.time())
                self.db.update_metadata("last_crawl_pages", self.crawl_stats["crawled"])
            
            self._broadcast_update({
                "status": "completed", 
                "stats": self.crawl_stats,
                "elapsed": round(time.time() - self.crawl_stats["start_time"], 1)
            })
        
        except Exception as e:
            logging.error(f"Crawler thread error: {e}")
            self.crawl_stats["status"] = "error"
            self._broadcast_update({"status": "error", "message": str(e)})
        
        finally:
            self.is_crawling = False
    
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
            # This fixes the "no current event loop" error
            ioloop = tornado.ioloop.IOLoop.current()
            
            def send_to_clients():
                # Create a copy outside the lock to minimize lock contention
                clients_to_notify = []
                with self.lock:
                    clients_to_notify = list(self.websocket_clients)  # Make a copy
                
                # Skip logging for frequent events to avoid log spam
                if message.get('status') not in ['ping', 'pong'] and message.get('type') not in ['ping', 'pong']:
                    logging.info(f"Sending message to {len(clients_to_notify)} clients")
                
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
                        
                        # Skip detailed logging for ping/pong messages
                        if message.get('status') not in ['ping', 'pong'] and message.get('type') not in ['ping', 'pong']:
                            logging.debug(f"Message sent to client: {client_id}")
                            
                    except tornado.websocket.WebSocketClosedError:
                        logging.warning(f"WebSocket already closed for client {id(client)}")
                        self.unregister_client(client)
                    except Exception as e:
                        if 'Connection already closed' in str(e) or 'not open' in str(e).lower():
                            logging.warning(f"Connection already closed when sending to client {id(client)}")
                        else:
                            logging.error(f"Error sending message to WebSocket client {id(client)}: {e}")
                            logging.debug(traceback.format_exc())
                        
                        # Client might be disconnected, remove it
                        self.unregister_client(client)
            
            # Schedule the sending in the main thread's event loop
            ioloop.add_callback(send_to_clients)
            
        except Exception as e:
            logging.error(f"Error in _broadcast_update: {e}")
            logging.error(traceback.format_exc())

    def generate_test_update(self):
        """Generate a test update to verify WebSocket communication"""
        self._broadcast_update({
            "status": "test",
            "message": "This is a test message",
            "time": time.time()
        })
        return True

    def get_stats(self):
        """Return current crawling statistics"""
        with self.lock:  # Thread-safe access to crawl_stats
            stats_copy = self.crawl_stats.copy()
            if stats_copy["status"] == "running":
                stats_copy["elapsed"] = round(time.time() - stats_copy["start_time"], 1)
            
            # Add index stats
            stats_copy["index_stats"] = self._get_index_stats()
            
            return stats_copy

    def _get_index_stats(self):
        """Get statistics about the search index"""
        # Use DB stats if available
        if self.use_db and self.db:
            try:
                return self.search_engine.get_stats()
            except Exception as e:
                logging.error(f"Error getting DB stats: {e}")
                # Fall back to basic stats
                
        # Basic stats calculation
        try:
            document_count = len(self.search_engine.documents)
            keyword_count = len(self.search_engine.index)
            
            # Calculate an estimated index size
            import sys
            index_size_bytes = sys.getsizeof(self.search_engine.index) + sys.getsizeof(self.search_engine.documents)
            
            # Format size for display
            if index_size_bytes < 1024:
                size_str = f"{index_size_bytes} bytes"
            elif index_size_bytes < 1024 * 1024:
                size_str = f"{index_size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{index_size_bytes / (1024 * 1024):.1f} MB"
            
            return {
                "documents": document_count,
                "keywords": keyword_count,
                "size": size_str
            }
        except Exception as e:
            logging.error(f"Error calculating index stats: {e}")
            return {
                "documents": 0,
                "keywords": 0,
                "size": "0 KB"
            }

    def register_client(self, client):
        """Register a WebSocket client for updates"""
        with self.lock:  # Thread-safe modification of clients list
            if client not in self.websocket_clients:
                client_id = id(client)
                logging.info(f"Registering new WebSocket client: {client_id}")
                self.websocket_clients.append(client)
                
                # Create a separate callback to send initial data
                # This avoids any potential deadlock with the lock
                def send_initial_data():
                    try:
                        stats = self.get_stats()
                        logging.info(f"Sending initial stats to client {client_id}: {stats['status']}")
                        
                        initial_data = {
                            "status": "connected",
                            "stats": stats,
                            "message": "Connection established"
                        }
                        
                        # Create safe message sending function
                        def safe_send_message(msg_data, msg_type="data"):
                            try:
                                # Check if client is still in our list (not unregistered)
                                if client not in self.websocket_clients:
                                    logging.info(f"Client {client_id} already unregistered, not sending {msg_type}")
                                    return False

                                # Check if client connection is still open
                                if not client.ws_connection or not client.ws_connection.stream or not client.ws_connection.stream.socket:
                                    logging.warning(f"Client connection {client_id} appears closed when sending {msg_type}")
                                    self.unregister_client(client)
                                    return False
                                    
                                # Send the message
                                client.write_message(json.dumps(msg_data))
                                logging.debug(f"{msg_type} sent to client {client_id}")
                                return True
                            except tornado.websocket.WebSocketClosedError:
                                logging.warning(f"WebSocket {client_id} closed when sending {msg_type}")
                                self.unregister_client(client)
                                return False
                            except Exception as e:
                                logging.error(f"Error sending {msg_type} to {client_id}: {e}")
                                logging.error(traceback.format_exc())
                                return False
                        
                        # First immediate message
                        if safe_send_message(initial_data, "initial data"):
                            # Send a ping message after a delay, only if first message succeeded
                            ioloop = tornado.ioloop.IOLoop.current()
                            ioloop.call_later(1.0, lambda: safe_send_message({
                                "status": "ping", 
                                "timestamp": time.time()
                            }, "ping"))
                            
                    except Exception as e:
                        logging.error(f"Error preparing initial data for {client_id}: {e}")
                        logging.error(traceback.format_exc())
                
                # Schedule the initial data send on the next event loop cycle
                tornado.ioloop.IOLoop.current().add_callback(send_initial_data)
    
    def unregister_client(self, client):
        """Unregister a WebSocket client"""
        with self.lock:  # Thread-safe modification of clients list
            if client in self.websocket_clients:
                logging.info(f"Unregistering WebSocket client: {id(client)}")
                self.websocket_clients.remove(client)
