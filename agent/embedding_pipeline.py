"""
Embedding Pipeline for Kafka Events

Automatically generates embeddings from incoming events for semantic search.
This enables queries like:
- "Find developers who worked on authentication features"
- "What PRs are related to database optimization?"
- "Who has experience with similar issues?"
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from postgres.embedding_service import embed_text
from agent.tools.postgres_tools import upsert_embedding

logger = logging.getLogger(__name__)


# ==============================================================================
# EMBEDDING TYPES
# ==============================================================================

class EmbeddingType:
    """Standard embedding types for different content"""
    DEVELOPER_PROFILE = "developer_profile"      # Aggregated developer skills/activity
    DEVELOPER_ACTIVITY = "developer_activity"    # Individual commits/PRs/reviews
    ISSUE_DESCRIPTION = "issue_description"      # Jira/GitHub issues
    DOCUMENTATION = "documentation"              # Notion pages, READMEs
    CODE_CHANGE = "code_change"                  # Commit diffs, code snippets
    PROJECT_DESCRIPTION = "project_description"  # Project overviews


# ==============================================================================
# TEXT EXTRACTION FROM EVENTS
# ==============================================================================

def extract_embeddable_text_github(event_type: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract text content from GitHub events for embedding.
    
    Returns list of dicts with: text, embedding_type, source_id, source_table, title, metadata
    """
    embeddings_to_create = []
    
    if event_type == "push":
        # Embed each commit message
        commits = raw.get("commits", [])
        repo = raw.get("repository", {})
        
        for commit in commits:
            commit_id = commit.get("id", "")
            message = commit.get("message", "")
            author = commit.get("author", {})
            
            if message and len(message) > 20:  # Only embed meaningful messages
                text = f"""
Commit in {repo.get('full_name', 'unknown')}: {message}
Author: {author.get('name', 'unknown')}
""".strip()
                
                embeddings_to_create.append({
                    "text": text,
                    "embedding_type": EmbeddingType.DEVELOPER_ACTIVITY,
                    "source_id": commit_id[:36] if len(commit_id) >= 36 else commit_id.ljust(36, '0'),
                    "source_table": "github_commits",
                    "title": f"Commit: {message[:50]}...",
                    "metadata": {
                        "repo": repo.get("full_name"),
                        "author_email": author.get("email"),
                        "author_name": author.get("name"),
                        "timestamp": commit.get("timestamp")
                    }
                })
    
    elif event_type == "pull_request":
        pr = raw.get("pull_request", {})
        action = raw.get("action", "")
        
        # Embed PR descriptions on open/update
        if action in ["opened", "edited", "synchronize"]:
            title = pr.get("title", "")
            body = pr.get("body", "") or ""
            user = pr.get("user", {})
            
            text = f"""
Pull Request: {title}
Description: {body}
Author: {user.get('login', 'unknown')}
Base: {pr.get('base', {}).get('ref', '')} ← Head: {pr.get('head', {}).get('ref', '')}
""".strip()
            
            embeddings_to_create.append({
                "text": text,
                "embedding_type": EmbeddingType.DEVELOPER_ACTIVITY,
                "source_id": str(raw.get("number", 0)).ljust(36, '0'),
                "source_table": "github_pull_requests",
                "title": f"PR: {title[:60]}",
                "metadata": {
                    "pr_number": raw.get("number"),
                    "action": action,
                    "author": user.get("login"),
                    "state": pr.get("state"),
                    "merged": pr.get("merged", False)
                }
            })
    
    elif event_type == "issues":
        issue = raw.get("issue", {})
        action = raw.get("action", "")
        
        if action in ["opened", "edited"]:
            title = issue.get("title", "")
            body = issue.get("body", "") or ""
            user = issue.get("user", {})
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            
            text = f"""
GitHub Issue: {title}
Description: {body}
Labels: {', '.join(labels) if labels else 'none'}
Reporter: {user.get('login', 'unknown')}
""".strip()
            
            embeddings_to_create.append({
                "text": text,
                "embedding_type": EmbeddingType.ISSUE_DESCRIPTION,
                "source_id": str(issue.get("number", 0)).ljust(36, '0'),
                "source_table": "github_issues",
                "title": f"Issue: {title[:60]}",
                "metadata": {
                    "issue_number": issue.get("number"),
                    "author": user.get("login"),
                    "labels": labels,
                    "state": issue.get("state")
                }
            })
    
    return embeddings_to_create


