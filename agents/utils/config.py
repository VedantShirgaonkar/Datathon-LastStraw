"""
Configuration and Environment Loader
Loads all environment variables and provides typed access to configuration.
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

from agents.utils.logger import get_logger

logger = get_logger(__name__, "CONFIG")


@dataclass
class PostgresConfig:
    """PostgreSQL connection configuration."""
    host: str
    port: int
    database: str
    user: str
    password: str
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""
    uri: str
    username: str
    password: str
    database: str


@dataclass
class ClickHouseConfig:
    """ClickHouse connection configuration."""
    host: str
    port: int
    database: str
    username: str
    password: str


@dataclass
class FeatherlessConfig:
    """Featherless.ai LLM configuration."""
    api_key: str
    base_url: str
    model_primary: str
    model_code: str
    model_fast: str
    model_analytics: str


@dataclass
class OpenAIConfig:
    """OpenAI LLM configuration."""
    api_key: str
    base_url: str
    model: str  # gpt-4o-mini, gpt-4o, etc.


@dataclass
class Config:
    """Main configuration container for all services."""
    postgres: PostgresConfig
    neo4j: Neo4jConfig
    clickhouse: ClickHouseConfig
    featherless: FeatherlessConfig
    openai: OpenAIConfig
    llm_provider: str = "openai"  # "openai" or "featherless"
    debug: bool = False
    log_level: str = "INFO"


def load_config(env_path: Optional[str] = None) -> Config:
    """
    Load configuration from environment variables.
    
    Args:
        env_path: Optional path to .env file. If None, searches parent directories.
    
    Returns:
        Config object with all settings loaded.
    
    Raises:
        ValueError: If required environment variables are missing.
    """
    # Find and load .env file
    if env_path:
        load_dotenv(env_path)
        logger.info(f"Loaded environment from: {env_path}")
    else:
        # Search for .env in current and parent directories
        current_dir = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):  # Search up to 5 levels
            env_file = os.path.join(current_dir, '.env')
            if os.path.exists(env_file):
                load_dotenv(env_file)
                logger.info(f"Loaded environment from: {env_file}")
                break
            parent_dir = os.path.dirname(current_dir)
            if parent_dir == current_dir:
                break
            current_dir = parent_dir
        else:
            # Try the Datathon directory directly
            datathon_env = "/Users/rahul/Desktop/Datathon/.env"
            if os.path.exists(datathon_env):
                load_dotenv(datathon_env)
                logger.info(f"Loaded environment from: {datathon_env}")
    
    # Helper to get required env var
    def get_required(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable '{key}' is not set")
        return value
    
    # Helper to get optional env var with default
    def get_optional(key: str, default: str = "") -> str:
        return os.getenv(key, default)
    
    # Build configuration objects
    try:
        postgres = PostgresConfig(
            host=get_required("POSTGRES_HOST"),
            port=int(get_optional("POSTGRES_PORT", "5432")),
            database=get_required("POSTGRES_DATABASE"),
            user=get_required("POSTGRES_USER"),
            password=get_required("POSTGRES_PASSWORD")
        )
        logger.debug(f"PostgreSQL config loaded: {postgres.host}:{postgres.port}/{postgres.database}")
        
        neo4j = Neo4jConfig(
            uri=get_required("NEO4J_URI"),
            username=get_required("NEO4J_USERNAME"),
            password=get_required("NEO4J_PASSWORD"),
            database=get_optional("NEO4J_DATABASE", "neo4j")
        )
        logger.debug(f"Neo4j config loaded: {neo4j.uri}")
        
        clickhouse = ClickHouseConfig(
            host=get_required("CLICKHOUSE_HOST"),
            port=int(get_optional("CLICKHOUSE_PORT", "8443")),
            database=get_optional("CLICKHOUSE_DATABASE", "default"),
            username=get_optional("CLICKHOUSE_USERNAME", "default"),
            password=get_required("CLICKHOUSE_PASSWORD")
        )
        logger.debug(f"ClickHouse config loaded: {clickhouse.host}:{clickhouse.port}")
        
        featherless = FeatherlessConfig(
            api_key=get_optional("FEATHERLESS_API_KEY", ""),
            base_url=get_optional("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            model_primary=get_optional("FEATHERLESS_MODEL_PRIMARY", "Qwen/Qwen2.5-72B-Instruct"),
            model_code=get_optional("FEATHERLESS_MODEL_CODE", "deepseek-ai/DeepSeek-Coder-V2-Instruct"),
            model_fast=get_optional("FEATHERLESS_MODEL_FAST", "NousResearch/Hermes-3-Llama-3.1-8B"),
            model_analytics=get_optional("FEATHERLESS_MODEL_ANALYTICS", "meta-llama/Llama-3.1-70B-Instruct")
        )
        logger.debug(f"Featherless config loaded: {featherless.base_url}")
        
        openai = OpenAIConfig(
            api_key=get_optional("OPENAI_API_KEY", ""),
            base_url=get_optional("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=get_optional("OPENAI_MODEL", "gpt-4o-mini")
        )
        logger.debug(f"OpenAI config loaded: model={openai.model}")
        
        # Determine LLM provider (default to openai)
        llm_provider = get_optional("LLM_PROVIDER", "openai")
        
        config = Config(
            postgres=postgres,
            neo4j=neo4j,
            clickhouse=clickhouse,
            featherless=featherless,
            openai=openai,
            llm_provider=llm_provider,
            debug=get_optional("DEBUG", "false").lower() == "true",
            log_level=get_optional("LOG_LEVEL", "INFO")
        )
        
        logger.info(f"✓ Configuration loaded successfully (LLM provider: {llm_provider})")
        return config
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise


# Singleton instance - initialized on first import
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the singleton configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
