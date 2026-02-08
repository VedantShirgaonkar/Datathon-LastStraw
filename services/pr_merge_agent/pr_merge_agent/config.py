from __future__ import annotations

from functools import lru_cache
import json
from typing import List

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


# Ensure values from `.env` are also available via `os.getenv(...)`.
# Pydantic's `env_file` is used for Settings, but it does not populate `os.environ`.
load_dotenv(override=False)


class Settings(BaseSettings):
    clickhouse_host: str = Field(default="localhost")
    clickhouse_port: int = Field(default=8123)
    clickhouse_secure: bool = Field(default=False)
    clickhouse_username: str = Field(default="default")
    clickhouse_password: str = Field(default="")
    clickhouse_database: str = Field(default="default")
    clickhouse_events_table: str = Field(default="events")

    github_token: str = Field(default="")
    github_repos: str = Field(default="", description="Comma-separated owner/repo list")
    github_merge_method: str = Field(default="squash", description="merge|squash|rebase")
    github_project_id_map: str = Field(
        default="",
        description="Optional JSON map of repo -> project_id (e.g. {\"owner/repo\":\"proj-api\"})",
    )

    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)
    email_from: str = Field(default="pr-merge-agent@company.com")
    lead_emails: str = Field(default="", description="Comma-separated list")

    pr_merge_agent_signing_secret: str = Field(default="")
    pr_merge_agent_base_url: str = Field(default="http://localhost:8080")

    email_dedupe_minutes: int = Field(default=240)

    clickhouse_pr_open_event_types: str = Field(
        default="pull_request_opened,pr_opened,pr_created",
        description="Comma-separated event types that mean PR opened",
    )
    clickhouse_pr_merged_event_type: str = Field(default="pr_merged")

    # Neo4j settings for dynamic email recipient lookup
    neo4j_uri: str = Field(default="", description="Neo4j connection URI (e.g. neo4j+s://xxx.databases.neo4j.io)")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")
    neo4j_database: str = Field(default="neo4j")
    neo4j_lead_roles: str = Field(
        default="tech_lead,manager,lead,engineering_manager",
        description="Comma-separated list of user roles considered as leads",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def repos_list(self) -> List[str]:
        return [r.strip() for r in self.github_repos.split(",") if r.strip()]

    def lead_emails_list(self) -> List[str]:
        return [e.strip() for e in self.lead_emails.split(",") if e.strip()]

    def pr_open_event_types_list(self) -> List[str]:
        return [t.strip() for t in self.clickhouse_pr_open_event_types.split(",") if t.strip()]

    def project_id_for_repo(self, repo: str) -> str:
        raw = (self.github_project_id_map or "").strip()
        if not raw:
            return repo
        try:
            mapping = json.loads(raw)
        except Exception:
            return repo
        if not isinstance(mapping, dict):
            return repo
        return str(mapping.get(repo) or repo)

    def lead_roles_list(self) -> List[str]:
        return [r.strip() for r in self.neo4j_lead_roles.split(",") if r.strip()]

    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