def extract_embeddable_text_jira(event_type: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract text content from Jira events for embedding."""
    embeddings_to_create = []
    
    issue = raw.get("issue", {})
    issue_key = issue.get("key", "")
    fields = issue.get("fields", {})
    
    if event_type in ["jira:issue_created", "jira:issue_updated"]:
        summary = fields.get("summary", "")
        description = fields.get("description", "") or ""
        issue_type = fields.get("issuetype", {}).get("name", "")
        priority = fields.get("priority", {}).get("name", "")
        assignee = fields.get("assignee", {})
        
        text = f"""
Jira {issue_type}: {summary}
Description: {description}
Priority: {priority}
Assignee: {assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'}
""".strip()
        
        embeddings_to_create.append({
            "text": text,
            "embedding_type": EmbeddingType.ISSUE_DESCRIPTION,
            "source_id": issue_key.ljust(36, '0')[:36],
            "source_table": "jira_issues",
            "title": f"[{issue_key}] {summary[:50]}",
            "metadata": {
                "issue_key": issue_key,
                "issue_type": issue_type,
                "priority": priority,
                "status": fields.get("status", {}).get("name"),
                "assignee": assignee.get("emailAddress") if assignee else None
            }
        })
    
    return embeddings_to_create


def extract_embeddable_text_notion(event_type: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract text content from Notion events for embedding."""
    embeddings_to_create = []
    
    page = raw.get("page", {})
    page_id = page.get("id", "")
    page_title = page.get("title", "")
    
    if event_type in ["page_created", "page_updated"]:
        # Get content from page properties if available
        content = page.get("content", "") or page.get("properties", {}).get("content", "")
        
        text = f"""
Notion Page: {page_title}
Content: {content if content else 'No content available'}
""".strip()
        
        embeddings_to_create.append({
            "text": text,
            "embedding_type": EmbeddingType.DOCUMENTATION,
            "source_id": page_id.ljust(36, '-')[:36],
            "source_table": "notion_pages",
            "title": page_title[:60] if page_title else "Untitled Page",
            "metadata": {
                "page_id": page_id,
                "event_type": event_type
            }
        })
    
    return embeddings_to_create


# ==============================================================================
# MAIN EMBEDDING PIPELINE
# ==============================================================================

def process_event_for_embeddings(source: str, event_type: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Process an event and generate embeddings for semantic search.
    
    This is called by the Kafka consumer after initial event processing.
    
    Args:
        source: Event source (github, jira, notion)
        event_type: Specific event type
        raw: Raw event payload
    
    Returns:
        List of embedding results with success status
    """
    extractors = {
        "github": extract_embeddable_text_github,
        "jira": extract_embeddable_text_jira,
        "notion": extract_embeddable_text_notion
    }
    
    extractor = extractors.get(source.lower())
    if not extractor:
        logger.warning(f"No embedding extractor for source: {source}")
        return []
    
    # Extract embeddable content
    items = extractor(event_type, raw)
    
    if not items:
        logger.info(f"No embeddable content in {source}/{event_type} event")
        return []
    
    # Create embeddings
    results = []
    for item in items:
        try:
            result = upsert_embedding(
                embedding_type=item["embedding_type"],
                source_id=item["source_id"],
                source_table=item["source_table"],
                text=item["text"],  # Will auto-generate embedding via Pinecone
                title=item["title"],
                metadata=item["metadata"]
            )
            results.append({
                "title": item["title"],
                "success": result.get("success", False),
                "embedding_id": result.get("embedding_id"),
                "error": result.get("message") if not result.get("success") else None
            })
            
            if result.get("success"):
                logger.info(f"Created embedding: {item['title']}")
            else:
                logger.error(f"Failed to create embedding: {result.get('message')}")
                
        except Exception as e:
            logger.error(f"Error creating embedding for {item['title']}: {e}")
            results.append({
                "title": item["title"],
                "success": False,
                "error": str(e)
            })
    
    return results


# ==============================================================================
# DEVELOPER PROFILE AGGREGATION
# ==============================================================================

def build_developer_profile_text(
    developer_email: str,
    commits: List[Dict[str, Any]] = None,
    prs: List[Dict[str, Any]] = None,
    issues: List[Dict[str, Any]] = None,
    skills: List[str] = None
) -> str:
    """
    Build a comprehensive developer profile text for embedding.
    
    This creates a searchable profile like:
    "Developer who works on authentication, API development, 
    has experience with Python, FastAPI, PostgreSQL..."
    """
    parts = [f"Developer: {developer_email}"]
    
    if skills:
        parts.append(f"Skills: {', '.join(skills)}")
    
    if commits:
        # Summarize recent commits
        commit_summary = "; ".join([
            c.get("message", "")[:50] for c in commits[:10]
        ])
        parts.append(f"Recent work: {commit_summary}")
    
    if prs:
        pr_titles = "; ".join([
            p.get("title", "") for p in prs[:5]
        ])
        parts.append(f"Pull requests: {pr_titles}")
    
    if issues:
        issue_titles = "; ".join([
            i.get("summary", i.get("title", "")) for i in issues[:5]
        ])
        parts.append(f"Issues worked on: {issue_titles}")
    
    return "\n".join(parts)


def update_developer_profile_embedding(
    employee_id: str,
    developer_email: str,
    profile_text: str
) -> Dict[str, Any]:
    """
    Update the searchable developer profile embedding.
    
    Called periodically or when significant activity occurs.
    """
    return upsert_embedding(
        embedding_type=EmbeddingType.DEVELOPER_PROFILE,
        source_id=employee_id,
        source_table="employees",
        text=profile_text,
        title=f"Profile: {developer_email}",
        metadata={
            "email": developer_email,
            "updated_at": datetime.utcnow().isoformat()
        }
    )
