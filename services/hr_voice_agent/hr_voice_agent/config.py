from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


# Ensure values from `.env` are also available via `os.getenv(...)`.
# When running via `uvicorn --app-dir services/hr_voice_agent ...` from repo root,
# the CWD is the repo root, but the service's .env lives in services/hr_voice_agent/.env.
# This file is: services/hr_voice_agent/hr_voice_agent/config.py
# parents[0] -> services/hr_voice_agent/hr_voice_agent
# parents[1] -> services/hr_voice_agent
_SERVICE_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"  # services/hr_voice_agent/.env
load_dotenv(dotenv_path=_SERVICE_ENV_PATH, override=False)
load_dotenv(override=False)  # also load CWD .env if present


class Settings(BaseSettings):
    # LLM (question generation)
    llm_provider: str = Field(
        default="openai",
        description="LLM provider: openai | groq",
    )

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4.1-mini")

    # Groq (OpenAI-compatible Chat Completions)
    groq_api_key: str = Field(default="")
    groq_model: str = Field(default="llama-3.1-8b-instant")

    # Embeddings (for Pinecone query embedding)
    # Providers:
    # - openai: uses OpenAI embeddings API (requires OPENAI_API_KEY)
    # - postgres: derives a query vector from existing pgvector rows in Postgres `embeddings`
    # - none: disables semantic retrieval
    embedding_provider: str = Field(default="openai", description="Embeddings provider: openai | postgres | none")
    openai_embedding_model: str = Field(default="text-embedding-3-small")

    # Postgres
    postgres_dsn: str = Field(default="", description="e.g. postgresql://user:pass@host:5432/db")

    # Neo4j
    neo4j_uri: str = Field(default="")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")
    neo4j_database: str = Field(default="neo4j")

    # Pinecone
    pinecone_api_key: str = Field(default="")
    pinecone_index: str = Field(default="engineering-intelligence")
    pinecone_namespace_developer_profiles: str = Field(default="developer_profiles")
    pinecone_namespace_project_docs: str = Field(default="project_docs")

    # Behavior
    default_top_k: int = Field(default=8)
    max_questions: int = Field(default=8)

    # TTS
    tts_backend: str = Field(
        default="macos_say",
        description="TTS backend: macos_say | piper | none",
    )
    piper_binary: str = Field(default="piper", description="Path to piper binary")
    piper_model_path: str = Field(default="", description="Path to a Piper .onnx voice model")
    piper_speaker_id: int = Field(default=0)

    class Config:
        env_file = str(_SERVICE_ENV_PATH)
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def postgres_enabled(self) -> bool:
        return bool(self.postgres_dsn)

    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    def pinecone_enabled(self) -> bool:
        return bool(self.pinecone_api_key and self.pinecone_index)

    def llm_enabled(self) -> bool:
        provider = (self.llm_provider or "").strip().lower()
        if provider == "groq":
            return bool(self.groq_api_key)
        return bool(self.openai_api_key)

    def embeddings_enabled(self) -> bool:
        provider = (self.embedding_provider or "").strip().lower()
        if provider in {"", "none", "off", "false", "0"}:
            return False
        if provider == "postgres":
            return bool(self.postgres_dsn)
        # default: openai
        return bool(self.openai_api_key)

    def tts_enabled(self) -> bool:
        return (self.tts_backend or "").lower() not in {"", "none", "off", "false", "0"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
