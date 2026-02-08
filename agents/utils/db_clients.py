"""
Database Client Connections
Provides singleton connection clients for all databases.
"""

from typing import Optional, Any, List, Dict
import psycopg2
from psycopg2.extras import RealDictCursor
from neo4j import GraphDatabase
import clickhouse_connect

from agents.utils.logger import get_logger, PhaseLogger
from agents.utils.config import get_config, Config

logger = get_logger(__name__, "DB_CLIENTS")


class PostgresClient:
    """PostgreSQL client with connection pooling."""
    
    def __init__(self, config: Config):
        self.config = config.postgres
        self._connection: Optional[psycopg2.extensions.connection] = None
        logger.debug(f"PostgresClient initialized for {self.config.host}")
    
    def _get_connection(self) -> psycopg2.extensions.connection:
        """Get or create a database connection."""
        if self._connection is None or self._connection.closed:
            logger.debug("Creating new PostgreSQL connection...")
            self._connection = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password
            )
            logger.info("✓ PostgreSQL connection established")
        return self._connection
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as list of dicts.
        
        Args:
            query: SQL query string
            params: Optional query parameters
        
        Returns:
            List of row dictionaries
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                logger.debug(f"Executing query: {query[:100]}...")
                cur.execute(query, params)
                results = [dict(row) for row in cur.fetchall()]
                logger.debug(f"Query returned {len(results)} rows")
                return results
        except Exception as e:
            logger.error(f"PostgreSQL query failed: {e}")
            conn.rollback()
            raise
    
    def execute_write(self, query: str, params: tuple = None) -> int:
        """
        Execute an INSERT/UPDATE/DELETE query.
        
        Returns:
            Number of affected rows
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                logger.debug(f"Executing write: {query[:100]}...")
                cur.execute(query, params)
                affected = cur.rowcount
                conn.commit()
                logger.debug(f"Write affected {affected} rows")
                return affected
        except Exception as e:
            logger.error(f"PostgreSQL write failed: {e}")
            conn.rollback()
            raise
    
    def close(self):
        """Close the database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.debug("PostgreSQL connection closed")
    
    def test_connection(self) -> bool:
        """Test if the connection is working."""
        try:
            results = self.execute_query("SELECT 1 as test")
            return len(results) == 1 and results[0]['test'] == 1
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {e}")
            return False


