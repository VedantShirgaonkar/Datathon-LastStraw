"""
Pydantic schemas for agent tools.
All tool inputs and outputs use these validated models.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ==============================================================================
# ENUMS
# ==============================================================================

class SkillProficiency(str, Enum):
    """Skill proficiency levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class DependencyType(str, Enum):
    """Project dependency types"""
    BLOCKING = "blocking"
    OPTIONAL = "optional"
    REQUIRED = "required"


class EventSource(str, Enum):
    """Event source types"""
    GITHUB = "github"
    JIRA = "jira"
    NOTION = "notion"
    PROMETHEUS = "prometheus"
    AI_AGENT = "ai_agent"


class GitHubEventType(str, Enum):
    """GitHub event types from MSK"""
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    ISSUES = "issues"
    ISSUE_COMMENT = "issue_comment"
    PULL_REQUEST_REVIEW = "pull_request_review"


class JiraEventType(str, Enum):
    """Jira event types from MSK"""
    ISSUE_CREATED = "jira:issue_created"
    ISSUE_UPDATED = "jira:issue_updated"
    ISSUE_DELETED = "jira:issue_deleted"
    COMMENT_CREATED = "jira:comment_created"
    SPRINT_STARTED = "jira:sprint_started"
    SPRINT_CLOSED = "jira:sprint_closed"


class NotionEventType(str, Enum):
    """Notion event types from MSK"""
    PAGE_CREATED = "page_created"
    PAGE_UPDATED = "page_updated"
    DATABASE_UPDATED = "database_updated"


# ==============================================================================
# NEO4J TOOL SCHEMAS
# ==============================================================================

class CreateDeveloperInput(BaseModel):
    """Input schema for creating a developer node"""
    email: EmailStr = Field(..., description="Developer's email address (unique)")
    name: str = Field(..., min_length=2, max_length=100, description="Developer's full name")
    team_id: str = Field(..., description="Team identifier")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "alice@company.com",
                "name": "Alice Johnson",
                "team_id": "team-platform"
            }
        }


class CreateDeveloperOutput(BaseModel):
    """Output schema for developer creation"""
    success: bool
    message: str
    developer_email: str
    node_id: Optional[str] = None


class AddSkillInput(BaseModel):
    """Input schema for adding skill to developer"""
    developer_email: EmailStr = Field(..., description="Developer's email")
    skill_name: str = Field(..., min_length=1, max_length=50, description="Skill name (e.g., Python, React)")
    proficiency: SkillProficiency = Field(..., description="Proficiency level")
    
    class Config:
        json_schema_extra = {
            "example": {
                "developer_email": "alice@company.com",
                "skill_name": "Python",
                "proficiency": "expert"
            }
        }


class AddSkillOutput(BaseModel):
    """Output schema for adding skill"""
    success: bool
    message: str
    skill_name: str
    proficiency: str


class ContributionMetrics(BaseModel):
    """Contribution metrics"""
    commits: int = Field(default=0, ge=0)
    prs: int = Field(default=0, ge=0)
    reviews: int = Field(default=0, ge=0)


class AddContributionInput(BaseModel):
    """Input schema for recording contribution"""
    developer_email: EmailStr
    project_id: str = Field(..., min_length=1)
    metrics: ContributionMetrics
    
    class Config:
        json_schema_extra = {
            "example": {
                "developer_email": "alice@company.com",
                "project_id": "proj-api",
                "metrics": {
                    "commits": 5,
                    "prs": 2,
                    "reviews": 3
                }
            }
        }


class AddContributionOutput(BaseModel):
    """Output schema for contribution"""
    success: bool
    message: str
    developer_email: str
    project_id: str


class CreateProjectDependencyInput(BaseModel):
    """Input schema for project dependency"""
    project_id: str = Field(..., description="Project that depends")
    depends_on_id: str = Field(..., description="Project being depended on")
    dependency_type: DependencyType


class CreateProjectDependencyOutput(BaseModel):
    """Output schema for dependency creation"""
    success: bool
    message: str
    from_project: str
    to_project: str


class FindDevelopersInput(BaseModel):
    """Input schema for finding available developers"""
    skill: str = Field(..., min_length=1, description="Required skill name")
    min_availability: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum availability (0.0-1.0)")


class DeveloperMatch(BaseModel):
    """Single developer match result"""
    email: EmailStr
    name: str
    availability: float
    skills: List[str]
    current_projects: List[str]


class FindDevelopersOutput(BaseModel):
    """Output schema for developer search"""
    success: bool
    matches: List[DeveloperMatch]
    total_found: int


# ==============================================================================
# CLICKHOUSE TOOL SCHEMAS
# ==============================================================================

class CommitData(BaseModel):
    """GitHub commit data"""
    sha: str = Field(..., min_length=7, max_length=40)
    message: str
    files_changed: int = Field(ge=0)
    lines_added: int = Field(ge=0)
    lines_deleted: int = Field(ge=0)
    timestamp: Optional[datetime] = None


class InsertCommitEventInput(BaseModel):
    """Input schema for commit event insertion"""
    project_id: str
    developer_email: EmailStr
    commit_data: CommitData
    
    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj-api",
                "developer_email": "alice@company.com",
                "commit_data": {
                    "sha": "abc123def",
                    "message": "Add OAuth2 authentication",
                    "files_changed": 3,
                    "lines_added": 150,
                    "lines_deleted": 20
                }
            }
        }


