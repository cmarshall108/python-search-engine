#!/usr/bin/env python3
"""
Debug utility to test the SmartCrawler functionality directly
"""
import os
import sys
import logging
import time
import requests
import traceback
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from queue import Queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def test_fetch(url):
    """Test fetching a URL directly to see if there's a connection issue"""
    logging.info(f"Testing direct fetch of URL: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        start_time = time.time()
        response = requests.get(
            url, 
            headers=headers, 
            timeout=15,
            allow_redirects=True,
            verify=True
        )
        elapsed = time.time() - start_time
        
        logging.info(f"Fetch completed in {elapsed:.2f}s with status: {response.status_code}")
        logging.info(f"Content type: {response.headers.get('Content-Type')}")
        logging.info(f"Content length: {len(response.text)} bytes")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "No title found"
            logging.info(f"Page title: {title}")
            
            # Count links
            links = soup.find_all('a', href=True)
            logging.info(f"Found {len(links)} links on the page")
            
            # Show first few links
            for i, link in enumerate(links[:5]):
                href = link['href']
                logging.info(f"  Link {i+1}: {href}")
            
            return True, response.text
            
    except Exception as e:
        logging.error(f"Error fetching URL: {e}")
        logging.error(traceback.format_exc())
        return False, str(e)
        
    return False, "Unknown error"

def create_mock_search_engine():
    """Create a simple mock search engine"""
    class MockSearchEngine:
        def __init__(self):
            self.documents = {}
            self.index = {}
            self.use_db = False
            self.db = None
            
        def add_document(self, url, title, content, metadata=None):
            doc_id = len(self.documents) + 1
            self.documents[doc_id] = {
                'url': url,
                'title': title,
                'content': content[:100] + '...' if len(content) > 100 else content,
                'metadata': metadata or {}
            }
            logging.info(f"Added document {doc_id}: {title}")
            return doc_id
            
        def get_stats(self):
            return {
                "documents": len(self.documents),
                "keywords": len(self.index)
            }
    
    return MockSearchEngine()

def test_crawler():
    """Test the SmartCrawler manually"""
    try:
        # Import the crawler module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from advanced_crawler import SmartCrawler
        
        # Create a mock search engine
        search_engine = create_mock_search_engine()
        
        # Create a crawler instance
        crawler = SmartCrawler(search_engine)
        
        # Test URLs to try
        test_urls = [
            "https://example.com",
            "https://google.com",
            "https://httpbin.org/html"
        ]
        
        # Test URL fetching
        for url in test_urls:
            logging.info(f"\n===== Testing URL: {url} =====")
            success, content = test_fetch(url)
            
            if success:
                # Test processing the page content
                logging.info("\n----- Testing page processing -----")
                try:
                    # Mock headers
                    headers = {'Content-Type': 'text/html'}
                    
                    # Extract content
                    title, main_content = crawler.extract_text_content(content, url)
                    logging.info(f"Extracted title: {title}")
                    logging.info(f"Content length: {len(main_content)} chars")
                    
                    # Extract links
                    links = crawler.extract_links(content, url)
                    logging.info(f"Extracted {len(links)} links")
                    
                    # Test adding to queue
                    links_added = crawler._add_links_to_queue(links[:10], 0)
                    logging.info(f"Added {links_added} links to queue")
                    
                except Exception as e:
                    logging.error(f"Error processing page: {e}")
                    logging.error(traceback.format_exc())
            
            logging.info(f"===== Finished testing {url} =====\n")
        
        # Test the complete crawl process for a single page
        test_url = "https://httpbin.org/html"  # Simple test page
        logging.info(f"\n===== Testing full crawl process on {test_url} =====")
        
        # Reset crawler
        crawler = SmartCrawler(search_engine)
        
        # Manually execute the fetch and process steps
        logging.info("Fetching page...")
        content, status_code, headers = crawler._fetch_page(test_url)
        
        if status_code == 200:
            logging.info(f"Processing page with {len(content)} bytes of content")
            crawler._process_page(test_url, content, headers, 0)
            logging.info("Page processed")
            logging.info(f"Documents indexed: {len(search_engine.documents)}")
        else:
            logging.error(f"Failed to fetch {test_url}: status code {status_code}")
            
    except ImportError as e:
        logging.error(f"Error importing SmartCrawler: {e}")
        logging.error(traceback.format_exc())
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    logging.info("Starting crawler debug utility")
    test_crawler()
    logging.info("Crawler debug utility completed")
