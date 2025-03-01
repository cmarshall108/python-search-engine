import json
import re
import math
import datetime
import logging
from collections import defaultdict, Counter
from urllib.parse import urlparse

from .db import SearchDatabase

class SearchEngine:
    
    def __init__(self, db_path="search_engine.db", use_db=True):
        # For backward compatibility, keep the in-memory structures
        self.index = defaultdict(list)
        self.documents = {}
        self.doc_count = 0
        
        # Use database system if enabled
        self.use_db = use_db
        if use_db:
            self.db = SearchDatabase(db_path)
            # Load doc_count from database for consistency
            self.doc_count = int(self.db.get_metadata('doc_count', 0))
        
    def add_document(self, url, title, content, metadata=None):
        """Add a document to the search index"""
        if not url or not content:
            return
            
        # Extract domain for favicon/preview
        try:
            domain = urlparse(url).netloc
        except:
            domain = ""
        
        # If metadata is provided, get domain from there if available
        if metadata and isinstance(metadata, dict):
            domain = metadata.get("domain", domain)
            
        if self.use_db:
            # Add document to database
            doc_id = self.db.add_document(url, title, content, domain)
            
            # Extract and index tokens
            words = self._tokenize(title + " " + content)
            if words:
                # Count word frequencies
                word_freq = Counter(words)
                total_words = len(words)
                
                # Normalize frequencies
                word_frequencies = {word: count/total_words for word, count in word_freq.items()}
                
                # Update the index in DB
                self.db.update_index(doc_id, word_frequencies)
            
            # Update document count for stats consistency
            self.doc_count = int(self.db.get_metadata('doc_count', 0))
            return doc_id
        else:
            # Legacy in-memory indexing
            doc_id = self.doc_count
            document = {
                'url': url,
                'title': title,
                'content': content,
                'domain': domain,
                'indexed_date': datetime.datetime.now().isoformat()
            }
            
            # Add metadata if provided
            if metadata and isinstance(metadata, dict):
                document.update({k: v for k, v in metadata.items() if k not in document})
                
            self.documents[doc_id] = document
            
            # Index the document
            words = self._tokenize(title + " " + content)
            for word in set(words):
                self.index[word].append(doc_id)
            
            self.doc_count += 1
            return doc_id
        
    def search(self, query, page=1, results_per_page=10, time_period=None):
        """Search for documents matching the query"""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return [], 0
        
        if self.use_db:
            # Use database search
            time_filter = None
            if time_period:
                # Convert time_period to ISO format date for filtering
                time_filter = datetime.datetime(time_period, 12, 31).isoformat()
                
            return self.db.search(
                query_tokens, 
                page=page,
                results_per_page=results_per_page,
                time_filter=time_filter
            )
        else:
            # Legacy in-memory search
            # Find matching documents
            matching_docs = self._find_matching_docs(query_tokens)
            
            # Apply time filter if specified
            if time_period:
                matching_docs = self._filter_by_time(matching_docs, time_period)
            
            # Calculate scores
            scored_docs = self._score_documents(query_tokens, matching_docs)
            
            # Sort by score
            sorted_docs = sorted(scored_docs.items(), key=lambda x: x[1], reverse=True)
            
            # Pagination
            total_results = len(sorted_docs)
            start_idx = (page - 1) * results_per_page
            end_idx = start_idx + results_per_page
            page_results = sorted_docs[start_idx:end_idx]
            
            # Format results
            results = []
            for doc_id, score in page_results:
                doc = self.documents[doc_id]
                snippet = self._generate_snippet(doc['content'], query_tokens)
                result = {
                    'title': doc['title'],
                    'url': doc['url'],
                    'snippet': snippet,
                    'score': score,
                    'domain': doc.get('domain', '')
                }
                
                # Add favicon URL for visual results
                result['favicon'] = f"https://www.google.com/s2/favicons?domain={doc.get('domain', '')}"
                
                # Try to determine an image for visual results (simplified version)
                if 'image.jpg' in doc['url'] or 'image.png' in doc['url']:
                    result['image'] = doc['url']
                
                results.append(result)
            
            return results, total_results
    
    def _find_matching_docs(self, query_tokens):
        """Find documents that match any of the query tokens"""
        matching_docs = set()
        for token in query_tokens:
            matching_docs.update(self.index.get(token, []))
        return matching_docs
    
    def _filter_by_time(self, doc_ids, year):
        """Filter documents by indexed year"""
        filtered_docs = []
        for doc_id in doc_ids:
            try:
                doc_date = datetime.datetime.fromisoformat(self.documents[doc_id]['indexed_date'])
                if doc_date.year <= year:
                    filtered_docs.append(doc_id)
            except:
                # If we can't parse the date, include it by default
                filtered_docs.append(doc_id)
        return filtered_docs
    
    def _score_documents(self, query_tokens, matching_docs):
        """Score documents based on TF-IDF"""
        scores = defaultdict(float)
        for doc_id in matching_docs:
            doc = self.documents[doc_id]
            doc_tokens = self._tokenize(doc['title'] + " " + doc['content'])
            
            for token in query_tokens:
                # Term frequency in document
                tf = doc_tokens.count(token) / len(doc_tokens) if doc_tokens else 0
                
                # Inverse document frequency
                idf = math.log(self.doc_count / (len(self.index.get(token, [])) + 1))
                
                # TF-IDF score
                scores[doc_id] += tf * idf
                
                # Boost score for title matches
                if token in self._tokenize(doc['title']):
                    scores[doc_id] += 0.5
        
        return scores
    
    def _generate_snippet(self, content, query_tokens):
        """Generate a relevant snippet from content"""
        # Delegate to DB if using database
        if self.use_db:
            return self.db._generate_snippet(content, query_tokens)
            
        # Legacy implementation
        content_lower = content.lower()
        max_snippet_length = 160
        
        # Try to find a section containing query terms
        best_start = 0
        max_matches = 0
        
        for i in range(len(content) - 50):
            window = content_lower[i:i + 100]
            matches = sum(1 for token in query_tokens if token in window)
            
            if matches > max_matches:
                max_matches = matches
                best_start = i
        
        # Create snippet around best position
        start = max(0, best_start - 20)
        end = min(len(content), best_start + max_snippet_length)
        
        snippet = content[start:end]
        
        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
            
        return snippet
    
    def _tokenize(self, text):
        """Convert text to lowercase tokens"""
        if not text:
            return []
            
        # Convert to lowercase and split on non-alphanumeric
        words = re.findall(r'\w+', text.lower())
        
        # Filter out short words and common English stopwords
        stopwords = {'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'in', 'on', 'of', 'to', 'for', 'with'}
        words = [word for word in words if len(word) > 1 and word not in stopwords]
        
        return words
    
    def save_index(self, filename="search_index.json"):
        """Save the search index to disk"""
        if self.use_db:
            # With DB, we don't need to save to JSON, but we'll provide a backup option
            try:
                logging.info(f"Database is already persistent. No need to save explicitly.")
                return True
            except Exception as e:
                logging.error(f"Error saving index: {e}")
                return False
        else:
            # Legacy JSON saving
            try:
                with open(filename, 'w') as f:
                    json.dump({
                        'index': {k: v for k, v in self.index.items()}, 
                        'documents': self.documents, 
                        'doc_count': self.doc_count
                    }, f)
                return True
            except Exception as e:
                logging.error(f"Error saving index to {filename}: {e}")
                return False
    
    def load_index(self, filename="search_index.json"):
        """Load the search index from disk"""
        if self.use_db:
            # If we're using the DB and want to import from JSON
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    
                    # Create in-memory search engine with the data
                    temp_engine = SearchEngine(use_db=False)
                    temp_engine.index = defaultdict(list, {k: v for k, v in data['index'].items()})
                    temp_engine.documents = {int(k): v for k, v in data['documents'].items()}
                    temp_engine.doc_count = data['doc_count']
                    
                    # Migrate the data to DB
                    success = self.db.migrate_from_memory(temp_engine)
                    if success:
                        # Update doc_count for stats consistency
                        self.doc_count = int(self.db.get_metadata('doc_count', 0))
                    return success
            except FileNotFoundError:
                logging.error(f"Index file {filename} not found.")
                return False
            except json.JSONDecodeError:
                logging.error(f"Error decoding {filename}. File may be corrupted.")
                return False
        else:
            # Legacy JSON loading
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                    self.index = defaultdict(list, data['index'])
                    self.documents = {int(k): v for k, v in data['documents'].items()}
                    self.doc_count = data['doc_count']
                return True
            except FileNotFoundError:
                logging.error(f"Index file {filename} not found.")
                return False
            except json.JSONDecodeError:
                logging.error(f"Error decoding {filename}. File may be corrupted.")
                return False
    
    def clear_index(self):
        """Clear the search index"""
        if self.use_db:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM index_entries')
                cursor.execute('DELETE FROM documents')
                cursor.execute("UPDATE metadata SET value = '0' WHERE key = 'doc_count'")
                conn.commit()
            
            self.doc_count = 0
        else:
            self.index = defaultdict(list)
            self.documents = {}
            self.doc_count = 0
    
    def get_stats(self):
        """Get statistics about the search index"""
        if self.use_db:
            return self.db.get_stats()
        else:
            # Legacy in-memory stats
            import sys
            
            # Calculate an estimated index size
            index_size_bytes = sys.getsizeof(self.index) + sys.getsizeof(self.documents)
            
            # Format size for display
            if index_size_bytes < 1024:
                size_str = f"{index_size_bytes} bytes"
            elif index_size_bytes < 1024 * 1024:
                size_str = f"{index_size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{index_size_bytes / (1024 * 1024):.1f} MB"
                
            return {
                "documents": len(self.documents),
                "keywords": len(self.index),
                "size": size_str
            }
