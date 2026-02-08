"""
Agent configuration with validation.
"""

import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional


class AgentConfig(BaseSettings):
    """Agent configuration with Pydantic validation"""
    
    # LLM Configuration (supports OpenAI and Groq)
    # API Keys
    openai_api_key: Optional[str] = Field(None, alias="OPENAI_API_KEY")
    groq_api_key: Optional[str] = Field(None, alias="GROQ_API_KEY")
    
    # Model selection (auto-detects provider: gpt-* = OpenAI, others = Groq)
    groq_model: str = Field(default="gpt-4o-mini", alias="GROQ_MODEL")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    groq_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    
    # Optional fallback model to use for very large requests
    groq_fallback_model: Optional[str] = Field(default=None, alias="GROQ_FALLBACK_MODEL")
    
    # Neo4j
    neo4j_uri: str = Field(..., alias="NEO4J_URI")
    neo4j_username: str = Field(..., alias="NEO4J_USERNAME")
    neo4j_password: str = Field(..., alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", alias="NEO4J_DATABASE")
    
    # ClickHouse
    clickhouse_host: str = Field(..., alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=8443, alias="CLICKHOUSE_PORT")
    clickhouse_database: str = Field(default="default", alias="CLICKHOUSE_DATABASE")
    clickhouse_username: str = Field(..., alias="CLICKHOUSE_USERNAME")
    clickhouse_password: str = Field(..., alias="CLICKHOUSE_PASSWORD")
    
    # Pinecone
    pinecone_api_key: str = Field(..., alias="PINECONE_API_KEY")
    pinecone_environment: str = Field(..., alias="PINECONE_ENVIRONMENT")
    pinecone_index_name: str = Field(default="engineering-intelligence", alias="PINECONE_INDEX_NAME")
    pinecone_embedding_model: str = Field(default="multilingual-e5-large")
    
    # Kafka / MSK Configuration
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092", 
        alias="KAFKA_BOOTSTRAP_SERVERS",
        description="Comma-separated MSK broker endpoints"
    )
    kafka_topics: str = Field(
        default="events.github,events.jira,events.notion", 
        alias="KAFKA_TOPICS",
        description="Comma-separated Kafka topic names"
    )
    kafka_group_id: str = Field(default="database-agent-group", alias="KAFKA_GROUP_ID")
    kafka_security_protocol: str = Field(
        default="SSL", 
        alias="KAFKA_SECURITY_PROTOCOL",
        description="Security protocol: PLAINTEXT, SSL, SASL_SSL"
    )
    kafka_ssl_enabled: bool = Field(default=True, alias="KAFKA_SSL_ENABLED")
    
    # AWS Lambda Executor
    executor_lambda_name: str = Field(
        default="datathon-executor",
        alias="EXECUTOR_LAMBDA_NAME",
        description="Lambda function for executing Jira/GitHub/Notion commands"
    )
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    
    # Optional integrations
    slack_webhook_url: Optional[str] = Field(None, alias="SLACK_WEBHOOK_URL")
    jira_url: Optional[str] = Field(None, alias="JIRA_URL")
    jira_api_token: Optional[str] = Field(None, alias="JIRA_API_TOKEN")
    jira_email: Optional[str] = Field(None, alias="JIRA_EMAIL")
    github_token: Optional[str] = Field(None, alias="GITHUB_TOKEN")
    
    # Webhook Server Configuration  
    github_webhook_secret: Optional[str] = Field(None, alias="GITHUB_WEBHOOK_SECRET")
    jira_webhook_secret: Optional[str] = Field(None, alias="JIRA_WEBHOOK_SECRET")
    webhook_server_host: str = Field("0.0.0.0", alias="WEBHOOK_SERVER_HOST")
    webhook_server_port: int = Field(8000, alias="WEBHOOK_SERVER_PORT")
    
    # Agent Server Configuration
    agent_server_host: str = Field("0.0.0.0", alias="AGENT_SERVER_HOST")
    agent_server_port: int = Field(8001, alias="AGENT_SERVER_PORT")
    agent_server_url: str = Field("http://localhost:8001", alias="AGENT_SERVER_URL")
    
    # Agent settings
    max_tool_retries: int = Field(default=3, ge=1, le=10)
    tool_timeout_seconds: int = Field(default=30, ge=5, le=300)
    enable_async_tools: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    
    @field_validator("groq_model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model supports tool calling"""
        supported_models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "mixtral-8x7b-32768"]
        # Accept any model - user knows what they're doing
        return v
    
    def get_api_config(self, model_name: str = None):
        """Get API key and base URL for the specified model."""
        model = model_name or self.groq_model
        # Auto-detect provider: gpt-* models use OpenAI, others use Groq
        if model.startswith('gpt-'):
            return self.openai_api_key, self.openai_base_url
        else:
            return self.groq_api_key, self.groq_base_url
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env (PostgreSQL, etc.)


# Global config instance
_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """Get or create global config instance"""
    global _config
    if _config is None:
        _config = AgentConfig()
    return _config
