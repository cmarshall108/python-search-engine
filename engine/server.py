import os
import json
import tornado.web
import tornado.ioloop
import tornado.websocket
from tornado.options import define, options
import logging
import time
import traceback
import math  # Import math for ceil function

# Add new imports
from .enhanced_search_engine import EnhancedSearchEngine
from .api_handlers import (
    WebSearchAPIHandler, 
    ImageSearchAPIHandler, 
    NewsSearchAPIHandler,
    VideoSearchAPIHandler,
    SuggestionsAPIHandler,
    QuickAnswerAPIHandler,
    RelatedSearchesAPIHandler
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from .db import SearchDatabase, OptimizedSearchDatabase
from .search import SearchEngine
from .crawler import Crawler
from .advanced_crawler import SmartCrawler

# Define command line parameters
define("port", default=8888, help="Run on the given port", type=int)
define("debug", default=True, help="Run in debug mode", type=bool)

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class SearchHandler(tornado.web.RequestHandler):
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        time_period = self.get_argument("time", None)
        search_type = self.get_argument("type", "web")
        
        if time_period and time_period.isdigit():
            time_period = int(time_period)
        
        results = []
        total_results = 0
        quick_answer = None
        related_searches = []
        
        if query:
            # Determine if we need quick answers
            if search_type == "web" and page == 1:
                try:
                    # Use the static method directly instead of creating an instance
                    from api_handlers import QuickAnswerAPIHandler
                    quick_answer = QuickAnswerAPIHandler._generate_answer(query, None)
                    logging.info(f"Quick answer generated: {quick_answer is not None}")
                except Exception as e:
                    logging.error(f"Error getting quick answer: {e}")
                    logging.error(traceback.format_exc())
            
            # Get related searches for web searches
            if search_type == "web" and page == 1:
                try:
                    # Use the static method directly instead of creating an instance
                    from api_handlers import RelatedSearchesAPIHandler
                    related_searches = RelatedSearchesAPIHandler._generate_related_searches(query, None)
                    logging.info(f"Related searches generated: {len(related_searches)}")
                except Exception as e:
                    logging.error(f"Error getting related searches: {e}")
                    logging.error(traceback.format_exc())
            
            # Get search results based on type
            content_type = search_type if search_type != "web" else None
            results, total_results = self.application.search_engine.search(
                query, 
                page=page, 
                results_per_page=10,
                time_period=time_period,
                content_type=content_type
            )
        
        self.render(
            "results.html", 
            query=query, 
            results=results, 
            total_results=total_results,
            current_page=page,
            pages=range(1, min(10, (total_results // 10) + 2)),
            quick_answer=quick_answer,
            related_searches=related_searches
        )

class AdminHandler(tornado.web.RequestHandler):
    """Handler for the admin page"""
    def get(self):
        # Get current crawler status
        crawler_stats = self.application.crawler.get_stats()
        self.render("admin.html", crawler_stats=crawler_stats)

class CrawlerHandler(tornado.web.RequestHandler):
    def post(self):
        url = self.get_argument("url", "")
        depth = int(self.get_argument("depth", 2))
        force = self.get_argument("force", "false").lower() == "true"
        
        if not url:
            self.write({"status": "error", "message": "URL is required"})
            return
        
        logging.info(f"Starting crawler with URL: {url}, depth: {depth}, force: {force}")
        
        # Start crawling in a non-blocking way
        try:
            success = self.application.crawler.crawl(url, depth, force_recrawl=force)
            if success:
                self.write({"status": "success", "message": f"Started crawling {url} with depth {depth}"})
            else:
                self.write({"status": "error", "message": "Crawler is already running or couldn't start"})
        except Exception as e:
            logging.error(f"Error starting crawler: {e}")
            logging.error(traceback.format_exc())
            self.write({"status": "error", "message": f"Error starting crawler: {str(e)}"})

class CrawlerStatusHandler(tornado.web.RequestHandler):
    def get(self):
        """Get the current crawler status"""
        stats = self.application.crawler.get_stats()
        self.write(stats)

class CrawlerTestHandler(tornado.web.RequestHandler):
    """Send a test message through WebSockets for debugging"""
    def post(self):
        result = self.application.crawler.generate_test_update()
        self.write({"status": "success", "message": "Test message sent"})

class CrawlerWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        # Allow connections from any origin
        return True
        
    def open(self):
        """Client connected to the WebSocket"""
        client_id = id(self)
        logging.info(f"WebSocket client {client_id} connected from {self.request.remote_ip}")
        self.set_nodelay(True)  # Disable Nagle algorithm for lower latency
        
        # Send an immediate acknowledgment
        try:
            self.write_message(json.dumps({
                "status": "welcome",
                "message": "WebSocket connection established",
                "clientId": client_id,
                "timestamp": time.time()
            }))
            logging.info(f"Welcome message sent to client {client_id}")
        except Exception as e:
            logging.error(f"Error sending welcome message: {e}")
            
        # Register with the crawler
        self.application.crawler.register_client(self)
    
    def on_message(self, message):
        """Handle messages from clients"""
        try:
            data = json.loads(message)
            message_type = data.get('type', 'unknown')
            
            # Only log non-ping messages to avoid spam
            if message_type != 'ping':
                logging.info(f"Received message from client {id(self)}: {message_type}")
                
            if message_type == 'ping':
                # Respond to ping with pong
                self.write_message(json.dumps({
                    "type": "pong",
                    "timestamp": time.time(),
                    "received": data.get('timestamp', 0)
                }))
            elif message_type == 'test':
                # Allow manual test from client
                self.application.crawler.generate_test_update()
        except Exception as e:
            logging.error(f"Error handling WebSocket message: {e}")
            logging.error(traceback.format_exc())
    
    def on_close(self):
        """Client disconnected from the WebSocket"""
        client_id = id(self)
        code = self.close_code if hasattr(self, 'close_code') else None
        reason = self.close_reason if hasattr(self, 'close_reason') else None
        logging.info(f"WebSocket client {client_id} disconnected. Code: {code}, Reason: {reason}")
        self.application.crawler.unregister_client(self)

class SaveIndexHandler(tornado.web.RequestHandler):
    def post(self):
        self.application.search_engine.save_index("search_index.json")
        self.write({"status": "success", "message": "Index saved successfully"})

class LoadIndexHandler(tornado.web.RequestHandler):
    def post(self):
        self.application.search_engine.load_index("search_index.json")
        self.write({"status": "success", "message": "Index loaded successfully"})

class ClearIndexHandler(tornado.web.RequestHandler):
    """Clear the search index"""
    def post(self):
        self.application.search_engine.clear_index()
        self.write({"status": "success", "message": "Search index cleared successfully"})

class CrawlerResumeHandler(tornado.web.RequestHandler):
    """Resume a previously stopped crawl"""
    def post(self):
        depth = int(self.get_argument("depth", 2))
        
        # Check if we have a smart crawler instance
        if hasattr(self.application.crawler, 'load_state'):
            success = self.application.crawler.crawl(None, depth, resume=True)
            if success:
                self.write({"status": "success", "message": "Resumed crawling from previous state"})
            else:
                self.write({"status": "error", "message": "Could not resume crawling. No saved state found or crawler already running."})
        else:
            self.write({"status": "error", "message": "This crawler doesn't support resuming"})

class CrawlerStopHandler(tornado.web.RequestHandler):
    """Stop the current crawl but save state for resuming"""
    def post(self):
        # Check if we have a smart crawler instance
        if hasattr(self.application.crawler, 'stop_crawl'):
            success = self.application.crawler.stop_crawl()
            if success:
                self.write({"status": "success", "message": "Crawler stopped and state saved"})
            else:
                self.write({"status": "error", "message": "Crawler is not running"})
        else:
            self.write({"status": "error", "message": "This crawler doesn't support controlled stopping"})

class SitemapHandler(tornado.web.RequestHandler):
    """Generate a sitemap of crawled URLs for a domain"""
    def get(self):
        domain = self.get_argument("domain", None)
        
        # Check if we have a smart crawler instance
        if hasattr(self.application.crawler, 'generate_site_map'):
            sitemap = self.application.crawler.generate_site_map(domain)
            self.write({"status": "success", "sitemap": sitemap})
        else:
            self.write({"status": "error", "message": "This crawler doesn't support sitemap generation"})

class ClearCacheHandler(tornado.web.RequestHandler):
    """Clear cache entries"""
    def post(self):
        all_cache = self.get_argument("all", "false").lower() == "true"
        
        # Get the database
        db = getattr(self.application.search_engine, 'db', None)
        
        if db:
            if all_cache:
                db.clear_cache()
                self.write({"status": "success", "message": "All cache entries cleared"})
            else:
                expired_count = db.clear_expired_cache()
                self.write({"status": "success", "message": f"{expired_count} expired cache entries cleared"})
        else:
            self.write({"status": "error", "message": "Cannot access database"})

class Application(tornado.web.Application):
    def __init__(self):
        # Initialize search engine with optimized database
        self.search_engine = EnhancedSearchEngine(db_path="search_engine.db", use_optimized=True)
        
        # Use the advanced crawler implementation
        try:
            logging.info("Initializing SmartCrawler...")
            self.crawler = SmartCrawler(self.search_engine, [])
        except Exception as e:
            logging.error(f"Error initializing SmartCrawler: {e}")
            logging.error(traceback.format_exc())
            logging.warning("Falling back to basic Crawler")
            self.crawler = Crawler(self.search_engine, [])
        
        handlers = [
            # Existing handlers
            (r"/", MainHandler),
            (r"/search", SearchHandler),
            (r"/admin", AdminHandler),
            
            # Enhanced UI routes
            (r"/enhanced", EnhancedMainHandler),
            (r"/enhanced/search", EnhancedSearchHandler),
            
            # Existing API routes
            (r"/api/crawl", CrawlerHandler),
            (r"/api/crawler/status", CrawlerStatusHandler),
            (r"/api/save_index", SaveIndexHandler),
            (r"/api/load_index", LoadIndexHandler),
            (r"/api/clear_index", ClearIndexHandler),
            (r"/api/crawler/test", CrawlerTestHandler),
            (r"/ws/crawler", CrawlerWebSocketHandler),
            (r"/api/crawler/resume", CrawlerResumeHandler),
            (r"/api/crawler/stop", CrawlerStopHandler),
            (r"/api/crawler/sitemap", SitemapHandler),
            (r"/api/cache/clear", ClearCacheHandler),
            
            # New API handlers
            (r"/api/search/web", WebSearchAPIHandler),
            (r"/api/search/images", ImageSearchAPIHandler),
            (r"/api/search/news", NewsSearchAPIHandler),
            (r"/api/search/videos", VideoSearchAPIHandler),
            (r"/api/search/suggestions", SuggestionsAPIHandler),
            (r"/api/search/quickanswer", QuickAnswerAPIHandler),
            (r"/api/search/related", RelatedSearchesAPIHandler),
        ]
        
        settings = {
            "template_path": os.path.join(os.path.dirname(__file__), "templates"),
            "static_path": os.path.join(os.path.dirname(__file__), "static"),
            "debug": options.debug,
            "websocket_ping_interval": 30,    # Send WebSocket ping every 30 seconds
            "websocket_ping_timeout": 60,     # Wait up to 60 seconds for pong response before closing
            "websocket_max_message_size": 10 * 1024 * 1024,  # 10 MB max message size
        }
        
        super(Application, self).__init__(handlers, **settings)

# Add these new handlers for the enhanced UI
class EnhancedMainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("enhanced_index.html")

class EnhancedSearchHandler(tornado.web.RequestHandler):
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        time_period = self.get_argument("time", None)
        search_type = self.get_argument("type", "web")
        
        # Default values
        results = []
        total_results = 0
        total_pages = 0
        quick_answer = None
        related_searches = []
        elapsed_time = 0
        
        if query:
            start_time = time.time()
            
            # Get search type specific data
            if search_type == "web":
                # Try to get quick answers for web searches on first page
                if page == 1:
                    try:
                        # Import here to avoid import errors
                        from api_handlers import QuickAnswerAPIHandler
                        
                        # Directly call the static method with query string as parameter
                        quick_answer = QuickAnswerAPIHandler._generate_answer(query, None)
                    except Exception as e:
                        logging.error(f"Error fetching quick answer: {e}")
                        logging.error(traceback.format_exc())
                
                # Get search results with detailed debug logging
                try:
                    logging.info(f"Searching for '{query}' with page={page}, time_period={time_period}")
                    results, total_results = self.application.search_engine.search(
                        query, page=page, results_per_page=10, time_period=time_period
                    )
                    
                    # Detailed logging about results
                    logging.info(f"Search results: found {total_results} total, {len(results)} on current page")
                    if results and len(results) > 0:
                        logging.info(f"First result: {results[0].get('title', 'Unknown')} - {results[0].get('url', 'No URL')}")
                    else:
                        logging.info(f"No results found for query: {query}")
                        # Try a simpler search if regular search gave no results
                        if query and len(query) > 3:
                            logging.info(f"Trying a simpler search with first word of query")
                            simple_query = query.split()[0]
                            results, total_results = self.application.search_engine.search(
                                simple_query, page=page, results_per_page=10
                            )
                            logging.info(f"Simple search results: {len(results)} results")
                except Exception as e:
                    logging.error(f"Error performing search: {e}")
                    logging.error(traceback.format_exc())
                
                # Try to get related searches
                try:
                    # Import here to avoid import errors
                    from api_handlers import RelatedSearchesAPIHandler
                    
                    # Directly call the static method with query string as parameter
                    related_searches = RelatedSearchesAPIHandler._generate_related_searches(query, None)
                except Exception as e:
                    logging.error(f"Error generating related searches: {e}")
                    logging.error(traceback.format_exc())
                    
            elif search_type == "images":
                # For image search, use the image search API
                try:
                    from api_handlers import ImageSearchAPIHandler
                    handler = ImageSearchAPIHandler(self.application)
                    handler.get_argument = lambda x, default: query if x == "q" else page if x == "page" else default
                    results = handler._generate_image_results(query, page)
                    total_results = 120  # Mock total for demo
                except Exception as e:
                    logging.error(f"Error generating image results: {e}")
                logging.info(f"Image search found {len(results)} results")
            
            elif search_type == "news":
                # For news search, use the news API
                try:
                    from api_handlers import NewsSearchAPIHandler
                    handler = NewsSearchAPIHandler(self.application)
                    handler.get_argument = lambda x, default: query if x == "q" else page if x == "page" else default
                    results = handler._generate_news_results(query, page)
                    total_results = 50  # Mock total for demo
                except Exception as e:
                    logging.error(f"Error generating news results: {e}")
                logging.info(f"News search found {len(results)} results")
            
            elif search_type == "videos":
                # For video search, use the video API
                try:
                    from api_handlers import VideoSearchAPIHandler
                    handler = VideoSearchAPIHandler(self.application)
                    handler.get_argument = lambda x, default: query if x == "q" else page if x == "page" else default
                    results = handler._generate_video_results(query, page)
                    total_results = 75  # Mock total for demo
                except Exception as e:
                    logging.error(f"Error generating video results: {e}")
                logging.info(f"Video search found {len(results)} results")
            
            # Calculate elapsed time
            elapsed_time = round(time.time() - start_time, 3)
            
            # Calculate total pages
            total_pages = math.ceil(total_results / 10) if total_results > 0 else 0
        
        # Log what we're rendering with complete details
        logging.info(f"Rendering enhanced results for '{query}'")
        logging.info(f"  - Type: {search_type}")
        logging.info(f"  - Total results: {total_results}")
        logging.info(f"  - Results on page: {len(results)}")
        logging.info(f"  - Current page: {page} of {total_pages}")
        
        # Double check that results is a list, not None
        if results is None:
            logging.warning("Results is None, fixing to empty list")
            results = []
        
        # Render the template with all search data
        try:
            self.render(
                "enhanced_results.html", 
                query=query,
                search_type=search_type,
                results=results,
                total_results=total_results,
                current_page=page,
                total_pages=total_pages,
                time_period=time_period,
                quick_answer=quick_answer,
                related_searches=related_searches,
                elapsed_time=elapsed_time
            )
        except Exception as e:
            logging.error(f"Error rendering template: {e}")
            logging.error(traceback.format_exc())
            self.write(f"Error rendering search results: {str(e)}")