from __future__ import annotations

from typing import List, Optional

from neo4j import GraphDatabase


class Neo4jClient:
    """Client to query Neo4j for team/project ownership and user roles."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
    ):
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_leads_for_repo(self, github_repo: str, roles: Optional[List[str]] = None) -> List[str]:
        """
        Find team leads/managers for a GitHub repo.

        Traverses:
          (:Project {github_repo})<-[:OWNS]-(:Team)<-[:BELONGS_TO]-(:User)

        If roles is provided, filters users by role (e.g. ["tech_lead", "manager"]).
        Returns list of email addresses.
        """
        if roles is None:
            roles = ["tech_lead", "manager", "lead", "engineering_manager"]

        query = """
        MATCH (p:Project {github_repo: $github_repo})<-[:OWNS]-(t:Team)<-[:BELONGS_TO]-(u:User)
        WHERE u.role IN $roles
        RETURN DISTINCT u.email AS email
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, github_repo=github_repo, roles=roles)
            return [record["email"] for record in result if record["email"]]

    def get_leads_for_project_id(self, project_id: str, roles: Optional[List[str]] = None) -> List[str]:
        """
        Find team leads/managers for a project by its id.

        Traverses:
          (:Project {id})<-[:OWNS]-(:Team)<-[:BELONGS_TO]-(:User)
        """
        if roles is None:
            roles = ["tech_lead", "manager", "lead", "engineering_manager"]

        query = """
        MATCH (p:Project {id: $project_id})<-[:OWNS]-(t:Team)<-[:BELONGS_TO]-(u:User)
        WHERE u.role IN $roles
        RETURN DISTINCT u.email AS email
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, project_id=project_id, roles=roles)
            return [record["email"] for record in result if record["email"]]

    def get_contributors_for_repo(self, github_repo: str) -> List[str]:
        """
        Get all contributors to a repo (optional, for CC or info).
        """
        query = """
        MATCH (p:Project {github_repo: $github_repo})<-[:CONTRIBUTES_TO]-(u:User)
        RETURN DISTINCT u.email AS email
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, github_repo=github_repo)
            return [record["email"] for record in result if record["email"]]

    def get_team_for_repo(self, github_repo: str) -> Optional[str]:
        """
        Get the team name that owns a repo.
        """
        query = """
        MATCH (p:Project {github_repo: $github_repo})<-[:OWNS]-(t:Team)
        RETURN t.name AS team_name LIMIT 1
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, github_repo=github_repo)
            record = result.single()
            return record["team_name"] if record else None
