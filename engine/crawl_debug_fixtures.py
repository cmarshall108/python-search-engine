"""
Debug fixtures to help test the crawler with controlled content
"""
import os
import tempfile
import http.server
import socketserver
import threading
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class TestWebServer:
    """A simple web server that serves test HTML pages"""
    
    def __init__(self, port=8000):
        self.port = port
        self.server = None
        self.server_thread = None
        self.temp_dir = None
        
    def start(self):
        """Start the test web server"""
        # Create a temporary directory to store HTML files
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        
        # Create test HTML files
        self._create_test_pages()
        
        # Start the server in a separate thread
        handler = http.server.SimpleHTTPRequestHandler
        self.server = socketserver.TCPServer(("", self.port), handler)
        
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        
        logging.info(f"Test web server started on port {self.port}")
        logging.info(f"Test pages available at http://localhost:{self.port}/")
        
        return f"http://localhost:{self.port}/"
    
    def stop(self):
        """Stop the test web server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logging.info("Test web server stopped")
        
        if self.temp_dir:
            self.temp_dir.cleanup()
    
    def _create_test_pages(self):
        """Create test HTML files with links between them"""
        # Home page
        with open("index.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Home Page</title>
                <meta name="description" content="This is a test home page">
            </head>
            <body>
                <h1>Test Home Page</h1>
                <p>This is the main test page for the crawler test.</p>
                <nav>
                    <ul>
                        <li><a href="page1.html">Page 1</a></li>
                        <li><a href="page2.html">Page 2</a></li>
                        <li><a href="page3.html">Page 3</a></li>
                        <li><a href="blog/index.html">Blog</a></li>
                    </ul>
                </nav>
            </body>
            </html>
            """)
        
        # Page 1
        with open("page1.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Page 1</title>
                <meta name="description" content="This is test page 1">
            </head>
            <body>
                <h1>Test Page 1</h1>
                <p>This is test page 1 with some content.</p>
                <p><a href="index.html">Back to Home</a></p>
                <p><a href="page2.html">Go to Page 2</a></p>
                <p><a href="duplicate.html">Duplicate Content</a></p>
            </body>
            </html>
            """)
        
        # Page 2
        with open("page2.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Page 2</title>
                <meta name="description" content="This is test page 2">
            </head>
            <body>
                <h1>Test Page 2</h1>
                <p>This is test page 2 with some different content.</p>
                <p><a href="index.html">Back to Home</a></p>
                <p><a href="page3.html">Go to Page 3</a></p>
            </body>
            </html>
            """)
        
        # Page 3
        with open("page3.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Page 3</title>
                <meta name="description" content="This is test page 3">
            </head>
            <body>
                <h1>Test Page 3</h1>
                <p>This is test page 3 with some more content.</p>
                <p><a href="index.html">Back to Home</a></p>
            </body>
            </html>
            """)
        
        # Duplicate Content 
        with open("duplicate.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Page Duplicate</title>
                <meta name="description" content="This is a duplicate test page">
            </head>
            <body>
                <h1>Test Page Duplicate</h1>
                <p>This page has the same content as another page.</p>
                <p>This is test page 2 with some different content.</p>
                <p><a href="index.html">Back to Home</a></p>
            </body>
            </html>
            """)
        
        # Create blog directory
        os.makedirs("blog", exist_ok=True)
        
        # Blog index
        with open("blog/index.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Blog Index</title>
                <meta name="description" content="This is a test blog index">
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Blog",
                    "name": "Test Blog",
                    "description": "This is a test blog for crawler testing"
                }
                </script>
            </head>
            <body>
                <h1>Test Blog</h1>
                <p>This is a test blog for crawler testing.</p>
                <ul>
                    <li><a href="post1.html">Blog Post 1</a></li>
                    <li><a href="post2.html">Blog Post 2</a></li>
                </ul>
                <p><a href="../index.html">Back to Home</a></p>
            </body>
            </html>
            """)
        
        # Blog post 1
        with open("blog/post1.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Blog Post 1</title>
                <meta name="description" content="This is blog post 1">
            </head>
            <body>
                <article>
                    <h1>Blog Post 1</h1>
                    <p>This is blog post 1 with a lot of content.</p>
                    <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                    <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p>
                    <p><a href="index.html">Back to Blog Index</a></p>
                    <p><a href="post2.html">Read Blog Post 2</a></p>
                </article>
            </body>
            </html>
            """)
        
        # Blog post 2
        with open("blog/post2.html", "w") as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Blog Post 2</title>
                <meta name="description" content="This is blog post 2">
            </head>
            <body>
                <article>
                    <h1>Blog Post 2</h1>
                    <p>This is blog post 2 with a different content.</p>
                    <p>Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.</p>
                    <p>Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.</p>
                    <p><a href="index.html">Back to Blog Index</a></p>
                    <p><a href="post1.html">Read Blog Post 1</a></p>
                </article>
            </body>
            </html>
            """)

def run_test_with_local_server():
    """Run a test with a local web server"""
    server = TestWebServer(port=8765)
    base_url = server.start()
    
    try:
        # Import modules here to avoid circular imports
        from search import SearchEngine
        from advanced_crawler import SmartCrawler
        
        print(f"Starting test crawl of local server at {base_url}")
        
        # Initialize the search engine
        search_engine = SearchEngine(db_path="test_search_engine.db", use_db=True)
        
        # Create the crawler
        crawler = SmartCrawler(search_engine)
        
        # Start crawling
        success = crawler.crawl(base_url, depth=3)
        if not success:
            print("Failed to start crawler")
            return
        
        # Wait for crawling to finish
        while crawler.is_crawling:
            stats = crawler.get_stats()
            print(f"Progress: {stats['crawled']} crawled, {stats['indexed']} indexed, " +
                  f"{stats['errors']} errors, {stats.get('queue_size', '?')} in queue")
            time.sleep(1)
        
        # Print results
        stats = crawler.get_stats()
        print("\nFinal crawler stats:")
        print(f"Status: {stats['status']}")
        print(f"Pages crawled: {stats['crawled']}")
        print(f"Pages indexed: {stats['indexed']}")
        print(f"Errors: {stats['errors']}")
        
        # Test search
        print("\nTesting search functionality:")
        results, count = search_engine.search("test")
        print(f"Found {count} results for 'test'")
        for i, result in enumerate(results[:3], 1):
            print(f"{i}. {result['title']} - {result['url']}")
        
    finally:
        server.stop()

if __name__ == "__main__":
    run_test_with_local_server()
