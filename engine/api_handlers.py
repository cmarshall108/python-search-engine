import tornado.web
import logging
import json
import time
import random
from datetime import datetime, timedelta

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

class SearchAPIHandler(tornado.web.RequestHandler):
    """Base class for all search API handlers"""
    
    def set_default_headers(self):
        """Set default headers for all API responses"""
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Headers", "x-requested-with")
    
    def write_error(self, status_code, **kwargs):
        """Write error response in JSON format"""
        self.set_header("Content-Type", "application/json")
        error_data = {
            "status": "error",
            "code": status_code,
            "message": self._reason
        }
        self.finish(json.dumps(error_data))
    
    def _handle_request_exception(self, e):
        """Handle uncaught exceptions"""
        logging.error(f"Uncaught exception in API request: {str(e)}")
        self.send_error(500, message="Internal server error")

class WebSearchAPIHandler(SearchAPIHandler):
    """Handle web search API requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        time_period = self.get_argument("time", None)
        
        if not query:
            self.write({"results": [], "total": 0})
            return
            
        start_time = time.time()
        results, total = self.application.search_engine.search(
            query, 
            page=page, 
            results_per_page=10, 
            time_period=time_period
        )
        
        # Format results for API response
        formatted_results = []
        for result in results:
            formatted_results.append({
                "title": result["title"],
                "url": result["url"],
                "snippet": result["snippet"],
                "domain": result["domain"],
                "favicon": result["favicon"]
            })
        
        self.write({
            "query": query,
            "results": formatted_results, 
            "total": total,
            "page": page,
            "time_taken": round(time.time() - start_time, 4)
        })

class ImageSearchAPIHandler(SearchAPIHandler):
    """Handle image search API requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        
        if not query:
            self.write({"results": [], "total": 0})
            return
        
        # For demonstration, we'll generate mock image results 
        # In a real application, these would come from the database
        results = self._generate_image_results(query, page)
        total = 120  # Mock total count
        
        self.write({
            "query": query,
            "results": results,
            "total": total,
            "page": page
        })
    
    def _generate_image_results(self, query, page, per_page=20):
        """Generate mock image results for demonstration"""
        results = []
        base_index = (page - 1) * per_page
        
        # Common image aspect ratios
        aspect_ratios = [(16, 9), (4, 3), (1, 1), (3, 2), (2, 3)]
        
        for i in range(per_page):
            # Skip if we reach the "end" of mock results
            if base_index + i >= 120:
                break
            
            # Pick a random aspect ratio
            aspect = random.choice(aspect_ratios)
            width = random.randint(300, 800)
            height = int(width * aspect[1] / aspect[0])
            
            # Generate a plausible URL based on query
            domain = random.choice(["pixabay.com", "unsplash.com", "pexels.com", "flickr.com", "500px.com"])
            image_id = f"{hash(query + str(base_index + i)) % 10000:04d}"
            
            results.append({
                "title": f"{query.title()} Image {base_index + i + 1}",
                "description": f"A {query} related image from {domain}",
                "thumbnail_url": f"https://source.unsplash.com/random/{width}x{height}?{query.replace(' ', '+')}",
                "url": f"https://source.unsplash.com/random/{width * 2}x{height * 2}?{query.replace(' ', '+')}",
                "source_url": f"https://{domain}/photos/{image_id}",
                "domain": domain,
                "width": width * 2,
                "height": height * 2,
                "thumbnail_width": width,
                "thumbnail_height": height
            })
        
        return results

