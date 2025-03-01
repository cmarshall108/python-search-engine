import sqlite3
import json
import os
import time
import logging
import gzip
from datetime import datetime
from contextlib import contextmanager

class SearchDatabase:
    """Database interface for the search engine"""
    
    def __init__(self, db_path="search_engine.db"):
        """Initialize the database connection"""
        self.db_path = db_path
        self.init_db()
        
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        try:
            yield conn
        finally:
            conn.close()
    
    def init_db(self):
        """Initialize the database schema if it doesn't exist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Documents table - stores web pages and their content
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                content TEXT,
                domain TEXT,
                indexed_date TEXT,
                last_updated TEXT,
                status INTEGER DEFAULT 1
            )
            ''')
            
            # Index table - stores word to document mappings
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_entries (
                word TEXT NOT NULL,
                doc_id INTEGER NOT NULL,
                frequency REAL,
                importance REAL DEFAULT 1.0,
                FOREIGN KEY (doc_id) REFERENCES documents (id),
                PRIMARY KEY (word, doc_id)
            )
            ''')
            
            # Create index on words for faster lookups
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_word ON index_entries(word)
            ''')
            
            # Cache table - stores page content with timestamps
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                url TEXT PRIMARY KEY,
                content BLOB,
                headers TEXT,
                status_code INTEGER,
                timestamp TEXT,
                expiry TEXT
            )
            ''')
            
            # Metadata table - stores various configuration and stats
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated TEXT
            )
            ''')
            
            # Crawler visits - tracks URLs that have been crawled
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawler_visits (
                url TEXT PRIMARY KEY,
                visit_date TEXT,
                depth INTEGER,
                success INTEGER DEFAULT 1
            )
            ''')
            
            # Initialize metadata
            current_time = datetime.now().isoformat()
            cursor.execute('''
            INSERT OR IGNORE INTO metadata (key, value, updated)
            VALUES (?, ?, ?)
            ''', ('doc_count', '0', current_time))
            
            cursor.execute('''
            INSERT OR IGNORE INTO metadata (key, value, updated)
            VALUES (?, ?, ?)
            ''', ('last_crawl_time', '0', current_time))
            
            conn.commit()
    
    def add_document(self, url, title, content, domain=""):
        """Add a document to the search index"""
        current_time = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Insert or update the document
            cursor.execute('''
            INSERT OR REPLACE INTO documents (url, title, content, domain, indexed_date, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (url, title, content, domain, current_time, current_time))
            
            doc_id = cursor.lastrowid
            
            # Update document count
            cursor.execute('''
            UPDATE metadata SET value = value + 1, updated = ?
            WHERE key = 'doc_count' AND NOT EXISTS (
                SELECT 1 FROM documents WHERE url = ? AND id != ?
            )
            ''', (current_time, url, doc_id))
            
            conn.commit()
            
            return doc_id
    
    def update_index(self, doc_id, word_frequencies):
        """Update the search index for a document"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete existing index entries for this document
            cursor.execute('DELETE FROM index_entries WHERE doc_id = ?', (doc_id,))
            
            # Insert new index entries
            for word, frequency in word_frequencies.items():
                cursor.execute('''
                INSERT INTO index_entries (word, doc_id, frequency)
                VALUES (?, ?, ?)
                ''', (word, doc_id, frequency))
            
            conn.commit()
    
    def search(self, query_tokens, page=1, results_per_page=10, time_filter=None):
        """Search for documents matching the query tokens"""
        if not query_tokens:
            return [], 0
            
        # Create placeholders for the SQL query
        placeholders = ', '.join(['?'] * len(query_tokens))
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Base SQL query - join documents with index entries
            base_query = '''
            SELECT d.id, d.url, d.title, d.content, d.domain, d.indexed_date,
                   SUM(i.frequency * i.importance) as score
            FROM documents d
            JOIN index_entries i ON d.id = i.doc_id
            WHERE i.word IN ({placeholders}) AND d.status = 1
            '''.format(placeholders=placeholders)
            
            # Add time filter if specified
            time_clause = ''
            params = list(query_tokens)
            
            if time_filter:
                time_clause = ' AND d.indexed_date <= ?'
                params.append(time_filter)
                
            # Complete the query with grouping and ordering
            query_sql = base_query + time_clause + '''
            GROUP BY d.id
            ORDER BY score DESC
            LIMIT ? OFFSET ?
            '''
            
            # Add pagination parameters
            params.append(results_per_page)
            params.append((page - 1) * results_per_page)
            
            # Execute search query
            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            
            # Count total results
            count_query = '''
            SELECT COUNT(DISTINCT d.id) as total
            FROM documents d
            JOIN index_entries i ON d.id = i.doc_id
            WHERE i.word IN ({placeholders}) AND d.status = 1
            '''.format(placeholders=placeholders)
            
            count_params = list(query_tokens)
            if time_filter:
                count_query += time_clause
                count_params.append(time_filter)
                
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            
            # Format the results
            formatted_results = []
            for row in results:
                snippet = self._generate_snippet(row['content'], query_tokens)
                formatted_results.append({
                    'id': row['id'],
                    'url': row['url'],
                    'title': row['title'],
                    'snippet': snippet,
                    'domain': row['domain'],
                    'score': row['score'],
                    'favicon': f"https://www.google.com/s2/favicons?domain={row['domain']}"
                })
            
            return formatted_results, total_count
    
    def get_document(self, url):
        """Retrieve a document by URL"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM documents WHERE url = ?', (url,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_document_by_id(self, doc_id):
        """Retrieve a document by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM documents WHERE id = ?', (doc_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def mark_url_visited(self, url, depth=0, success=True):
        """Mark a URL as visited by the crawler"""
        visit_date = datetime.now().isoformat()
        success_int = 1 if success else 0
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO crawler_visits (url, visit_date, depth, success)
            VALUES (?, ?, ?, ?)
            ''', (url, visit_date, depth, success_int))
            conn.commit()
    
    def is_url_visited(self, url):
        """Check if a URL has been visited"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM crawler_visits WHERE url = ?', (url,))
            return cursor.fetchone() is not None
    
    def cache_page(self, url, content, headers, status_code, expiry_seconds=86400):
        """Cache a page's content"""
        timestamp = datetime.now().isoformat()
        expiry = datetime.fromtimestamp(time.time() + expiry_seconds).isoformat()
        headers_json = json.dumps(dict(headers))
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO cache (url, content, headers, status_code, timestamp, expiry)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (url, content, headers_json, status_code, timestamp, expiry))
            conn.commit()
    
    def get_cached_page(self, url):
        """Get a cached page if it exists and is not expired"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM cache WHERE url = ? AND expiry > ?
            ''', (url, datetime.now().isoformat()))
            cache = cursor.fetchone()
            
            if cache:
                result = dict(cache)
                result['headers'] = json.loads(result['headers'])
                return result
            return None
    
    def clear_cache(self):
        """Clear the cache table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cache')
            conn.commit()
    
    def clear_expired_cache(self):
        """Clear expired cache entries"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM cache WHERE expiry < ?', (datetime.now().isoformat(),))
            conn.commit()
            return cursor.rowcount
    
    def update_metadata(self, key, value):
        """Update a metadata value"""
        current_time = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO metadata (key, value, updated)
            VALUES (?, ?, ?)
            ''', (key, str(value), current_time))
            conn.commit()
    
    def get_metadata(self, key, default=None):
        """Get a metadata value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM metadata WHERE key = ?', (key,))
            result = cursor.fetchone()
            return result[0] if result else default
    
    def _generate_snippet(self, content, query_tokens, max_length=160):
        """Generate a relevant snippet from content containing query tokens"""
        if not content:
            return ""
            
        content_lower = content.lower()
        best_start = 0
        max_matches = 0
        
        # Find the best section containing query terms
        for i in range(len(content) - 50):
            window = content_lower[i:i+100]
            matches = sum(1 for token in query_tokens if token in window)
            
            if matches > max_matches:
                max_matches = matches
                best_start = i
        
        # Create snippet
        start = max(0, best_start - 20)
        end = min(len(content), best_start + max_length)
        
        snippet = content[start:end]
        
        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
            
        return snippet
    
    def get_stats(self):
        """Get database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get document count
            cursor.execute('SELECT COUNT(*) FROM documents')
            doc_count = cursor.fetchone()[0]
            
            # Get word count
            cursor.execute('SELECT COUNT(DISTINCT word) FROM index_entries')
            word_count = cursor.fetchone()[0]
            
            # Get cache size
            cursor.execute('SELECT COUNT(*) FROM cache')
            cache_count = cursor.fetchone()[0]
            
            # Get database file size
            try:
                db_size = os.path.getsize(self.db_path)
                if db_size < 1024:
                    db_size_str = f"{db_size} bytes"
                elif db_size < 1024 * 1024:
                    db_size_str = f"{db_size / 1024:.1f} KB"
                else:
                    db_size_str = f"{db_size / (1024 * 1024):.1f} MB"
            except:
                db_size_str = "Unknown"
            
            return {
                "documents": doc_count,
                "keywords": word_count,
                "cached_pages": cache_count,
                "database_size": db_size_str
            }
    
    def migrate_from_memory(self, search_engine):
        """Migrate data from in-memory SearchEngine instance to the database"""
        doc_count = 0
        word_count = 0
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Begin transaction for better performance
            cursor.execute('BEGIN TRANSACTION')
            
            try:
                # Migrate documents
                for doc_id, doc in search_engine.documents.items():
                    url = doc['url']
                    title = doc['title']
                    content = doc['content']
                    domain = doc.get('domain', '')
                    indexed_date = doc.get('indexed_date', datetime.now().isoformat())
                    
                    cursor.execute('''
                    INSERT OR REPLACE INTO documents (id, url, title, content, domain, indexed_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (doc_id, url, title, content, domain, indexed_date, datetime.now().isoformat()))
                    doc_count += 1
                
                # Migrate index
                for word, doc_ids in search_engine.index.items():
                    for doc_id in doc_ids:
                        content = search_engine.documents[doc_id]['content']
                        title = search_engine.documents[doc_id]['title']
                        text = title + " " + content
                        
                        # Get word frequency
                        word_tokens = search_engine._tokenize(text)
                        frequency = word_tokens.count(word) / len(word_tokens) if word_tokens else 0
                        
                        # Increase importance if word appears in title
                        importance = 1.5 if word in search_engine._tokenize(title) else 1.0
                        
                        cursor.execute('''
                        INSERT OR REPLACE INTO index_entries (word, doc_id, frequency, importance)
                        VALUES (?, ?, ?, ?)
                        ''', (word, doc_id, frequency, importance))
                        word_count += 1
                
                # Update metadata
                cursor.execute('''
                INSERT OR REPLACE INTO metadata (key, value, updated)
                VALUES (?, ?, ?)
                ''', ('doc_count', str(search_engine.doc_count), datetime.now().isoformat()))
                
                # Commit the transaction
                conn.commit()
                
                logging.info(f"Migration completed: {doc_count} documents and {word_count} index entries migrated")
                return True
            except Exception as e:
                conn.rollback()
                logging.error(f"Migration failed: {str(e)}")
                return False

