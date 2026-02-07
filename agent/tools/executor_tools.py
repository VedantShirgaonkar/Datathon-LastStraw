"""
Executor Tools for External System Commands

Uses AWS Lambda (datathon-executor) to execute commands on:
- Jira: Create issues, add comments, assign issues, transition status
- GitHub: Create issues, add comments, close issues
- Notion: Create pages, update status, assign tasks
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import boto3
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

# Jira Schemas
class JiraCreateIssueInput(BaseModel):
    """Input for creating a Jira issue"""
    project_key: str = Field(..., description="Jira project key (e.g., PROJ)")
    summary: str = Field(..., description="Issue title/summary")
    issue_type: str = Field(default="Task", description="Issue type: Bug, Task, Story, Epic")
    description: Optional[str] = Field(None, description="Issue description")
    priority: Optional[str] = Field(None, description="Priority: Highest, High, Medium, Low, Lowest")
    assignee: Optional[str] = Field(None, description="Assignee username")
    labels: Optional[List[str]] = Field(None, description="Issue labels")


class JiraAddCommentInput(BaseModel):
    """Input for adding a comment to Jira issue"""
    issue_key: str = Field(..., description="Issue key (e.g., PROJ-123)")
    body: str = Field(..., description="Comment text")


class JiraAssignIssueInput(BaseModel):
    """Input for assigning a Jira issue"""
    issue_key: str = Field(..., description="Issue key (e.g., PROJ-123)")
    assignee: str = Field(..., description="Assignee username")


class JiraTransitionInput(BaseModel):
    """Input for transitioning Jira issue status"""
    issue_key: str = Field(..., description="Issue key (e.g., PROJ-123)")
    status: str = Field(..., description="Target status: To Do, In Progress, Done, etc.")


# GitHub Schemas
class GitHubCreateIssueInput(BaseModel):
    """Input for creating a GitHub issue"""
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    title: str = Field(..., description="Issue title")
    body: Optional[str] = Field(None, description="Issue body/description")
    labels: Optional[List[str]] = Field(None, description="Issue labels")
    assignees: Optional[List[str]] = Field(None, description="Assignee usernames")


class GitHubAddCommentInput(BaseModel):
    """Input for adding a comment to GitHub issue"""
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    issue_number: int = Field(..., description="Issue number")
    body: str = Field(..., description="Comment text")


class GitHubCloseIssueInput(BaseModel):
    """Input for closing a GitHub issue"""
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    issue_number: int = Field(..., description="Issue number")


# Notion Schemas
class NotionCreatePageInput(BaseModel):
    """Input for creating a Notion page"""
    parent_id: str = Field(..., description="Parent database or page ID")
    title: str = Field(..., description="Page title")
    title_property: str = Field(default="Name", description="Title property name in database")
    properties: Optional[Dict[str, Any]] = Field(None, description="Additional properties")


class NotionUpdateStatusInput(BaseModel):
    """Input for updating Notion page status"""
    page_id: str = Field(..., description="Page ID")
    status: str = Field(..., description="New status value")
    status_property: str = Field(default="Status", description="Status property name")


class NotionAssignTaskInput(BaseModel):
    """Input for assigning a Notion task"""
    page_id: str = Field(..., description="Page ID")
    assignee: str = Field(..., description="Assignee name")
    priority: Optional[str] = Field(None, description="Priority: High, Medium, Low")
    deadline: Optional[str] = Field(None, description="Deadline date (YYYY-MM-DD)")


class ExecutorOutput(BaseModel):
    """Output from executor commands"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ==============================================================================
# LAMBDA EXECUTOR CLIENT
# ==============================================================================

