#!/usr/bin/env python3
"""
Utility to reset crawler database state
"""
import sqlite3
import os
import sys
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def reset_crawler_visits(db_path):
    """Reset crawler_visits table in the database"""
    if not os.path.exists(db_path):
        logging.error(f"Database file not found: {db_path}")
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crawler_visits'")
        if not cursor.fetchone():
            logging.error("crawler_visits table doesn't exist in the database")
            conn.close()
            return False
        
        # Delete all records
        cursor.execute("DELETE FROM crawler_visits")
        conn.commit()
        
        # Get row count
        cursor.execute("SELECT COUNT(*) FROM crawler_visits")
        count = cursor.fetchone()[0]
        
        logging.info(f"Reset crawler_visits table. Now has {count} records (should be 0).")
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error resetting crawler visits: {e}")
        return False

def reset_cache(db_path):
    """Reset cache table in the database"""
    if not os.path.exists(db_path):
        logging.error(f"Database file not found: {db_path}")
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cache'")
        if not cursor.fetchone():
            logging.error("cache table doesn't exist in the database")
            conn.close()
            return False
        
        # Delete all records
        cursor.execute("DELETE FROM cache")
        conn.commit()
        
        # Get row count
        cursor.execute("SELECT COUNT(*) FROM cache")
        count = cursor.fetchone()[0]
        
        logging.info(f"Reset cache table. Now has {count} records (should be 0).")
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error resetting cache: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Reset crawler database state")
    parser.add_argument("--db", default="search_engine.db", help="Database file path")
    parser.add_argument("--all", action="store_true", help="Reset all crawler-related tables")
    parser.add_argument("--visits", action="store_true", help="Reset only crawler_visits table")
    parser.add_argument("--cache", action="store_true", help="Reset only cache table")
    
    args = parser.parse_args()
    
    if not (args.all or args.visits or args.cache):
        parser.print_help()
        print("\nError: Please specify what to reset (--all, --visits, or --cache)")
        return 1
    
    success = True
    
    if args.all or args.visits:
        if not reset_crawler_visits(args.db):
            success = False
    
    if args.all or args.cache:
        if not reset_cache(args.db):
            success = False
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