class NewsSearchAPIHandler(SearchAPIHandler):
    """Handle news search API requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        
        if not query:
            self.write({"results": [], "total": 0})
            return
        
        # For demonstration, we'll generate mock news results 
        # In a real application, these would come from the database or news API
        results = self._generate_news_results(query, page)
        total = 50  # Mock total count
        
        self.write({
            "query": query,
            "results": results,
            "total": total,
            "page": page
        })
    
    def _generate_news_results(self, query, page, per_page=10):
        """Generate mock news results for demonstration"""
        results = []
        base_index = (page - 1) * per_page
        
        # News sources
        sources = [
            "The Daily News", "Tech Chronicles", "Science Today", 
            "World Report", "Business Insider", "Health Journal"
        ]
        
        # Generate dates within the last month
        today = datetime.now()
        
        for i in range(per_page):
            # Skip if we reach the "end" of mock results
            if base_index + i >= 50:
                break
            
            # Generate a random date within the last month
            days_ago = random.randint(0, 30)
            news_date = today - timedelta(days=days_ago)
            date_str = news_date.strftime("%b %d, %Y")
            
            # Select a source
            source = random.choice(sources)
            
            # Generate image URL for some news items
            has_image = random.random() > 0.3  # 70% of news have images
            image_url = f"https://source.unsplash.com/random/240x160?{query.replace(' ', '+')}" if has_image else None
            
            # Generate headline and snippet
            headline_templates = [
                f"New Research on {query} Shows Promising Results",
                f"Experts Discuss Future of {query}",
                f"Top 10 Things to Know About {query}",
                f"{query} Trends in 2025",
                f"The Impact of {query} on Modern Society"
            ]
            headline = random.choice(headline_templates)
            
            # Generate snippet
            snippets = [
                f"A recent study on {query} has revealed important insights that could change how we understand this topic.",
                f"Industry leaders gathered to discuss the latest developments in {query} and what they mean for the future.",
                f"As {query} continues to evolve, experts predict significant changes in how it's approached.",
                f"New technology is revolutionizing {query} according to leading researchers in the field.",
                f"The growing interest in {query} has led to innovative approaches and methodologies."
            ]
            snippet = random.choice(snippets)
            
            results.append({
                "title": headline,
                "snippet": snippet,
                "url": f"https://news-example.com/article/{base_index + i}",
                "source": source,
                "date": date_str,
                "image_url": image_url
            })
        
        return results

class VideoSearchAPIHandler(SearchAPIHandler):
    """Handle video search API requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        page = int(self.get_argument("page", 1))
        
        if not query:
            self.write({"results": [], "total": 0})
            return
        
        # Generate mock video results
        results = self._generate_video_results(query, page)
        total = 75  # Mock total count
        
        self.write({
            "query": query,
            "results": results,
            "total": total,
            "page": page
        })
    
    def _generate_video_results(self, query, page, per_page=12):
        """Generate mock video results for demonstration"""
        results = []
        base_index = (page - 1) * per_page
        
        # Video platforms
        platforms = ["VideoHub", "Streamly", "ViewTube", "MediaShare", "ClickStream"]
        
        # Duration ranges (in seconds)
        durations = [(30, 120), (120, 300), (300, 900), (900, 1800), (1800, 3600)]
        
        for i in range(per_page):
            if base_index + i >= 75:
                break
                
            # Generate random metadata
            platform = random.choice(platforms)
            duration_range = random.choice(durations)
            duration_secs = random.randint(*duration_range)
            views = random.randint(100, 1000000)
            
            # Format duration
            minutes = duration_secs // 60
            seconds = duration_secs % 60
            duration = f"{minutes}:{seconds:02d}"
            
            # Format views
            if views >= 1000000:
                views_str = f"{views/1000000:.1f}M"
            elif views >= 1000:
                views_str = f"{views/1000:.1f}K"
            else:
                views_str = str(views)
                
            # Generate thumbnail with different aspect ratio (16:9)
            width = 320
            height = 180
                
            results.append({
                "title": f"{query.title()} - {platform} Video {base_index + i + 1}",
                "description": f"Learn about {query} in this informative video",
                "thumbnail_url": f"https://source.unsplash.com/random/{width}x{height}?{query.replace(' ', '+')}",
                "video_url": f"https://example.com/videos/{query.replace(' ', '-')}-{base_index + i}",
                "platform": platform,
                "duration": duration,
                "views": views_str,
                "published": f"{random.randint(1, 12)} months ago"
            })
        
        return results