class OptimizedSearchDatabase(SearchDatabase):
    """Enhanced database interface with compression and optimization"""
    
    def __init__(self, db_path="search_engine_optimized.db"):
        super().__init__(db_path)
        self.init_optimized_db()
    
    def init_optimized_db(self):
        """Initialize additional optimized tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Optimized content storage with compression
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS compressed_content (
                doc_id INTEGER PRIMARY KEY,
                content BLOB,  -- Compressed content
                compression TEXT DEFAULT 'gzip',
                original_size INTEGER,
                compressed_size INTEGER,
                FOREIGN KEY (doc_id) REFERENCES documents (id)
            )
            ''')
            
            # Create full-text search index for more efficient searches
            cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
                content, title, url, domain,
                content_rowid=id,
                tokenize='porter unicode61'
            )
            ''')
            
            # Domain statistics table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS domain_stats (
                domain TEXT PRIMARY KEY,
                pages_count INTEGER DEFAULT 0,
                last_crawled TEXT,
                avg_page_size INTEGER DEFAULT 0,
                importance REAL DEFAULT 1.0
            )
            ''')
            
            # Create table for embeddings if using vector search
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS embeddings (
                doc_id INTEGER PRIMARY KEY,
                vector BLOB,  -- Binary serialized vector
                dimensions INTEGER,
                model TEXT,
                FOREIGN KEY (doc_id) REFERENCES documents (id)
            )
            ''')
            
            conn.commit()
    
    def compress_content(self, content):
        """Compress text content using gzip"""
        if not content:
            return None, 0, 0
            
        original_size = len(content.encode('utf-8'))
        compressed = gzip.compress(content.encode('utf-8'))
        compressed_size = len(compressed)
        
        return compressed, original_size, compressed_size
    
    def decompress_content(self, compressed_data):
        """Decompress gzipped content"""
        if not compressed_data:
            return ""
            
        return gzip.decompress(compressed_data).decode('utf-8')
    
    def add_document(self, url, title, content, domain=""):
        """Add a document with compressed storage and FTS indexing"""
        doc_id = super().add_document(url, title, content, domain)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Compress the content
            compressed, original_size, compressed_size = self.compress_content(content)
            
            # Store compressed content
            cursor.execute('''
            INSERT OR REPLACE INTO compressed_content 
            (doc_id, content, original_size, compressed_size)
            VALUES (?, ?, ?, ?)
            ''', (doc_id, compressed, original_size, compressed_size))
            
            # Add to full-text search index
            cursor.execute('''
            INSERT OR REPLACE INTO fts_index (rowid, content, title, url, domain)
            VALUES (?, ?, ?, ?, ?)
            ''', (doc_id, content, title, url, domain))
            
            # Update domain statistics
            cursor.execute('''
            INSERT OR REPLACE INTO domain_stats (domain, pages_count, last_crawled, avg_page_size)
            VALUES (
                ?,
                COALESCE((SELECT pages_count FROM domain_stats WHERE domain = ?) + 1, 1),
                ?,
                (
                    COALESCE((SELECT avg_page_size FROM domain_stats WHERE domain = ?), 0) * 
                    COALESCE((SELECT pages_count FROM domain_stats WHERE domain = ?), 0) + ?
                ) / (COALESCE((SELECT pages_count FROM domain_stats WHERE domain = ?), 0) + 1)
            )
            ''', (domain, domain, datetime.now().isoformat(), domain, domain, original_size, domain))
            
            conn.commit()
        
        return doc_id
    
    def fts_search(self, query_string, page=1, results_per_page=10):
        """Perform a full-text search using the FTS5 index"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Execute FTS query - customize this based on your relevance needs
            cursor.execute('''
            SELECT 
                d.id, d.url, d.title, d.domain, d.indexed_date,
                snippet(fts_index, 0, '<b>', '</b>', '...', 20) as snippet,
                rank
            FROM fts_index
            JOIN documents d ON fts_index.rowid = d.id
            WHERE fts_index MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
            ''', (query_string, results_per_page, (page - 1) * results_per_page))
            
            results = cursor.fetchall()
            
            # Count total results
            cursor.execute('''
            SELECT COUNT(*) FROM fts_index WHERE fts_index MATCH ?
            ''', (query_string,))
            
            total_count = cursor.fetchone()[0]
            
            # Format results
            formatted_results = []
            for row in results:
                formatted_results.append({
                    'id': row['id'],
                    'url': row['url'],
                    'title': row['title'],
                    'snippet': row['snippet'],
                    'domain': row['domain'],
                    'score': row['rank'],
                    'favicon': f"https://www.google.com/s2/favicons?domain={row['domain']}"
                })
            
            return formatted_results, total_count
    
    def hybrid_search(self, query_tokens, query_string, page=1, results_per_page=10):
        """Perform a hybrid search combining inverted index and FTS"""
        # First get candidates from the inverted index (more structured)
        inverted_results, count = super().search(query_tokens, page=1, results_per_page=100)
        inverted_ids = [r['id'] for r in inverted_results]
        
        if not inverted_ids:
            # Fallback to FTS only if no inverted index results
            return self.fts_search(query_string, page, results_per_page)
        
        # Then filter and re-rank using FTS
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            placeholders = ', '.join(['?'] * len(inverted_ids))
            
            cursor.execute(f'''
            SELECT 
                d.id, d.url, d.title, d.domain, d.indexed_date,
                snippet(fts_index, 0, '<b>', '</b>', '...', 20) as snippet,
                rank
            FROM fts_index
            JOIN documents d ON fts_index.rowid = d.id
            WHERE fts_index MATCH ? AND d.id IN ({placeholders})
            ORDER BY rank
            LIMIT ? OFFSET ?
            ''', [query_string] + inverted_ids + [results_per_page, (page - 1) * results_per_page])
            
            results = cursor.fetchall()
            
            # Format results
            formatted_results = []
            for row in results:
                formatted_results.append({
                    'id': row['id'],
                    'url': row['url'],
                    'title': row['title'],
                    'snippet': row['snippet'],
                    'domain': row['domain'],
                    'score': row['rank'],
                    'favicon': f"https://www.google.com/s2/favicons?domain={row['domain']}"
                })
            
            return formatted_results, count
    
    def rebuild_fts_index(self):
        """Rebuild the FTS index from the documents table"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Clear the FTS index
            cursor.execute('DELETE FROM fts_index')
            
            # Rebuild from documents table
            cursor.execute('''
            INSERT INTO fts_index(rowid, content, title, url, domain)
            SELECT id, content, title, url, domain FROM documents
            ''')
            
            conn.commit()
            
            # Return the count of indexed documents
            return cursor.rowcount
    
    def optimize_storage(self):
        """Optimize database storage"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Optimize the FTS index
            cursor.execute('INSERT INTO fts_index(fts_index) VALUES("optimize")')
            
            # Run VACUUM to reclaim space and defragment
            cursor.execute('VACUUM')
            
            conn.commit()
    
    def get_domain_importance(self):
        """Get domain importance scores for crawler prioritization"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT domain, pages_count, importance
            FROM domain_stats
            ORDER BY importance DESC
            ''')
            
            domains = cursor.fetchall()
            
            # Format as dictionary
            domain_importance = {}
            for row in domains:
                domain_importance[row['domain']] = row['importance']
                
            return domain_importance
    
    def update_domain_importance(self, domain, importance):
        """Update the importance score for a domain"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE domain_stats
            SET importance = ?
            WHERE domain = ?
            ''', (importance, domain))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def get_storage_stats(self):
        """Get storage efficiency statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get compression stats
            cursor.execute('''
            SELECT 
                SUM(original_size) as total_original,
                SUM(compressed_size) as total_compressed
            FROM compressed_content
            ''')
            
            compression = cursor.fetchone()
            
            if compression and compression['total_original'] and compression['total_compressed']:
                original_size = compression['total_original']
                compressed_size = compression['total_compressed']
                savings_percent = round((1 - compressed_size / original_size) * 100, 2)
                
                return {
                    "original_size": self._format_size(original_size),
                    "compressed_size": self._format_size(compressed_size),
                    "savings_percent": savings_percent,
                    "savings": self._format_size(original_size - compressed_size)
                }
            
            return {
                "original_size": "0 B",
                "compressed_size": "0 B",
                "savings_percent": 0,
                "savings": "0 B"
            }
    
    def _format_size(self, size_bytes):
        """Format size in bytes to human readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024)::.2f} GB"
    
    def clear_index(self):
        """Clear all index data while preserving database structure"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Start transaction for faster operation
            cursor.execute('BEGIN TRANSACTION')
            
            try:
                # Clear the primary tables
                cursor.execute('DELETE FROM index_entries')
                cursor.execute('DELETE FROM documents')
                
                # Also clear the additional optimized tables
                cursor.execute('DELETE FROM compressed_content')
                cursor.execute('DELETE FROM fts_index')
                cursor.execute('DELETE FROM embeddings')
                
                # Reset domain stats without deleting records
                cursor.execute('UPDATE domain_stats SET pages_count=0, avg_page_size=0')
                
                # Reset document count in metadata
                cursor.execute("UPDATE metadata SET value = '0' WHERE key = 'doc_count'")
                
                # Commit changes
                conn.commit()
                
                # Rebuild FTS index (empty but initialized)
                cursor.execute('INSERT INTO fts_index(fts_index) VALUES("rebuild")')
                
                # Optimize storage after large delete
                self.optimize_storage()
                
                logging.info("Search index cleared successfully")
                return True
                
            except Exception as e:
                # Roll back in case of error
                conn.rollback()
                logging.error(f"Error clearing index: {e}")
                logging.error(traceback.format_exc())
                return False
