"""
PostgreSQL + pgvector client for entity storage and vector operations.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from typing import List, Dict, Any, Optional
import json

from config import DatabaseConfig


class PostgresClient:
    """
    PostgreSQL client with pgvector support.
    """
    
    def __init__(self):
        """Initialize PostgreSQL connection"""
        config = DatabaseConfig().postgres
        
        self.connection_params = {
            'host': config.host,
            'port': config.port,
            'database': config.database,
            'user': config.username,
            'password': config.password,
            'connect_timeout': 10
        }
        
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(**self.connection_params)
            self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
    
    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
        
        Returns:
            List of dictionaries (rows)
        """
        self.connect()
        self.cursor.execute(query, params)
        results = self.cursor.fetchall()
        return [dict(row) for row in results]
    
    def execute_write(self, query: str, params: tuple = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
        
        Returns:
            Number of affected rows
        """
        self.connect()
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor.rowcount
    
    def execute_write_returning(self, query: str, params: tuple = None) -> List[Dict]:
        """
        Execute an INSERT/UPDATE/DELETE query with RETURNING clause.
        
        Args:
            query: SQL query string with RETURNING clause
            params: Query parameters (optional)
        
        Returns:
            List of dictionaries (returned rows)
        """
        self.connect()
        self.cursor.execute(query, params)
        results = self.cursor.fetchall()
        self.conn.commit()
        return [dict(row) for row in results]
    
    def get_server_version(self) -> str:
        """Get PostgreSQL server version"""
        self.connect()
        self.cursor.execute("SELECT version();")
        result = self.cursor.fetchone()
        return result['version']
    
    def verify_connection(self) -> bool:
        """Verify database connection is working"""
        try:
            self.connect()
            self.cursor.execute("SELECT 1;")
            result = self.cursor.fetchone()
            return result is not None
        except Exception as e:
            print(f"Connection verification failed: {e}")
            return False
    
    def check_pgvector_extension(self) -> bool:
        """Check if pgvector extension is installed"""
        try:
            self.connect()
            self.cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM pg_extension WHERE extname = 'vector'
                );
            """)
            result = self.cursor.fetchone()
            return result['exists']
        except Exception as e:
            print(f"Error checking pgvector: {e}")
            return False
    
    def list_tables(self) -> List[str]:
        """List all tables in the database"""
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """
        results = self.execute_query(query)
        return [row['table_name'] for row in results]
    
    def get_table_schema(self, table_name: str) -> List[Dict]:
        """
        Get schema information for a table.
        
        Args:
            table_name: Name of the table
        
        Returns:
            List of column information dictionaries
        """
        query = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' 
                AND table_name = %s
            ORDER BY ordinal_position;
        """
        return self.execute_query(query, (table_name,))
    
    def get_table_row_count(self, table_name: str) -> int:
        """Get row count for a table"""
        query = f"SELECT COUNT(*) as count FROM {table_name};"
        result = self.execute_query(query)
        return result[0]['count'] if result else 0
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