class Neo4jClient:
    """Neo4j client for graph queries."""
    
    def __init__(self, config: Config):
        self.config = config.neo4j
        self._driver = None
        logger.debug(f"Neo4jClient initialized for {self.config.uri}")
    
    def _get_driver(self):
        """Get or create the Neo4j driver."""
        if self._driver is None:
            logger.debug("Creating Neo4j driver...")
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password)
            )
            logger.info("✓ Neo4j driver created")
        return self._driver
    
    def execute_query(self, query: str, params: dict = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            params: Optional query parameters
        
        Returns:
            List of result records as dictionaries
        """
        driver = self._get_driver()
        try:
            with driver.session(database=self.config.database) as session:
                logger.debug(f"Executing Cypher: {query[:100]}...")
                result = session.run(query, params or {})
                records = [dict(record) for record in result]
                logger.debug(f"Cypher returned {len(records)} records")
                return records
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")
            raise
    
    def close(self):
        """Close the Neo4j driver."""
        if self._driver:
            self._driver.close()
            logger.debug("Neo4j driver closed")
    
    def test_connection(self) -> bool:
        """Test if the connection is working."""
        try:
            results = self.execute_query("RETURN 1 as test")
            return len(results) == 1 and results[0]['test'] == 1
        except Exception as e:
            logger.error(f"Neo4j connection test failed: {e}")
            return False


class ClickHouseClient:
    """ClickHouse client for time-series queries."""
    
    def __init__(self, config: Config):
        self.config = config.clickhouse
        self._client = None
        logger.debug(f"ClickHouseClient initialized for {self.config.host}")
    
    def _get_client(self):
        """Get or create the ClickHouse client."""
        if self._client is None:
            logger.debug("Creating ClickHouse client...")
            self._client = clickhouse_connect.get_client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                database=self.config.database,
                secure=True  # Use HTTPS
            )
            logger.info("✓ ClickHouse client created")
        return self._client
    
    def execute_query(self, query: str, params: dict = None) -> List[Dict[str, Any]]:
        """
        Execute a ClickHouse query and return results.
        
        Args:
            query: SQL query string
            params: Optional query parameters
        
        Returns:
            List of result rows as dictionaries
        """
        client = self._get_client()
        try:
            logger.debug(f"Executing ClickHouse query: {query[:100]}...")
            result = client.query(query, parameters=params or {})
            
            # Convert to list of dicts
            columns = result.column_names
            rows = []
            for row in result.result_rows:
                rows.append(dict(zip(columns, row)))
            
            logger.debug(f"ClickHouse returned {len(rows)} rows")
            return rows
        except Exception as e:
            logger.error(f"ClickHouse query failed: {e}")
            raise
    
    def close(self):
        """Close the ClickHouse client."""
        if self._client:
            self._client.close()
            logger.debug("ClickHouse client closed")
    
    def test_connection(self) -> bool:
        """Test if the connection is working."""
        try:
            results = self.execute_query("SELECT 1 as test")
            return len(results) == 1 and results[0]['test'] == 1
        except Exception as e:
            logger.error(f"ClickHouse connection test failed: {e}")
            return False


# Singleton clients
_postgres_client: Optional[PostgresClient] = None
_neo4j_client: Optional[Neo4jClient] = None
_clickhouse_client: Optional[ClickHouseClient] = None


def get_postgres_client() -> PostgresClient:
    """Get the singleton PostgreSQL client."""
    global _postgres_client
    if _postgres_client is None:
        _postgres_client = PostgresClient(get_config())
    return _postgres_client


def get_neo4j_client() -> Neo4jClient:
    """Get the singleton Neo4j client."""
    global _neo4j_client
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient(get_config())
    return _neo4j_client


def get_clickhouse_client() -> ClickHouseClient:
    """Get the singleton ClickHouse client."""
    global _clickhouse_client
    if _clickhouse_client is None:
        _clickhouse_client = ClickHouseClient(get_config())
    return _clickhouse_client


def test_all_connections() -> Dict[str, bool]:
    """
    Test connections to all databases.
    
    Returns:
        Dictionary mapping database name to connection status
    """
    logger.info("Testing all database connections...")
    
    results = {}
    
    with PhaseLogger(logger, "PostgreSQL Connection Test"):
        results['postgres'] = get_postgres_client().test_connection()
    
    with PhaseLogger(logger, "Neo4j Connection Test"):
        results['neo4j'] = get_neo4j_client().test_connection()
    
    with PhaseLogger(logger, "ClickHouse Connection Test"):
        results['clickhouse'] = get_clickhouse_client().test_connection()
    
    # Summary
    all_passed = all(results.values())
    if all_passed:
        logger.info("✓ All database connections successful")
    else:
        failed = [k for k, v in results.items() if not v]
        logger.error(f"✗ Connection failures: {failed}")
    
    return results


def diagnose_tools() -> Dict[str, Any]:
    """
    Test tool execution directly.
    """
    diagnostics = {}
    
    # Test Postgres Tool: list_developers
    try:
        from agents.tools.postgres_tools import list_developers
        # Manually invoke the tool function (bypassing LangChain wrapper if possible, or using it directly)
        # The @tool decorator makes it a StructuredTool. We can call .invoke or .func
        
        # Try calling the underlying function if available, or invoke
        if hasattr(list_developers, 'func'):
            result = list_developers.func(limit=1)
        else:
            result = list_developers.invoke({"limit": 1})
            
        diagnostics['list_developers'] = {"status": "ok", "result": str(result)[:100]}
    except Exception as e:
        diagnostics['list_developers'] = {"status": "error", "error": str(e)}

    return diagnostics

def diagnose_schema() -> Dict[str, Any]:
    """
    Inspect the actual schema of the connected database.
    """
    diagnostics = {}
    
    try:
        pg = get_postgres_client()
        # Query to list columns for 'employees' table
        query = """
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'employees'
            ORDER BY ordinal_position;
        """
        results = pg.execute_query(query)
        diagnostics['employees_table_columns'] = [dict(r) for r in results]
        
        # Also check current database name to ensure we are in the right DB
        db_name = pg.execute_query("SELECT current_database();")[0]['current_database']
        diagnostics['connected_database'] = db_name
        
    except Exception as e:
        diagnostics['error'] = str(e)

    return diagnostics

def diagnose_clickhouse() -> Dict[str, Any]:
    """
    Inspect the ClickHouse database: list tables and count rows.
    """
    diagnostics = {}
    try:
        ch = get_clickhouse_client()
        
        # Check tables
        tables = ch.execute_query("SHOW TABLES")
        diagnostics['tables'] = [t['name'] for t in tables]
        
        # Count rows in key tables
        counts = {}
        for t in diagnostics['tables']:
            if t in ['events', 'dora_daily_metrics']:
                try:
                    c = ch.execute_query(f"SELECT count() as c FROM {t}")
                    counts[t] = c[0]['c']
                except Exception as e:
                    counts[t] = f"Error: {str(e)}"
        
        diagnostics['row_counts'] = counts
        
    except Exception as e:
        diagnostics['error'] = str(e)
        
    return diagnostics

def diagnose_connections() -> Dict[str, Dict[str, Any]]:
    """
    Test connections and return detailed diagnostics including error messages.
    """
    diagnostics = {}
    
    # Postgres
    try:
        get_postgres_client().execute_query("SELECT 1")
        diagnostics['postgres'] = {"status": "ok", "error": None}
    except Exception as e:
        diagnostics['postgres'] = {"status": "error", "error": str(e)}

    # Neo4j
    try:
        get_neo4j_client().execute_query("RETURN 1")
        diagnostics['neo4j'] = {"status": "ok", "error": None}
    except Exception as e:
        diagnostics['neo4j'] = {"status": "error", "error": str(e)}

    # ClickHouse
    try:
        get_clickhouse_client().execute_query("SELECT 1")
        diagnostics['clickhouse'] = {"status": "ok", "error": None}
    except Exception as e:
        diagnostics['clickhouse'] = {"status": "error", "error": str(e)}

    return diagnostics

def close_all_connections():
    """Close all database connections."""
    global _postgres_client, _neo4j_client, _clickhouse_client
    
    if _postgres_client:
        _postgres_client.close()
        _postgres_client = None
    
    if _neo4j_client:
        _neo4j_client.close()
        _neo4j_client = None
    
    if _clickhouse_client:
        _clickhouse_client.close()
        _clickhouse_client = None
    
    logger.info("All database connections closed")