class InsertEventOutput(BaseModel):
    """Generic output for event insertion"""
    success: bool
    message: str
    event_type: str
    project_id: str


class PRData(BaseModel):
    """GitHub PR data"""
    pr_number: int = Field(gt=0)
    action: str = Field(..., description="opened, merged, reviewed, closed")
    review_time_hours: Optional[float] = Field(None, ge=0)
    lines_changed: Optional[int] = Field(None, ge=0)


class InsertPREventInput(BaseModel):
    """Input schema for PR event"""
    project_id: str
    developer_email: EmailStr
    pr_data: PRData


class JiraIssueData(BaseModel):
    """Jira issue data"""
    issue_key: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    event_type: str = Field(..., description="issue_created, issue_updated, issue_completed")
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    story_points: Optional[int] = Field(None, ge=0, le=100)


class InsertJiraEventInput(BaseModel):
    """Input schema for Jira event"""
    project_id: str
    developer_email: EmailStr
    issue_data: JiraIssueData


class DeveloperActivityInput(BaseModel):
    """Input schema for getting developer activity"""
    developer_email: EmailStr
    days: int = Field(default=30, ge=1, le=365, description="Number of days to look back")


class DeveloperActivityOutput(BaseModel):
    """Output schema for developer activity"""
    success: bool
    developer_email: str
    period_days: int
    commits: int
    prs_opened: int
    prs_merged: int
    reviews: int
    issues_completed: int


class DORAMetricsInput(BaseModel):
    """Input schema for DORA metrics"""
    project_id: str
    days: int = Field(default=30, ge=1, le=365)


class DORAMetricsOutput(BaseModel):
    """Output schema for DORA metrics"""
    success: bool
    project_id: str
    period_days: int
    deployment_frequency: float
    avg_lead_time_hours: float
    prs_merged: int
    story_points_completed: int


# ==============================================================================
# PINECONE TOOL SCHEMAS
# ==============================================================================

class UpsertEmbeddingInput(BaseModel):
    """Input schema for upserting embedding"""
    developer_email: EmailStr
    profile_text: str = Field(..., min_length=10, description="Text summary of developer profile")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class UpsertEmbeddingOutput(BaseModel):
    """Output schema for embedding upsert"""
    success: bool
    message: str
    developer_email: str
    embedding_dimension: int


class SearchDevelopersInput(BaseModel):
    """Input schema for semantic search"""
    query: str = Field(..., min_length=5, description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20)


class DeveloperSearchMatch(BaseModel):
    """Single search result"""
    email: EmailStr
    score: float = Field(..., ge=0.0, le=1.0)
    metadata: Dict[str, Any]


class SearchDevelopersOutput(BaseModel):
    """Output schema for developer search"""
    success: bool
    query: str
    matches: List[DeveloperSearchMatch]
    total_results: int


# ==============================================================================
# NOTIFICATION TOOL SCHEMAS
# ==============================================================================

class SendSlackInput(BaseModel):
    """Input schema for Slack notification"""
    channel: str = Field(..., description="Channel name or user email")
    message: str = Field(..., min_length=1, max_length=4000)
    blocks: Optional[List[Dict[str, Any]]] = None


class SendSlackOutput(BaseModel):
    """Output schema for Slack notification"""
    success: bool
    message: str
    channel: str


class SendEmailInput(BaseModel):
    """Input schema for email"""
    to: EmailStr
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)


class SendEmailOutput(BaseModel):
    """Output schema for email"""
    success: bool
    message: str
    recipient: str


# ==============================================================================
# JIRA TOOL SCHEMAS
# ==============================================================================

class AssignJiraIssueInput(BaseModel):
    """Input schema for Jira assignment"""
    issue_key: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    assignee_email: EmailStr


class AssignJiraIssueOutput(BaseModel):
    """Output schema for Jira assignment"""
    success: bool
    message: str
    issue_key: str
    assignee: str


class AddJiraCommentInput(BaseModel):
    """Input schema for Jira comment"""
    issue_key: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    comment: str = Field(..., min_length=1, max_length=10000)


class AddJiraCommentOutput(BaseModel):
    """Output schema for Jira comment"""
    success: bool
    message: str
    issue_key: str


# ==============================================================================
# AGENT STATE SCHEMAS
# ==============================================================================

class KafkaEvent(BaseModel):
    """Kafka event schema matching MSK event wrapper format"""
    event_id: Optional[str] = Field(None, description="Unique event identifier")
    source: EventSource
    event_type: str
    timestamp: datetime
    raw: Dict[str, Any] = Field(..., description="Original payload from source system")


class EventClassification(BaseModel):
    """Event classification result"""
    source: EventSource
    event_type: str
    developer_email: Optional[EmailStr] = None
    project_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class ToolCall(BaseModel):
    """Tool call specification"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str


class ToolResult(BaseModel):
    """Tool execution result"""
    tool_name: str
    call_id: str
    success: bool
    result: Any
    error: Optional[str] = None


class AgentResponse(BaseModel):
    """Final agent response"""
    summary: str
    actions_taken: List[str]
    tools_executed: int
    errors: List[str]
    success: bool
