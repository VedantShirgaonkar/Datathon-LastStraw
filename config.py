"""
Configuration management for database connections.
Loads environment variables and provides typed configuration objects.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


@dataclass
class Neo4jConfig:
    """Neo4j Aura connection configuration"""
    uri: str
    username: str
    password: str
    database: str = "neo4j"
    
    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Load Neo4j config from environment variables"""
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "neo4j")
        
        if not all([uri, username, password]):
            raise ValueError(
                "Missing Neo4j credentials. Please set NEO4J_URI, "
                "NEO4J_USERNAME, and NEO4J_PASSWORD in .env file"
            )
        
        return cls(
            uri=uri,
            username=username,
            password=password,
            database=database
        )


@dataclass
class PostgresConfig:
    """Aurora PostgreSQL connection configuration"""
    host: str
    port: int
    database: str
    username: str
    password: str
    
    @classmethod
    def from_env(cls) -> "PostgresConfig":
        """Load PostgreSQL config from environment variables"""
        host = os.getenv("POSTGRES_HOST")
        port = int(os.getenv("POSTGRES_PORT", "5432"))
        database = os.getenv("POSTGRES_DATABASE")
        username = os.getenv("POSTGRES_USERNAME")
        password = os.getenv("POSTGRES_PASSWORD")
        
        if not all([host, database, username, password]):
            raise ValueError(
                "Missing PostgreSQL credentials. Please set POSTGRES_* "
                "variables in .env file"
            )
        
        return cls(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password
        )


@dataclass
class ClickHouseConfig:
    """ClickHouse Cloud connection configuration"""
    host: str
    port: int
    database: str
    username: str
    password: str
    
    @classmethod
    def from_env(cls) -> "ClickHouseConfig":
        """Load ClickHouse config from environment variables"""
        host = os.getenv("CLICKHOUSE_HOST")
        port = int(os.getenv("CLICKHOUSE_PORT", "8443"))
        database = os.getenv("CLICKHOUSE_DATABASE")
        username = os.getenv("CLICKHOUSE_USERNAME")
        password = os.getenv("CLICKHOUSE_PASSWORD")
        
        if not all([host, database, username, password]):
            raise ValueError(
                "Missing ClickHouse credentials. Please set CLICKHOUSE_* "
                "variables in .env file"
            )
        
        return cls(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password
        )


@dataclass
class PineconeConfig:
    """Pinecone vector database configuration"""
    api_key: str
    environment: str
    
    @classmethod
    def from_env(cls) -> "PineconeConfig":
        """Load Pinecone config from environment variables"""
        api_key = os.getenv("PINECONE_API_KEY")
        environment = os.getenv("PINECONE_ENVIRONMENT")
        
        if not all([api_key, environment]):
            raise ValueError(
                "Missing Pinecone credentials. Please set PINECONE_API_KEY "
                "and PINECONE_ENVIRONMENT in .env file"
            )
        
        return cls(
            api_key=api_key,
            environment=environment
        )


class DatabaseConfig:
    """Central configuration for all databases"""
    
    def __init__(self):
        self._neo4j: Optional[Neo4jConfig] = None
        self._postgres: Optional[PostgresConfig] = None
        self._clickhouse: Optional[ClickHouseConfig] = None
        self._pinecone: Optional[PineconeConfig] = None
    
    @property
    def neo4j(self) -> Neo4jConfig:
        """Get Neo4j configuration (lazy load)"""
        if self._neo4j is None:
            self._neo4j = Neo4jConfig.from_env()
        return self._neo4j
    
    @property
    def postgres(self) -> PostgresConfig:
        """Get PostgreSQL configuration (lazy load)"""
        if self._postgres is None:
            self._postgres = PostgresConfig.from_env()
        return self._postgres
    
    @property
    def clickhouse(self) -> ClickHouseConfig:
        """Get ClickHouse configuration (lazy load)"""
        if self._clickhouse is None:
            self._clickhouse = ClickHouseConfig.from_env()
        return self._clickhouse
    
    @property
    def pinecone(self) -> PineconeConfig:
        """Get Pinecone configuration (lazy load)"""
        if self._pinecone is None:
            self._pinecone = PineconeConfig.from_env()
        return self._pinecone


# Global configuration instance
config = DatabaseConfig()