class SuggestionsAPIHandler(SearchAPIHandler):
    """Handle search suggestions requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        
        if not query or len(query) < 2:
            self.write({"suggestions": []})
            return
            
        # In a production system, you'd fetch suggestions from the database
        # or use a specialized service. Here we'll generate mock suggestions.
        suggestions = self._generate_suggestions(query)
        
        self.write({
            "query": query,
            "suggestions": suggestions
        })
    
    def _generate_suggestions(self, query):
        """Generate search suggestions based on query prefix"""
        common_suffixes = [
            " tutorial", " examples", " guide", 
            " definition", " vs", " meaning",
            " best practices", " for beginners", " advanced",
            " online", " course", " review"
        ]
        
        # Generate a base set of suggestions
        suggestions = [f"{query}{suffix}" for suffix in random.sample(common_suffixes, min(5, len(common_suffixes)))]
        
        # Add a "how to" suggestion if query doesn't already start with it
        if not query.lower().startswith("how to"):
            suggestions.append(f"how to {query}")
            
        # Add a "what is" suggestion if query doesn't already start with it
        if not query.lower().startswith(("what is", "what's")):
            suggestions.append(f"what is {query}")
        
        # Shuffle and limit
        random.shuffle(suggestions)
        return suggestions[:7]  # Return up to 7 suggestions

class QuickAnswerAPIHandler(SearchAPIHandler):
    """Handle quick answer requests for featured snippets"""
    
    def get(self):
        query = self.get_argument("q", "")
        
        if not query:
            self.write({"has_answer": False})
            return
            
        # In a real system, you'd use NLP or look up structured data
        # Here we'll use some hardcoded answers for demo purposes
        answer = self._generate_answer(query)
        
        if answer:
            self.write({
                "query": query,
                "has_answer": True,
                "answer": answer
            })
        else:
            self.write({
                "query": query,
                "has_answer": False
            })
    
    @staticmethod
    def _generate_answer(query_text, ignored=None):
        """Generate a quick answer for common queries"""
        # Process the query text directly without complex logic
        query_lower = query_text.lower() if query_text else ""
        
        # Definition-type answers
        definitions = {
            "algorithm": {
                "title": "Algorithm Definition",
                "content": "An algorithm is a step-by-step procedure or formula for solving a problem, based on conducting a sequence of specified actions. In computing, algorithms are essential for processing data, making calculations, automated reasoning, and other tasks.",
                "source": "Computer Science Encyclopedia",
                "source_url": "https://example.com/algorithm"
            },
            "python": {
                "title": "Python Programming Language",
                "content": "Python is a high-level, interpreted programming language known for its readability and versatility. It supports multiple programming paradigms and is widely used in web development, data science, artificial intelligence, and more.",
                "source": "Programming Language Database",
                "source_url": "https://example.com/python"
            },
            "html": {
                "title": "HTML (HyperText Markup Language)",
                "content": "HTML (HyperText Markup Language) is the standard markup language for documents designed to be displayed in a web browser. It defines the structure and content of web pages using a series of elements that label pieces of content.",
                "source": "Web Development Guide",
                "source_url": "https://example.com/html"
            },
        }
        
        # Check if query matches any definitions
        for key, data in definitions.items():
            if key in query_lower.split():
                return data
        
        # How-to answers
        if query_lower.startswith("how to"):
            topic = query_lower[7:].strip()
            
            how_tos = {
                "create a website": {
                    "title": "How to Create a Website",
                    "content": "1. Choose and register a domain name\n2. Select a web hosting provider\n3. Set up your website using a CMS or HTML\n4. Design your website layout\n5. Add content to your pages\n6. Test and publish your website",
                    "source": "Web Development Basics",
                    "source_url": "https://example.com/create-website"
                },
                "learn programming": {
                    "title": "How to Learn Programming",
                    "content": "1. Choose a programming language to start with (Python is recommended for beginners)\n2. Use free online resources and tutorials\n3. Practice with small projects\n4. Join coding communities\n5. Build a portfolio of projects\n6. Continue learning and exploring new technologies",
                    "source": "Coding Education Resource",
                    "source_url": "https://example.com/learn-programming"
                }
            }
            
            for key, data in how_tos.items():
                if key in topic:
                    return data
        
        # No match found
        return None

class RelatedSearchesAPIHandler(SearchAPIHandler):
    """Handle related searches requests"""
    
    def get(self):
        query = self.get_argument("q", "")
        
        if not query:
            self.write({"related": []})
            return
            
        # In a real system, you'd use query logs and clustering
        # Here we'll generate plausible related searches
        related = self._generate_related_searches(query)
        
        self.write({
            "query": query,
            "related": related
        })
    
    @staticmethod
    def _generate_related_searches(query_text, ignored=None):
        """Generate related search terms"""
        # Ensure query_text is a string
        query_text = str(query_text) if query_text is not None else ""
        words = query_text.lower().split()
        
        related = []
        
        # Add variations by adding adjectives
        adjectives = ["best", "top", "new", "popular", "easy", "advanced", "free"]
        for adj in random.sample(adjectives, 2):
            related.append(f"{adj} {query_text}")
        
        # Add variations by adding common suffixes
        suffixes = [" tutorial", " examples", " alternatives", " courses", " books"]
        for suffix in random.sample(suffixes, 2):
            related.append(f"{query_text}{suffix}")
        
        # Add "vs" comparisons if query_text is a single word
        if len(words) == 1:
            alternatives = ["alternative", "competitor", "vs python", "vs javascript", "vs react"]
            related.append(f"{query_text} vs {random.choice(alternatives)}")
        
        # Add "how to" and "what is" if not already in query_text
        if not query_text.startswith(("how to", "what is")):
            related.append(f"how to use {query_text}")
            related.append(f"what is {query_text}")
        
        # Remove duplicates and limit to 8
        unique_related = list(dict.fromkeys(related))
        return unique_related[:8]
