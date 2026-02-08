# PR Merge Agent Service

Independent service that:

1. Detects PRs that are not yet merged (from ClickHouse events and/or GitHub).
2. Checks mergeability (no merge conflicts).
3. **Dynamically looks up team leads/managers** from Neo4j based on project ownership.
4. Emails the appropriate Tech Lead/Manager with:
   - Summary of code changes
   - A signed, clickable "Merge PR" link
5. If PR has conflicts (or is not mergeable), sends an email asking to check.
6. When a PR is merged via the link, inserts a `pr_merged` event into ClickHouse.

## Quick start

```bash
cd services/pr_merge_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run the HTTP service (handles merge links)
uvicorn pr_merge_agent.app:app --host 0.0.0.0 --port 8080 --reload

# In another terminal, run the poller once
python -m pr_merge_agent.runner
```

## Env vars

See `.env.example`.

### Dynamic Email Recipients (Neo4j)

The agent queries Neo4j to find the right people to email based on your org structure:

```cypher
// Given a GitHub repo, find the owning team's leads/managers
MATCH (p:Project {github_repo: $repo})<-[:OWNS]-(t:Team)<-[:BELONGS_TO]-(u:User)
WHERE u.role IN ['tech_lead', 'manager', 'lead', 'engineering_manager']
RETURN u.email
```

**Required Neo4j schema:**
```
(:User {id, email, name, role, team})
(:Team {id, name})
(:Project {id, name, github_repo})

(:User)-[:BELONGS_TO]->(:Team)
(:Team)-[:OWNS]->(:Project)
```

If Neo4j is not configured or returns no results, it falls back to `LEAD_EMAILS` from `.env`.

### Optional: AI summaries (Groq)

If you set `GROQ_API_KEY`, the email summary will be generated via Groq's LLM API (using Llama 3.3 70B by default).
If not set, the service uses a deterministic heuristic summary.

## ClickHouse schema

This service expects an events table with columns matching the screenshot:
`event_id, timestamp, source, event_type, project_id, actor_id, entity_id, entity_type, metadata`.

DDL example is in `clickhouse_schema.sql`.
