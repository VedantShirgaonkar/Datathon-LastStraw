"""
Neo4j client for managing graph database connections and operations.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver, Session, Result
from neo4j.exceptions import ServiceUnavailable, AuthError

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


class Neo4jClient:
    """
    Neo4j Aura client with connection pooling and error handling.
    
    Usage:
        client = Neo4jClient()
        
        # Execute a query
        result = client.execute_query(
            "MATCH (d:Developer {email: $email}) RETURN d",
            {"email": "john@example.com"}
        )
        
        # Use context manager for transactions
        with client.session() as session:
            session.run("CREATE (d:Developer {name: $name})", {"name": "Jane"})
    """
    
    def __init__(self):
        """Initialize Neo4j client with configuration from environment"""
        self._driver: Optional[Driver] = None
        self._config = config.neo4j
    
    @property
    def driver(self) -> Driver:
        """Get or create Neo4j driver (lazy initialization)"""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self._config.uri,
                    auth=(self._config.username, self._config.password),
                    max_connection_lifetime=3600,  # 1 hour
                    max_connection_pool_size=50,
                    connection_acquisition_timeout=60.0
                )
                # Test connection
                self._driver.verify_connectivity()
            except AuthError as e:
                raise ValueError(
                    f"Neo4j authentication failed. Check credentials in .env file: {e}"
                )
            except ServiceUnavailable as e:
                raise ConnectionError(
                    f"Cannot connect to Neo4j. Is the instance running? {e}"
                )
        
        return self._driver
    
    def close(self):
        """Close the Neo4j driver and release connections"""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
    
    @contextmanager
    def session(self, database: Optional[str] = None) -> Session:
        """
        Context manager for Neo4j sessions.
        
        Args:
            database: Database name (defaults to config database)
        
        Yields:
            Neo4j session
        """
        db = database or self._config.database
        session = self.driver.session(database=db)
        try:
            yield session
        finally:
            session.close()
    
    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results as list of dictionaries.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Database name (optional)
        
        Returns:
            List of result records as dictionaries
        """
        with self.session(database=database) as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]
    
    def execute_write(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a write query in a transaction.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Database name (optional)
        
        Returns:
            List of result records as dictionaries
        """
        def _execute(tx):
            result = tx.run(query, parameters or {})
            return [dict(record) for record in result]
        
        with self.session(database=database) as session:
            return session.execute_write(_execute)
    
    def execute_read(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a read query in a transaction.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            database: Database name (optional)
        
        Returns:
            List of result records as dictionaries
        """
        def _execute(tx):
            result = tx.run(query, parameters or {})
            return [dict(record) for record in result]
        
        with self.session(database=database) as session:
            return session.execute_read(_execute)
    
    def verify_connection(self) -> Dict[str, Any]:
        """
        Verify connection to Neo4j and return database info.
        
        Returns:
            Dictionary with connection status and database info
        """
        try:
            result = self.execute_query("CALL dbms.components() YIELD name, versions, edition")
            
            if result:
                component = result[0]
                return {
                    "connected": True,
                    "name": component.get("name"),
                    "version": component.get("versions", ["unknown"])[0],
                    "edition": component.get("edition"),
                    "uri": self._config.uri,
                    "database": self._config.database
                }
            
            return {"connected": True, "uri": self._config.uri}
            
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }
    
    def count_nodes(self, label: Optional[str] = None) -> int:
        """
        Count total nodes or nodes with specific label.
        
        Args:
            label: Optional node label to filter by
        
        Returns:
            Number of nodes
        """
        if label:
            query = f"MATCH (n:{label}) RETURN count(n) as count"
        else:
            query = "MATCH (n) RETURN count(n) as count"
        
        result = self.execute_query(query)
        return result[0]["count"] if result else 0
    
    def count_relationships(self, rel_type: Optional[str] = None) -> int:
        """
        Count total relationships or relationships of specific type.
        
        Args:
            rel_type: Optional relationship type to filter by
        
        Returns:
            Number of relationships
        """
        if rel_type:
            query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count"
        else:
            query = "MATCH ()-[r]->() RETURN count(r) as count"
        
        result = self.execute_query(query)
        return result[0]["count"] if result else 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive database statistics.
        
        Returns:
            Dictionary with node counts, relationship counts, labels, etc.
        """
        # Get all labels
        labels_result = self.execute_query("CALL db.labels()")
        labels = [record["label"] for record in labels_result]
        
        # Get all relationship types
        rel_types_result = self.execute_query("CALL db.relationshipTypes()")
        rel_types = [record["relationshipType"] for record in rel_types_result]
        
        # Count nodes per label
        node_counts = {}
        for label in labels:
            node_counts[label] = self.count_nodes(label)
        
        # Count relationships per type
        rel_counts = {}
        for rel_type in rel_types:
            rel_counts[rel_type] = self.count_relationships(rel_type)
        
        return {
            "total_nodes": self.count_nodes(),
            "total_relationships": self.count_relationships(),
            "labels": labels,
            "relationship_types": rel_types,
            "node_counts": node_counts,
            "relationship_counts": rel_counts
        }
    
    def clear_database(self) -> int:
        """
        Delete all nodes and relationships (USE WITH CAUTION!)
        
        Returns:
            Number of nodes deleted
        """
        result = self.execute_write(
            "MATCH (n) DETACH DELETE n RETURN count(n) as deleted"
        )
        return result[0]["deleted"] if result else 0
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    def __del__(self):
        """Destructor to ensure driver is closed"""
        self.close()