class LambdaExecutor:
    """Client for invoking the datathon-executor Lambda function"""
    
    def __init__(self, function_name: str = "datathon-executor", region: str = "ap-south-1"):
        self.function_name = function_name
        self.region = region
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of boto3 Lambda client"""
        if self._client is None:
            self._client = boto3.client('lambda', region_name=self.region)
        return self._client
    
    def execute(self, target: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a command via Lambda.
        
        Args:
            target: Target system (jira, github, notion)
            action: Action to perform (create_issue, add_comment, etc.)
            payload: Action-specific payload
        
        Returns:
            Response from Lambda executor
        """
        try:
            command = {
                "command": {
                    "target": target,
                    "action": action,
                    "payload": payload
                }
            }
            
            logger.info(f"Executing {target}.{action}: {payload}")
            
            response = self.client.invoke(
                FunctionName=self.function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(command)
            )
            
            result = json.loads(response['Payload'].read())
            
            if response.get('FunctionError'):
                logger.error(f"Lambda error: {result}")
                return {"success": False, "error": str(result)}
            
            return {"success": True, "data": result}
            
        except Exception as e:
            logger.error(f"Executor error: {e}")
            return {"success": False, "error": str(e)}


# Global executor instance
_executor: Optional[LambdaExecutor] = None


def get_executor() -> LambdaExecutor:
    """Get or create global executor instance"""
    global _executor
    if _executor is None:
        _executor = LambdaExecutor()
    return _executor


# ==============================================================================
# JIRA TOOLS
# ==============================================================================

