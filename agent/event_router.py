"""
Event Action Router

Defines rules for cross-platform actions based on incoming events.
This module helps the agent decide WHEN to use executor tools.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """Types of cross-platform actions"""
    JIRA_CREATE_ISSUE = "jira_create_issue"
    JIRA_ADD_COMMENT = "jira_add_comment"
    JIRA_ASSIGN_ISSUE = "jira_assign_issue"
    JIRA_TRANSITION_ISSUE = "jira_transition_issue"
    GITHUB_CREATE_ISSUE = "github_create_issue"
    GITHUB_ADD_COMMENT = "github_add_comment"
    GITHUB_CLOSE_ISSUE = "github_close_issue"
    NOTION_CREATE_PAGE = "notion_create_page"
    NOTION_UPDATE_STATUS = "notion_update_status"
    NOTION_ASSIGN_TASK = "notion_assign_task"


@dataclass
class SuggestedAction:
    """A suggested action based on event routing rules"""
    action_type: ActionType
    reason: str
    suggested_params: Dict[str, Any]
    priority: int  # 1=high, 2=medium, 3=low
    requires_confirmation: bool = False


# ==============================================================================
# EVENT ROUTING RULES
# ==============================================================================

def route_github_event(event_type: str, raw: Dict[str, Any]) -> List[SuggestedAction]:
    """
    Route GitHub events to appropriate cross-platform actions.
    
    Triggers:
    - push → log commits in Jira comments if linked
    - pull_request opened → create/link Jira issue
    - pull_request merged → transition Jira to Done, update Notion
    - issues opened → create corresponding Jira bug (if critical)
    - issues closed → sync status
    """
    actions = []
    
    if event_type == "push":
        # Push events could update Jira with commit info
        commits = raw.get("commits", [])
        repo = raw.get("repository", {})
        
        for commit in commits:
            message = commit.get("message", "")
            # Check if commit references a Jira ticket (e.g., "PROJ-123")
            import re
            jira_refs = re.findall(r'([A-Z]+-\d+)', message)
            
            for issue_key in jira_refs:
                actions.append(SuggestedAction(
                    action_type=ActionType.JIRA_ADD_COMMENT,
                    reason=f"Commit '{message[:50]}...' references {issue_key}",
                    suggested_params={
                        "issue_key": issue_key,
                        "body": f"Commit pushed: {commit.get('id', '')[:7]}\n{message}\nRepo: {repo.get('full_name', '')}"
                    },
                    priority=2
                ))
    
    elif event_type == "pull_request":
        action = raw.get("action", "")
        pr = raw.get("pull_request", {})
        pr_title = pr.get("title", "")
        pr_number = raw.get("number", 0)
        
        # Look for Jira refs in PR title
        import re
        jira_refs = re.findall(r'([A-Z]+-\d+)', pr_title)
        
        if action == "opened":
            # PR opened - might need Jira tracking
            if not jira_refs:
                # No Jira ticket referenced - suggest creating one
                actions.append(SuggestedAction(
                    action_type=ActionType.JIRA_CREATE_ISSUE,
                    reason=f"PR #{pr_number} opened without Jira reference",
                    suggested_params={
                        "project_key": "PROJ",  # Agent should extract from context
                        "summary": f"[PR #{pr_number}] {pr_title}",
                        "issue_type": "Task",
                        "description": pr.get("body", "")
                    },
                    priority=2,
                    requires_confirmation=True
                ))
        
        elif action == "closed" and pr.get("merged"):
            # PR merged - transition Jira issues
            for issue_key in jira_refs:
                actions.append(SuggestedAction(
                    action_type=ActionType.JIRA_TRANSITION_ISSUE,
                    reason=f"PR #{pr_number} merged - transitioning {issue_key} to Done",
                    suggested_params={
                        "issue_key": issue_key,
                        "status": "Done"
                    },
                    priority=1
                ))
            
            # Also update Notion if sprint tracking
            actions.append(SuggestedAction(
                action_type=ActionType.NOTION_UPDATE_STATUS,
                reason=f"PR #{pr_number} merged - update sprint status",
                suggested_params={
                    "status": "Completed"
                },
                priority=3,
                requires_confirmation=True
            ))
    
    elif event_type == "issues":
        action = raw.get("action", "")
        issue = raw.get("issue", {})
        issue_title = issue.get("title", "")
        issue_number = issue.get("number", 0)
        
        if action == "opened":
            # GitHub issue opened - create Jira for tracking
            labels = [l.get("name", "") for l in issue.get("labels", [])]
            
            if "bug" in labels or "critical" in labels:
                actions.append(SuggestedAction(
                    action_type=ActionType.JIRA_CREATE_ISSUE,
                    reason=f"GitHub issue #{issue_number} opened with bug/critical label",
                    suggested_params={
                        "project_key": "PROJ",
                        "summary": f"[GH-{issue_number}] {issue_title}",
                        "issue_type": "Bug",
                        "priority": "High" if "critical" in labels else "Medium",
                        "description": issue.get("body", "")
                    },
                    priority=1
                ))
    
    return actions


def route_jira_event(event_type: str, raw: Dict[str, Any]) -> List[SuggestedAction]:
    """
    Route Jira events to appropriate cross-platform actions.
    
    Triggers:
    - issue_created → create GitHub issue if code-related
    - issue_updated (status change) → update Notion, comment on GitHub
    - issue_assigned → sync to Notion task assignment
    """
    actions = []
    
    issue = raw.get("issue", {})
    issue_key = issue.get("key", "")
    fields = issue.get("fields", {})
    
    if event_type == "jira:issue_created":
        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        priority = fields.get("priority", {}).get("name", "")
        
        # Code-related bugs should have GitHub issues
        if issue_type == "Bug":
            actions.append(SuggestedAction(
                action_type=ActionType.GITHUB_CREATE_ISSUE,
                reason=f"Jira bug {issue_key} created - sync to GitHub",
                suggested_params={
                    "owner": "owner",  # Agent extracts from context
                    "repo": "repo",
                    "title": f"[{issue_key}] {summary}",
                    "body": f"Jira Issue: {issue_key}\nPriority: {priority}\n\n{fields.get('description', '')}",
                    "labels": ["bug", "from-jira"]
                },
                priority=1 if priority == "High" else 2
            ))
        
        # Track in Notion for sprint management
        actions.append(SuggestedAction(
            action_type=ActionType.NOTION_CREATE_PAGE,
            reason=f"Track {issue_key} in Notion sprint board",
            suggested_params={
                "title": f"{issue_key}: {summary}",
                "title_property": "Name",
                "properties": {
                    "Type": issue_type,
                    "Priority": priority
                }
            },
            priority=2,
            requires_confirmation=True
        ))
    
    elif event_type == "jira:issue_updated":
        changelog = raw.get("changelog", {})
        items = changelog.get("items", [])
        
        for item in items:
            field = item.get("field", "")
            from_val = item.get("fromString", "")
            to_val = item.get("toString", "")
            
            if field == "status":
                # Status changed - sync to Notion
                actions.append(SuggestedAction(
                    action_type=ActionType.NOTION_UPDATE_STATUS,
                    reason=f"{issue_key} status: {from_val} → {to_val}",
                    suggested_params={
                        "status": to_val
                    },
                    priority=2
                ))
                
                # If marked Done, check if linked GitHub issue should close
                if to_val.lower() in ["done", "resolved", "closed"]:
                    actions.append(SuggestedAction(
                        action_type=ActionType.GITHUB_CLOSE_ISSUE,
                        reason=f"{issue_key} resolved - close linked GitHub issue",
                        suggested_params={
                            "owner": "owner",
                            "repo": "repo",
                            "issue_number": 0  # Agent extracts from context
                        },
                        priority=2,
                        requires_confirmation=True
                    ))
            
            elif field == "assignee":
                # Assignee changed - sync to Notion
                actions.append(SuggestedAction(
                    action_type=ActionType.NOTION_ASSIGN_TASK,
                    reason=f"{issue_key} assigned to {to_val}",
                    suggested_params={
                        "assignee": to_val
                    },
                    priority=3
                ))
    
    return actions


def route_notion_event(event_type: str, raw: Dict[str, Any]) -> List[SuggestedAction]:
    """
    Route Notion events to appropriate cross-platform actions.
    
    Triggers:
    - page_created → inform Jira if task-related
    - page_updated → sync status to Jira
    """
    actions = []
    
    page = raw.get("page", {})
    page_title = page.get("title", "")
    
    if event_type == "page_created":
        # New Notion page might need Jira task
        actions.append(SuggestedAction(
            action_type=ActionType.JIRA_ADD_COMMENT,
            reason=f"Notion page created: {page_title}",
            suggested_params={
                "issue_key": "PROJ-XXX",  # Agent extracts from context
                "body": f"Documentation page created: {page_title}"
            },
            priority=3,
            requires_confirmation=True
        ))
    
    elif event_type == "page_updated":
        user = raw.get("user", {})
        # Status sync to Jira
        actions.append(SuggestedAction(
            action_type=ActionType.JIRA_ADD_COMMENT,
            reason=f"Notion page updated: {page_title}",
            suggested_params={
                "issue_key": "PROJ-XXX",
                "body": f"Doc updated by {user.get('name', 'unknown')}: {page_title}"
            },
            priority=3,
            requires_confirmation=True
        ))
    
    return actions


# ==============================================================================
# MAIN ROUTER
# ==============================================================================

def get_suggested_actions(source: str, event_type: str, raw: Dict[str, Any]) -> List[SuggestedAction]:
    """
    Main routing function - determines cross-platform actions based on event.
    
    Args:
        source: Event source (github, jira, notion)
        event_type: Specific event type
        raw: Raw event payload
    
    Returns:
        List of suggested actions for the agent to consider
    """
    routers = {
        "github": route_github_event,
        "jira": route_jira_event,
        "notion": route_notion_event
    }
    
    router = routers.get(source.lower())
    if router:
        return router(event_type, raw)
    
    return []


def format_actions_for_prompt(actions: List[SuggestedAction]) -> str:
    """
    Format suggested actions for inclusion in LLM prompt.
    """
    if not actions:
        return "No specific cross-platform actions suggested for this event."
    
    lines = ["Suggested Cross-Platform Actions:"]
    for i, action in enumerate(sorted(actions, key=lambda a: a.priority), 1):
        priority_label = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}.get(action.priority, "MEDIUM")
        confirm = " (requires confirmation)" if action.requires_confirmation else ""
        lines.append(f"\n{i}. [{priority_label}] {action.action_type.value}{confirm}")
        lines.append(f"   Reason: {action.reason}")
        lines.append(f"   Params: {action.suggested_params}")
    
    return "\n".join(lines)
