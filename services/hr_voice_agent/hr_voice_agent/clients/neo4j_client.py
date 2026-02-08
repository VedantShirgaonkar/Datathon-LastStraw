from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase


@dataclass
class Neo4jClient:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    def __post_init__(self) -> None:
        self._driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))

    def close(self) -> None:
        if self._driver:
            self._driver.close()

    def get_person_graph_context(self, *, email: Optional[str], user_id: Optional[str]) -> Dict[str, Any]:
        """Return lightweight relationship context used for personalization."""
        # We support matching either by email or by id (stored in :User.id).
        params: Dict[str, Any] = {"email": email, "id": user_id}

        cypher = """
        MATCH (u:User)
        WHERE ($email IS NOT NULL AND toLower(u.email) = toLower($email))
           OR ($id IS NOT NULL AND u.id = $id)
        OPTIONAL MATCH (u)-[:BELONGS_TO]->(t:Team)
        OPTIONAL MATCH (u)-[c:CONTRIBUTES_TO]->(p:Project)
        OPTIONAL MATCH (u)-[hs:HAS_SKILL]->(s:Skill)
        RETURN
            u { .id, .email, .name, .team } as user,
            collect(DISTINCT t { .id, .name }) as teams,
            collect(DISTINCT p { .id, .name, .jira_key, .github_repo, .status }) as projects,
            collect(DISTINCT {name: s.name, level: hs.level}) as skills,
            collect(DISTINCT {project: p.name, commits: c.commits, prs: c.prs}) as contributions
        LIMIT 1
        """

        with self._driver.session(database=self.database) as session:
            rec = session.run(cypher, **params).single()
            if not rec:
                return {}
            return {
                "user": rec.get("user"),
                "teams": rec.get("teams") or [],
                "projects": rec.get("projects") or [],
                "skills": rec.get("skills") or [],
                "contributions": rec.get("contributions") or [],
            }