def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = None,
    priority: str = None,
    assignee: str = None,
    labels: List[str] = None
) -> dict:
    """
    Create a new Jira issue.
    
    Args:
        project_key: Jira project key (e.g., PROJ)
        summary: Issue title/summary
        issue_type: Bug, Task, Story, Epic
        description: Issue description
        priority: Highest, High, Medium, Low, Lowest
        assignee: Assignee username
        labels: Issue labels
    
    Returns:
        dict with success status and issue key
    """
    try:
        payload = {
            "project_key": project_key,
            "summary": summary,
            "issue_type": issue_type
        }
        if description:
            payload["description"] = description
        if priority:
            payload["priority"] = priority
        if assignee:
            payload["assignee"] = assignee
        if labels:
            payload["labels"] = labels
        
        result = get_executor().execute("jira", "create_issue", payload)
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Created Jira issue in {project_key}" if result.get("success") else "Failed to create issue",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def jira_add_comment(issue_key: str, body: str) -> dict:
    """
    Add a comment to a Jira issue.
    
    Args:
        issue_key: Issue key (e.g., PROJ-123)
        body: Comment text
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("jira", "add_comment", {
            "issue_key": issue_key,
            "body": body
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Added comment to {issue_key}" if result.get("success") else "Failed to add comment",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def jira_assign_issue(issue_key: str, assignee: str) -> dict:
    """
    Assign a Jira issue to a user.
    
    Args:
        issue_key: Issue key (e.g., PROJ-123)
        assignee: Assignee username
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("jira", "assign_issue", {
            "issue_key": issue_key,
            "assignee": assignee
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Assigned {issue_key} to {assignee}" if result.get("success") else "Failed to assign issue",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def jira_transition_issue(issue_key: str, status: str) -> dict:
    """
    Transition a Jira issue to a new status.
    
    Args:
        issue_key: Issue key (e.g., PROJ-123)
        status: Target status (To Do, In Progress, Done, etc.)
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("jira", "transition_issue", {
            "issue_key": issue_key,
            "status": status
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Transitioned {issue_key} to {status}" if result.get("success") else "Failed to transition issue",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


# ==============================================================================
# GITHUB TOOLS
# ==============================================================================

def github_create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = None,
    labels: List[str] = None,
    assignees: List[str] = None
) -> dict:
    """
    Create a new GitHub issue.
    
    Args:
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body/description
        labels: Issue labels
        assignees: Assignee usernames
    
    Returns:
        dict with success status and issue number
    """
    try:
        payload = {
            "owner": owner,
            "repo": repo,
            "title": title
        }
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        
        result = get_executor().execute("github", "create_issue", payload)
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Created GitHub issue in {owner}/{repo}" if result.get("success") else "Failed to create issue",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def github_add_comment(owner: str, repo: str, issue_number: int, body: str) -> dict:
    """
    Add a comment to a GitHub issue or PR.
    
    Args:
        owner: Repository owner
        repo: Repository name
        issue_number: Issue or PR number
        body: Comment text
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("github", "add_comment", {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "body": body
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Added comment to {owner}/{repo}#{issue_number}" if result.get("success") else "Failed to add comment",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def github_close_issue(owner: str, repo: str, issue_number: int) -> dict:
    """
    Close a GitHub issue.
    
    Args:
        owner: Repository owner
        repo: Repository name
        issue_number: Issue number to close
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("github", "close_issue", {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Closed {owner}/{repo}#{issue_number}" if result.get("success") else "Failed to close issue",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


# ==============================================================================
# NOTION TOOLS
# ==============================================================================

def notion_create_page(
    parent_id: str,
    title: str,
    title_property: str = "Name",
    properties: Dict[str, Any] = None
) -> dict:
    """
    Create a new Notion page in a database.
    
    Args:
        parent_id: Parent database ID
        title: Page title
        title_property: Name of the title property (default: Name)
        properties: Additional property values
    
    Returns:
        dict with success status and page ID
    """
    try:
        payload = {
            "parent_id": parent_id,
            "title": title,
            "title_property": title_property
        }
        if properties:
            payload["properties"] = properties
        
        result = get_executor().execute("notion", "create_page", payload)
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Created Notion page: {title}" if result.get("success") else "Failed to create page",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def notion_update_status(page_id: str, status: str, status_property: str = "Status") -> dict:
    """
    Update the status of a Notion page.
    
    Args:
        page_id: Notion page ID
        status: New status value
        status_property: Name of the status property (default: Status)
    
    Returns:
        dict with success status
    """
    try:
        result = get_executor().execute("notion", "update_status", {
            "page_id": page_id,
            "status": status,
            "status_property": status_property
        })
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Updated Notion page status to {status}" if result.get("success") else "Failed to update status",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


def notion_assign_task(
    page_id: str,
    assignee: str,
    priority: str = None,
    deadline: str = None
) -> dict:
    """
    Assign a Notion task to a user with optional priority and deadline.
    
    Args:
        page_id: Notion page ID
        assignee: Assignee name
        priority: Priority level (High, Medium, Low)
        deadline: Deadline date (YYYY-MM-DD)
    
    Returns:
        dict with success status
    """
    try:
        payload = {
            "page_id": page_id,
            "assignee": assignee
        }
        if priority:
            payload["priority"] = priority
        if deadline:
            payload["deadline"] = deadline
        
        result = get_executor().execute("notion", "assign_task", payload)
        
        return ExecutorOutput(
            success=result.get("success", False),
            message=f"Assigned task to {assignee}" if result.get("success") else "Failed to assign task",
            data=result.get("data"),
            error=result.get("error")
        ).model_dump()
        
    except Exception as e:
        return ExecutorOutput(success=False, error=str(e)).model_dump()


# ==============================================================================
# LANGCHAIN STRUCTURED TOOLS
# ==============================================================================

executor_tools = [
    # Jira Tools
    StructuredTool.from_function(
        func=jira_create_issue,
        name="jira_create_issue",
        description="Create a new Jira issue. Use when you need to create bugs, tasks, or stories.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=jira_add_comment,
        name="jira_add_comment",
        description="Add a comment to an existing Jira issue.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=jira_assign_issue,
        name="jira_assign_issue",
        description="Assign a Jira issue to a team member.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=jira_transition_issue,
        name="jira_transition_issue",
        description="Move a Jira issue to a different status (To Do, In Progress, Done).",
        return_direct=False
    ),
    
    # GitHub Tools
    StructuredTool.from_function(
        func=github_create_issue,
        name="github_create_issue",
        description="Create a new GitHub issue in a repository.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=github_add_comment,
        name="github_add_comment",
        description="Add a comment to a GitHub issue or pull request.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=github_close_issue,
        name="github_close_issue",
        description="Close a GitHub issue.",
        return_direct=False
    ),
    
    # Notion Tools
    StructuredTool.from_function(
        func=notion_create_page,
        name="notion_create_page",
        description="Create a new page in a Notion database.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=notion_update_status,
        name="notion_update_status",
        description="Update the status of a Notion page/task.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=notion_assign_task,
        name="notion_assign_task",
        description="Assign a Notion task to someone with optional priority and deadline.",
        return_direct=False
    ),
]
