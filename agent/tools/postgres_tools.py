"""
PostgreSQL tools with pgvector support and Pydantic validation.
Embeddings are generated using Pinecone's inference API (llama-text-embed-v2).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, EmailStr, ValidationError
from typing import Optional, List, Dict, Any
from uuid import UUID
import json

from postgres.postgres_client import PostgresClient
from postgres.embedding_service import embed_text


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class CreateEmployeeInput(BaseModel):
    """Input for creating an employee"""
    email: EmailStr = Field(..., description="Employee's email address")
    full_name: str = Field(..., min_length=2, max_length=255, description="Employee's full name")
    team_id: UUID = Field(..., description="Team UUID")
    title: Optional[str] = Field(None, max_length=100, description="Job title (e.g., Senior Engineer)")
    role: Optional[str] = Field(None, max_length=100, description="Job role (legacy, use title)")
    hourly_rate: float = Field(default=50.0, ge=0.0, le=500.0)
    manager_id: Optional[UUID] = Field(None, description="Manager's employee UUID")
    location: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    employment_type: Optional[str] = Field(default="full_time", description="full_time, part_time, contractor")
    level: Optional[str] = Field(None, max_length=50, description="Seniority level")


class CreateEmployeeOutput(BaseModel):
    """Output for employee creation"""
    success: bool
    message: str
    employee_id: Optional[str] = None
    email: str


# Backward compatibility aliases
CreateUserInput = CreateEmployeeInput
CreateUserOutput = CreateEmployeeOutput


class CreateProjectInput(BaseModel):
    """Input for creating a project"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    github_repo: Optional[str] = Field(None, max_length=255, description="GitHub repository (owner/repo)")
    jira_project_key: Optional[str] = Field(None, max_length=50, description="Jira project key")
    notion_database_id: Optional[str] = Field(None, max_length=255, description="Notion database ID")
    status: str = Field(default="active", pattern="^(active|on_hold|completed)$")
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD format")


class CreateProjectOutput(BaseModel):
    """Output for project creation"""
    success: bool
    message: str
    project_id: Optional[str] = None
    name: str


class AssignEmployeeToProjectInput(BaseModel):
    """Input for assigning employee to project"""
    employee_id: UUID
    project_id: UUID
    role: str = Field(default="contributor", max_length=50)
    allocated_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    start_date: Optional[str] = Field(None, description="Assignment start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Assignment end date (YYYY-MM-DD)")


class AssignEmployeeToProjectOutput(BaseModel):
    """Output for project assignment"""
    success: bool
    message: str
    assignment_id: Optional[str] = None


# Backward compatibility aliases
AssignUserToProjectInput = AssignEmployeeToProjectInput
AssignUserToProjectOutput = AssignEmployeeToProjectOutput


class AddIdentityMappingInput(BaseModel):
    """Input for adding external identity mapping"""
    employee_id: UUID
    source: str = Field(..., description="github, jira, slack, notion, etc.")
    external_id: str = Field(..., max_length=255)
    external_username: Optional[str] = Field(None, max_length=255)
    external_email: Optional[str] = Field(None, max_length=255)


class AddIdentityMappingOutput(BaseModel):
    """Output for identity mapping"""
    success: bool
    message: str
    mapping_id: Optional[str] = None


class UpsertEmbeddingInput(BaseModel):
    """Input for upserting vector embedding"""
    embedding_type: str = Field(..., max_length=50, description="developer_profile, project_description, etc.")
    source_id: UUID = Field(..., description="UUID of the source record")
    source_table: str = Field(..., max_length=50, description="employees, projects, tasks, etc.")
    embedding: Optional[List[float]] = Field(None, min_length=1024, max_length=1024, description="Pre-computed vector (1024 dims). If not provided, text must be given.")
    text: Optional[str] = Field(None, description="Text to embed using Pinecone. Required if embedding not provided.")
    title: str = Field(..., max_length=255)
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UpsertEmbeddingOutput(BaseModel):
    """Output for embedding upsert"""
    success: bool
    message: str
    embedding_id: Optional[str] = None
    dimensions: int


class SearchEmbeddingsInput(BaseModel):
    """Input for semantic search"""
    query_embedding: Optional[List[float]] = Field(None, min_length=1024, max_length=1024, description="Pre-computed query vector (1024 dims). If not provided, query_text must be given.")
    query_text: Optional[str] = Field(None, description="Text to embed as query using Pinecone. Required if query_embedding not provided.")
    embedding_type: Optional[str] = Field(None, description="Filter by embedding type")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum cosine similarity (0-1)")


class EmbeddingMatch(BaseModel):
    """Single search result"""
    id: str
    source_id: str
    source_table: str
    title: str
    content: Optional[str]
    metadata: Optional[Dict[str, Any]]
    similarity: float = Field(..., ge=0.0, le=1.0)


class SearchEmbeddingsOutput(BaseModel):
    """Output for vector search"""
    success: bool
    matches: List[EmbeddingMatch]
    total_results: int


class GetEmployeeByEmailInput(BaseModel):
    """Input for getting employee by email"""
    email: EmailStr


class EmployeeDetails(BaseModel):
    """Employee details"""
    id: str
    email: str
    full_name: str
    team_id: Optional[str]
    title: Optional[str]
    role: Optional[str]  # Legacy field
    hourly_rate: float
    manager_id: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    active: bool = True


class GetEmployeeByEmailOutput(BaseModel):
    """Output for employee lookup"""
    success: bool
    employee: Optional[EmployeeDetails]
    message: str


# Backward compatibility aliases
GetUserByEmailInput = GetEmployeeByEmailInput
UserDetails = EmployeeDetails
GetUserByEmailOutput = GetEmployeeByEmailOutput


class GetProjectByIdInput(BaseModel):
    """Input for getting project by ID"""
    project_id: UUID


class ProjectDetails(BaseModel):
    """Project details"""
    id: str
    name: str
    description: Optional[str]
    github_repo: Optional[str]
    jira_project_key: Optional[str]
    notion_database_id: Optional[str]
    status: str
    priority: str
    target_date: Optional[str]


class GetProjectByIdOutput(BaseModel):
    """Output for project lookup"""
    success: bool
    project: Optional[ProjectDetails]
    message: str


# ==============================================================================
# NEW UNIFIED SCHEMA MODELS
# ==============================================================================

# Task Models
class CreateTaskInput(BaseModel):
    """Input for creating a task"""
    source: str = Field(..., description="jira, notion, internal")
    external_key: str = Field(..., max_length=255, description="External key (e.g., PROJ-123)")
    project_id: Optional[UUID] = Field(None, description="Project UUID")
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    task_type: Optional[str] = Field(None, description="Bug, Task, Story, Epic")
    priority: Optional[str] = Field(None, description="High, Medium, Low")
    status: Optional[str] = Field(default="todo")
    status_category: Optional[str] = Field(default="todo", description="todo, in_progress, done, blocked")
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD format")
    assignee_employee_id: Optional[UUID] = None
    reporter_employee_id: Optional[UUID] = None
    labels: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class CreateTaskOutput(BaseModel):
    """Output for task creation"""
    success: bool
    message: str
    task_id: Optional[str] = None
    external_key: str


class UpdateTaskStatusInput(BaseModel):
    """Input for updating task status"""
    task_id: Optional[UUID] = None
    external_key: Optional[str] = None
    status: str = Field(..., description="New status value")
    status_category: str = Field(..., description="todo, in_progress, done, blocked")


class UpdateTaskStatusOutput(BaseModel):
    """Output for task status update"""
    success: bool
    message: str


class TaskDetails(BaseModel):
    """Task details"""
    id: str
    source: str
    external_key: str
    project_id: Optional[str]
    title: str
    description: Optional[str]
    task_type: Optional[str]
    priority: Optional[str]
    status: Optional[str]
    status_category: Optional[str]
    due_date: Optional[str]
    assignee_employee_id: Optional[str]


class GetTaskOutput(BaseModel):
    """Output for task lookup"""
    success: bool
    task: Optional[TaskDetails]
    message: str


# Check-In Models
class LogCheckInInput(BaseModel):
    """Input for logging employee check-in"""
    employee_id: UUID
    cadence: str = Field(..., description="weekly or monthly")
    period_start: str = Field(..., description="YYYY-MM-DD")
    period_end: str = Field(..., description="YYYY-MM-DD")
    wins: Optional[str] = None
    challenges: Optional[str] = None
    blockers: Optional[str] = None
    learnings: Optional[str] = None
    next_period_focus: Optional[str] = None
    help_needed: Optional[str] = None
    morale_score: Optional[int] = Field(None, ge=1, le=10)


class LogCheckInOutput(BaseModel):
    """Output for check-in logging"""
    success: bool
    message: str
    check_in_id: Optional[str] = None


class CheckInDetails(BaseModel):
    """Check-in details"""
    id: str
    employee_id: str
    cadence: str
    period_start: str
    period_end: str
    wins: Optional[str]
    challenges: Optional[str]
    blockers: Optional[str]
    morale_score: Optional[int]
    submitted_at: str


class GetCheckInsOutput(BaseModel):
    """Output for check-ins lookup"""
    success: bool
    check_ins: List[CheckInDetails]
    message: str


# Feedback Models
class AddFeedbackInput(BaseModel):
    """Input for adding feedback"""
    subject_employee_id: UUID = Field(..., description="Employee receiving feedback")
    author_employee_id: Optional[UUID] = Field(None, description="Feedback author (null for anonymous)")
    period_start: str = Field(..., description="YYYY-MM-DD")
    period_end: str = Field(..., description="YYYY-MM-DD")
    feedback_type: str = Field(..., description="kudos, constructive, peer_review")
    competency: Optional[str] = Field(None, description="Area being evaluated")
    rating: Optional[int] = Field(None, ge=1, le=5)
    content: str = Field(..., description="Feedback content")
    visibility: str = Field(default="hr_manager", description="private, manager, hr_manager")


class AddFeedbackOutput(BaseModel):
    """Output for feedback adding"""
    success: bool
    message: str
    feedback_id: Optional[str] = None


class FeedbackDetails(BaseModel):
    """Feedback details"""
    id: str
    subject_employee_id: str
    feedback_type: str
    competency: Optional[str]
    rating: Optional[int]
    content: str
    period_start: str
    period_end: str
    created_at: str


class GetFeedbackOutput(BaseModel):
    """Output for feedback lookup"""
    success: bool
    feedback: List[FeedbackDetails]
    message: str


# ==============================================================================
# TOOL FUNCTIONS
# ==============================================================================

def create_employee(
    email: str,
    full_name: str,
    team_id: str,
    title: str = None,
    role: str = None,
    hourly_rate: float = 50.0,
    manager_id: str = None,
    location: str = None,
    timezone: str = None,
    employment_type: str = "full_time",
    level: str = None
) -> dict:
    """
    Create a new employee in PostgreSQL.
    
    Args:
        email: Employee's email address (unique)
        full_name: Employee's full name
        team_id: Team UUID
        title: Job title (e.g., Senior Engineer, Tech Lead)
        role: Legacy field for job role (prefer title)
        hourly_rate: Hourly rate in USD
        manager_id: Manager's employee UUID
        location: Work location
        timezone: Employee timezone
        employment_type: full_time, part_time, contractor
        level: Seniority level
        
    Returns:
        dict: Success status and employee ID
    """
    try:
        # Use title or fall back to role for backward compatibility
        job_title = title or role
        
        # Validate input
        input_data = CreateEmployeeInput(
            email=email,
            full_name=full_name,
            team_id=UUID(team_id),
            title=job_title,
            role=role,
            hourly_rate=hourly_rate,
            manager_id=UUID(manager_id) if manager_id else None,
            location=location,
            timezone=timezone,
            employment_type=employment_type,
            level=level
        )
        
        # Insert employee
        client = PostgresClient()
        query = """
            INSERT INTO employees (email, full_name, team_id, title, role, hourly_rate, manager_id, location, timezone, employment_type, level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        result = client.execute_write_returning(
            query,
            (input_data.email, input_data.full_name, str(input_data.team_id), 
             input_data.title, input_data.role, input_data.hourly_rate,
             str(input_data.manager_id) if input_data.manager_id else None,
             input_data.location, input_data.timezone, input_data.employment_type, input_data.level)
        )
        client.close()
        
        employee_id = str(result[0]['id']) if result else None
        
        output = CreateEmployeeOutput(
            success=True,
            message=f"Created employee {full_name}",
            employee_id=employee_id,
            email=email
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "employee_id": None, "email": email}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "employee_id": None, "email": email}


# Backward compatibility wrapper
def create_user(email: str, name: str, team_id: str, role: str, hourly_rate: float = 50.0) -> dict:
    """Backward compatibility wrapper for create_employee"""
    return create_employee(email=email, full_name=name, team_id=team_id, title=role, role=role, hourly_rate=hourly_rate)


def create_project(
    name: str,
    description: str = None,
    github_repo: str = None,
    jira_project_key: str = None,
    notion_database_id: str = None,
    status: str = "active",
    priority: str = "medium",
    target_date: str = None
) -> dict:
    """
    Create a new project in PostgreSQL.
    
    Args:
        name: Project name
        description: Project description
        github_repo: GitHub repository (e.g., company/repo-name)
        jira_project_key: Jira project key (e.g., PROJ)
        notion_database_id: Notion database ID for project tracking
        status: Project status (active, on_hold, completed)
        priority: Priority level (low, medium, high, critical)
        target_date: Target completion date (YYYY-MM-DD)
        
    Returns:
        dict: Success status and project ID
    """
    try:
        input_data = CreateProjectInput(
            name=name,
            description=description,
            github_repo=github_repo,
            jira_project_key=jira_project_key,
            notion_database_id=notion_database_id,
            status=status,
            priority=priority,
            target_date=target_date
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO projects (name, description, github_repo, jira_project_key, notion_database_id, status, priority, target_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        result = client.execute_write_returning(
            query,
            (input_data.name, input_data.description, input_data.github_repo, 
             input_data.jira_project_key, input_data.notion_database_id, input_data.status, input_data.priority, input_data.target_date)
        )
        client.close()
        
        project_id = str(result[0]['id']) if result else None
        
        output = CreateProjectOutput(
            success=True,
            message=f"Created project {name}",
            project_id=project_id,
            name=name
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "project_id": None, "name": name}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "project_id": None, "name": name}


def assign_employee_to_project(
    employee_id: str,
    project_id: str,
    role: str = "contributor",
    allocated_percent: float = 100.0,
    start_date: str = None,
    end_date: str = None
) -> dict:
    """
    Assign an employee to a project with allocation percentage.
    
    Args:
        employee_id: Employee UUID
        project_id: Project UUID
        role: Role on project (lead, contributor, reviewer)
        allocated_percent: Percentage allocation (0-100)
        start_date: Assignment start date (YYYY-MM-DD)
        end_date: Assignment end date (YYYY-MM-DD)
        
    Returns:
        dict: Success status and assignment ID
    """
    try:
        input_data = AssignEmployeeToProjectInput(
            employee_id=UUID(employee_id),
            project_id=UUID(project_id),
            role=role,
            allocated_percent=allocated_percent,
            start_date=start_date,
            end_date=end_date
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO project_assignments (employee_id, project_id, role, allocated_percent, start_date, end_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """
        result = client.execute_write_returning(
            query,
            (str(input_data.employee_id), str(input_data.project_id), input_data.role, 
             input_data.allocated_percent, input_data.start_date, input_data.end_date)
        )
        client.close()
        
        assignment_id = str(result[0]['id']) if result else None
        
        output = AssignEmployeeToProjectOutput(
            success=True,
            message=f"Assigned employee to project with {allocated_percent}% allocation",
            assignment_id=assignment_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "assignment_id": None}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "assignment_id": None}


# Backward compatibility wrapper
def assign_user_to_project(user_id: str, project_id: str, role: str = "contributor", allocated_percent: float = 100.0) -> dict:
    """Backward compatibility wrapper for assign_employee_to_project"""
    return assign_employee_to_project(employee_id=user_id, project_id=project_id, role=role, allocated_percent=allocated_percent)


def add_identity_mapping(
    employee_id: str,
    source: str,
    external_id: str,
    external_username: str = None,
    external_email: str = None
) -> dict:
    """
    Map employee to external identity (GitHub, Jira, Slack, etc.).
    
    Args:
        employee_id: Employee UUID
        source: Source system (github, jira, slack, notion)
        external_id: External ID in that system
        external_username: Username in external system
        external_email: Email in external system
        
    Returns:
        dict: Success status and mapping ID
    """
    try:
        input_data = AddIdentityMappingInput(
            employee_id=UUID(employee_id),
            source=source.lower(),
            external_id=external_id,
            external_username=external_username,
            external_email=external_email
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO identity_mappings (employee_id, source, external_id, external_username, external_email)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        result = client.execute_write_returning(
            query,
            (str(input_data.employee_id), input_data.source, input_data.external_id, 
             input_data.external_username, input_data.external_email)
        )
        client.close()
        
        mapping_id = str(result[0]['id']) if result else None
        
        output = AddIdentityMappingOutput(
            success=True,
            message=f"Added {source} identity mapping for employee",
            mapping_id=mapping_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "mapping_id": None}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "mapping_id": None}


def upsert_embedding(
    embedding_type: str,
    source_id: str,
    source_table: str,
    embedding: List[float] = None,
    text: str = None,
    title: str = "",
    content: str = None,
    metadata: dict = None
) -> dict:
    """
    Upsert a vector embedding for semantic search.
    Can accept pre-computed embedding OR text to embed via Pinecone.
    
    Args:
        embedding_type: Type (developer_profile, project_description)
        source_id: Source record UUID
        source_table: Source table name (users, projects)
        embedding: Pre-computed vector (1536 dims). If not provided, text must be given.
        text: Text to embed using Pinecone inference API. Required if embedding not provided.
        title: Short title for display
        content: Full text content (defaults to text if not provided)
        metadata: Additional metadata as JSON
        
    Returns:
        dict: Success status and embedding ID
    """
    try:
        # Generate embedding from text if not provided
        if embedding is None:
            if text is None:
                return {"success": False, "message": "Either 'embedding' or 'text' must be provided", "embedding_id": None, "dimensions": 0}
            embedding = embed_text(text, input_type="passage")
        
        # Use text as content if content not explicitly provided
        if content is None and text is not None:
            content = text
        
        input_data = UpsertEmbeddingInput(
            embedding_type=embedding_type,
            source_id=UUID(source_id),
            source_table=source_table,
            embedding=embedding,
            text=text,
            title=title,
            content=content,
            metadata=metadata or {}
        )
        
        client = PostgresClient()
        
        # Convert embedding list to pgvector format
        embedding_str = "[" + ",".join(str(x) for x in input_data.embedding) + "]"
        
        query = """
            INSERT INTO embeddings (embedding_type, source_id, source_table, embedding, title, content, metadata)
            VALUES (%s, %s, %s, %s::vector, %s, %s, %s)
            ON CONFLICT (source_id, source_table) 
            DO UPDATE SET 
                embedding_type = EXCLUDED.embedding_type,
                embedding = EXCLUDED.embedding,
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            RETURNING id;
        """
        result = client.execute_write_returning(
            query,
            (input_data.embedding_type, str(input_data.source_id), input_data.source_table, 
             embedding_str, input_data.title, input_data.content, json.dumps(input_data.metadata))
        )
        client.close()
        
        embedding_id = str(result[0]['id']) if result else None
        
        output = UpsertEmbeddingOutput(
            success=True,
            message=f"Upserted embedding for {source_table}/{source_id}" + (" (generated from text)" if text is not None else ""),
            embedding_id=embedding_id,
            dimensions=len(input_data.embedding)
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "embedding_id": None, "dimensions": 0}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "embedding_id": None, "dimensions": 0}


def search_embeddings(
    query_embedding: List[float] = None,
    query_text: str = None,
    embedding_type: str = None,
    limit: int = 10,
    similarity_threshold: float = 0.7
) -> dict:
    """
    Semantic search using pgvector cosine similarity.
    Can accept pre-computed query embedding OR text to embed via Pinecone.
    
    Args:
        query_embedding: Pre-computed query vector (1536 dims). If not provided, query_text must be given.
        query_text: Text to embed as query using Pinecone. Required if query_embedding not provided.
        embedding_type: Filter by type (optional)
        limit: Max results to return (1-50)
        similarity_threshold: Minimum similarity score (0.0-1.0)
        
    Returns:
        dict: List of matching embeddings with similarity scores
    """
    try:
        # Generate query embedding from text if not provided
        if query_embedding is None:
            if query_text is None:
                return {"success": False, "message": "Either 'query_embedding' or 'query_text' must be provided", "matches": [], "total_results": 0}
            query_embedding = embed_text(query_text, input_type="query")
        
        input_data = SearchEmbeddingsInput(
            query_embedding=query_embedding,
            query_text=query_text,
            embedding_type=embedding_type,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        
        client = PostgresClient()
        
        # Convert embedding to pgvector format
        embedding_str = "[" + ",".join(str(x) for x in input_data.query_embedding) + "]"
        
        # Build query with optional type filter and similarity threshold
        if input_data.embedding_type:
            query = """
                SELECT 
                    id, source_id, source_table, title, content, metadata,
                    1 - (embedding <=> %s::vector) as similarity
                FROM embeddings
                WHERE embedding_type = %s
                    AND (1 - (embedding <=> %s::vector)) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            params = (embedding_str, input_data.embedding_type, embedding_str, 
                     input_data.similarity_threshold, embedding_str, input_data.limit)
        else:
            query = """
                SELECT 
                    id, source_id, source_table, title, content, metadata,
                    1 - (embedding <=> %s::vector) as similarity
                FROM embeddings
                WHERE (1 - (embedding <=> %s::vector)) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            params = (embedding_str, embedding_str, input_data.similarity_threshold, embedding_str, input_data.limit)
        
        results = client.execute_query(query, params)
        client.close()
        
        matches = []
        for row in results:
            match = EmbeddingMatch(
                id=str(row['id']),
                source_id=str(row['source_id']),
                source_table=row['source_table'],
                title=row['title'],
                content=row.get('content'),
                metadata=row.get('metadata'),
                similarity=float(row['similarity'])
            )
            matches.append(match)
        
        output = SearchEmbeddingsOutput(
            success=True,
            matches=matches,
            total_results=len(matches)
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}", "matches": [], "total_results": 0}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}", "matches": [], "total_results": 0}


def get_employee_by_email(email: str) -> dict:
    """
    Get employee details by email address.
    
    Args:
        email: Employee's email address
        
    Returns:
        dict: Employee details if found
    """
    try:
        input_data = GetEmployeeByEmailInput(email=email)
        
        client = PostgresClient()
        query = """
            SELECT id, email, full_name, team_id, title, role, hourly_rate, manager_id, location, timezone, active
            FROM employees
            WHERE email = %s;
        """
        results = client.execute_query(query, (input_data.email,))
        client.close()
        
        if results:
            row = results[0]
            employee = EmployeeDetails(
                id=str(row['id']),
                email=row['email'],
                full_name=row['full_name'],
                team_id=str(row['team_id']) if row['team_id'] else None,
                title=row.get('title'),
                role=row.get('role'),
                hourly_rate=float(row['hourly_rate']) if row.get('hourly_rate') else 50.0,
                manager_id=str(row['manager_id']) if row.get('manager_id') else None,
                location=row.get('location'),
                timezone=row.get('timezone'),
                active=row.get('active', True)
            )
            output = GetEmployeeByEmailOutput(
                success=True,
                employee=employee,
                message=f"Found employee {row['full_name']}"
            )
        else:
            output = GetEmployeeByEmailOutput(
                success=False,
                employee=None,
                message=f"Employee with email {email} not found"
            )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "employee": None, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "employee": None, "message": f"Error: {str(e)}"}


# Backward compatibility wrapper
def get_user_by_email(email: str) -> dict:
    """Backward compatibility wrapper for get_employee_by_email"""
    result = get_employee_by_email(email)
    # Map employee -> user for backward compat
    if result.get('employee'):
        result['user'] = result.pop('employee')
        if result['user'].get('full_name'):
            result['user']['name'] = result['user'].get('full_name')
    return result


def get_project_by_id(project_id: str) -> dict:
    """
    Get project details by project ID.
    
    Args:
        project_id: Project UUID
        
    Returns:
        dict: Project details if found
    """
    try:
        input_data = GetProjectByIdInput(project_id=UUID(project_id))
        
        client = PostgresClient()
        query = """
            SELECT id, name, description, github_repo, jira_project_key, notion_database_id, status, priority, target_date
            FROM projects
            WHERE id = %s;
        """
        results = client.execute_query(query, (str(input_data.project_id),))
        client.close()
        
        if results:
            row = results[0]
            project = ProjectDetails(
                id=str(row['id']),
                name=row['name'],
                description=row.get('description'),
                github_repo=row.get('github_repo'),
                jira_project_key=row.get('jira_project_key'),
                notion_database_id=row.get('notion_database_id'),
                status=row['status'],
                priority=row['priority'],
                target_date=str(row['target_date']) if row.get('target_date') else None
            )
            output = GetProjectByIdOutput(
                success=True,
                project=project,
                message=f"Found project {row['name']}"
            )
        else:
            output = GetProjectByIdOutput(
                success=False,
                project=None,
                message=f"Project with ID {project_id} not found"
            )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "project": None, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "project": None, "message": f"Error: {str(e)}"}


def create_task(
    title: str,
    project_id: str,
    assignee_id: Optional[str] = None,
    reporter_id: Optional[str] = None,
    description: Optional[str] = None,
    priority: str = "medium",
    due_date: Optional[str] = None,
    estimated_hours: Optional[float] = None,
    external_id: Optional[str] = None,
    source_system: Optional[str] = None
) -> dict:
    """
    Create a new task in the database.
    
    Args:
        title: Task title
        project_id: UUID of the project
        assignee_id: UUID of assigned employee (optional)
        reporter_id: UUID of reporter employee (optional)
        description: Task description
        priority: low, medium, high, critical
        due_date: Due date (YYYY-MM-DD)
        estimated_hours: Estimated hours to complete
        external_id: External ID (e.g., Jira issue key)
        source_system: Source system (e.g., jira, github)
    
    Returns:
        dict: Created task details
    """
    try:
        input_data = CreateTaskInput(
            title=title,
            project_id=UUID(project_id),
            assignee_id=UUID(assignee_id) if assignee_id else None,
            reporter_id=UUID(reporter_id) if reporter_id else None,
            description=description,
            priority=priority,
            due_date=due_date,
            estimated_hours=estimated_hours,
            external_id=external_id,
            source_system=source_system
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO tasks (title, project_id, assignee_id, reporter_id, description, priority, due_date, estimated_hours, external_id, source_system)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, title, status, created_at;
        """
        results = client.execute_query(query, (
            input_data.title,
            str(input_data.project_id),
            str(input_data.assignee_id) if input_data.assignee_id else None,
            str(input_data.reporter_id) if input_data.reporter_id else None,
            input_data.description,
            input_data.priority,
            input_data.due_date,
            input_data.estimated_hours,
            input_data.external_id,
            input_data.source_system
        ))
        client.close()
        
        if results:
            row = results[0]
            output = CreateTaskOutput(
                success=True,
                task_id=str(row['id']),
                message=f"Created task: {row['title']}"
            )
        else:
            output = CreateTaskOutput(success=False, task_id=None, message="Failed to create task")
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "task_id": None, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "task_id": None, "message": f"Error: {str(e)}"}


def update_task_status(task_id: str, status: str, actor_id: Optional[str] = None) -> dict:
    """
    Update task status and log the event.
    
    Args:
        task_id: UUID of the task
        status: New status (todo, in_progress, in_review, done, blocked, cancelled)
        actor_id: UUID of the employee making the change (optional)
    
    Returns:
        dict: Update confirmation
    """
    try:
        input_data = UpdateTaskStatusInput(
            task_id=UUID(task_id),
            status=status,
            actor_id=UUID(actor_id) if actor_id else None
        )
        
        client = PostgresClient()
        
        # Get old status for event logging
        old_status_query = "SELECT status FROM tasks WHERE id = %s;"
        old_result = client.execute_query(old_status_query, (str(input_data.task_id),))
        old_status = old_result[0]['status'] if old_result else None
        
        # Update task status
        update_query = """
            UPDATE tasks SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, title, status;
        """
        results = client.execute_query(update_query, (input_data.status, str(input_data.task_id)))
        
        # Log task event
        if results and old_status:
            event_query = """
                INSERT INTO task_events (task_id, event_type, old_value, new_value, actor_id)
                VALUES (%s, 'status_change', %s, %s, %s);
            """
            client.execute_query(event_query, (
                str(input_data.task_id),
                old_status,
                input_data.status,
                str(input_data.actor_id) if input_data.actor_id else None
            ))
        
        client.close()
        
        if results:
            row = results[0]
            output = UpdateTaskStatusOutput(
                success=True,
                message=f"Task '{row['title']}' status updated to {row['status']}"
            )
        else:
            output = UpdateTaskStatusOutput(success=False, message=f"Task {task_id} not found")
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


def get_task(task_id: str) -> dict:
    """
    Get task details by ID.
    
    Args:
        task_id: UUID of the task
    
    Returns:
        dict: Task details
    """
    try:
        client = PostgresClient()
        query = """
            SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
                   t.estimated_hours, t.actual_hours, t.external_id, t.source_system,
                   t.created_at, t.updated_at,
                   p.name as project_name,
                   a.full_name as assignee_name,
                   r.full_name as reporter_name
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN employees a ON t.assignee_id = a.id
            LEFT JOIN employees r ON t.reporter_id = r.id
            WHERE t.id = %s;
        """
        results = client.execute_query(query, (task_id,))
        client.close()
        
        if results:
            row = results[0]
            task = TaskDetails(
                id=str(row['id']),
                title=row['title'],
                description=row.get('description'),
                status=row['status'],
                priority=row['priority'],
                due_date=str(row['due_date']) if row.get('due_date') else None,
                estimated_hours=row.get('estimated_hours'),
                actual_hours=row.get('actual_hours'),
                assignee_name=row.get('assignee_name'),
                reporter_name=row.get('reporter_name'),
                project_name=row.get('project_name'),
                external_id=row.get('external_id'),
                source_system=row.get('source_system'),
                created_at=str(row['created_at']),
                updated_at=str(row['updated_at']) if row.get('updated_at') else None
            )
            output = GetTaskOutput(success=True, task=task, message="Task found")
        else:
            output = GetTaskOutput(success=False, task=None, message=f"Task {task_id} not found")
        
        return output.model_dump()
        
    except Exception as e:
        return {"success": False, "task": None, "message": f"Error: {str(e)}"}


def log_check_in(
    employee_id: str,
    check_in_type: str,
    mood_score: Optional[int] = None,
    blockers: Optional[str] = None,
    accomplishments: Optional[str] = None,
    goals_today: Optional[str] = None,
    notes: Optional[str] = None
) -> dict:
    """
    Log a daily check-in for an employee.
    
    Args:
        employee_id: UUID of the employee
        check_in_type: daily, weekly, or adhoc
        mood_score: 1-5 mood rating (optional)
        blockers: Current blockers
        accomplishments: Recent accomplishments
        goals_today: Goals for today
        notes: Additional notes
    
    Returns:
        dict: Created check-in details
    """
    try:
        input_data = LogCheckInInput(
            employee_id=UUID(employee_id),
            check_in_type=check_in_type,
            mood_score=mood_score,
            blockers=blockers,
            accomplishments=accomplishments,
            goals_today=goals_today,
            notes=notes
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO check_ins (employee_id, check_in_type, mood_score, blockers, accomplishments, goals_today, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, check_in_type, created_at;
        """
        results = client.execute_query(query, (
            str(input_data.employee_id),
            input_data.check_in_type,
            input_data.mood_score,
            input_data.blockers,
            input_data.accomplishments,
            input_data.goals_today,
            input_data.notes
        ))
        client.close()
        
        if results:
            row = results[0]
            output = LogCheckInOutput(
                success=True,
                check_in_id=str(row['id']),
                message=f"Logged {row['check_in_type']} check-in"
            )
        else:
            output = LogCheckInOutput(success=False, check_in_id=None, message="Failed to log check-in")
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "check_in_id": None, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "check_in_id": None, "message": f"Error: {str(e)}"}


def get_employee_check_ins(employee_id: str, limit: int = 10) -> dict:
    """
    Get recent check-ins for an employee.
    
    Args:
        employee_id: UUID of the employee
        limit: Maximum number of check-ins to return
    
    Returns:
        dict: List of check-ins
    """
    try:
        client = PostgresClient()
        query = """
            SELECT c.id, c.check_in_type, c.mood_score, c.blockers, c.accomplishments,
                   c.goals_today, c.notes, c.created_at,
                   e.full_name as employee_name
            FROM check_ins c
            JOIN employees e ON c.employee_id = e.id
            WHERE c.employee_id = %s
            ORDER BY c.created_at DESC
            LIMIT %s;
        """
        results = client.execute_query(query, (employee_id, limit))
        client.close()
        
        check_ins = []
        for row in results:
            check_ins.append(CheckInDetails(
                id=str(row['id']),
                employee_name=row['employee_name'],
                check_in_type=row['check_in_type'],
                mood_score=row.get('mood_score'),
                blockers=row.get('blockers'),
                accomplishments=row.get('accomplishments'),
                goals_today=row.get('goals_today'),
                notes=row.get('notes'),
                created_at=str(row['created_at'])
            ))
        
        output = GetCheckInsOutput(
            success=True,
            check_ins=check_ins,
            message=f"Found {len(check_ins)} check-ins"
        )
        return output.model_dump()
        
    except Exception as e:
        return {"success": False, "check_ins": [], "message": f"Error: {str(e)}"}


def add_feedback(
    from_employee_id: str,
    to_employee_id: str,
    feedback_type: str,
    content: str,
    visibility: str = "private",
    related_task_id: Optional[str] = None
) -> dict:
    """
    Add feedback from one employee to another.
    
    Args:
        from_employee_id: UUID of employee giving feedback
        to_employee_id: UUID of employee receiving feedback
        feedback_type: praise, constructive, review, peer
        content: Feedback content
        visibility: private, manager_only, public
        related_task_id: UUID of related task (optional)
    
    Returns:
        dict: Created feedback details
    """
    try:
        input_data = AddFeedbackInput(
            from_employee_id=UUID(from_employee_id),
            to_employee_id=UUID(to_employee_id),
            feedback_type=feedback_type,
            content=content,
            visibility=visibility,
            related_task_id=UUID(related_task_id) if related_task_id else None
        )
        
        client = PostgresClient()
        query = """
            INSERT INTO feedback (from_employee_id, to_employee_id, feedback_type, content, visibility, related_task_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, feedback_type, created_at;
        """
        results = client.execute_query(query, (
            str(input_data.from_employee_id),
            str(input_data.to_employee_id),
            input_data.feedback_type,
            input_data.content,
            input_data.visibility,
            str(input_data.related_task_id) if input_data.related_task_id else None
        ))
        client.close()
        
        if results:
            row = results[0]
            output = AddFeedbackOutput(
                success=True,
                feedback_id=str(row['id']),
                message=f"Added {row['feedback_type']} feedback"
            )
        else:
            output = AddFeedbackOutput(success=False, feedback_id=None, message="Failed to add feedback")
        
        return output.model_dump()
        
    except ValidationError as e:
        return {"success": False, "feedback_id": None, "message": f"Validation error: {str(e)}"}
    except Exception as e:
        return {"success": False, "feedback_id": None, "message": f"Error: {str(e)}"}


def get_employee_feedback(employee_id: str, direction: str = "received", limit: int = 10) -> dict:
    """
    Get feedback for an employee.
    
    Args:
        employee_id: UUID of the employee
        direction: 'received' or 'given'
        limit: Maximum number of feedback entries to return
    
    Returns:
        dict: List of feedback entries
    """
    try:
        client = PostgresClient()
        
        if direction == "received":
            query = """
                SELECT f.id, f.feedback_type, f.content, f.visibility, f.created_at,
                       fe.full_name as from_employee_name,
                       te.full_name as to_employee_name,
                       t.title as task_title
                FROM feedback f
                JOIN employees fe ON f.from_employee_id = fe.id
                JOIN employees te ON f.to_employee_id = te.id
                LEFT JOIN tasks t ON f.related_task_id = t.id
                WHERE f.to_employee_id = %s
                ORDER BY f.created_at DESC
                LIMIT %s;
            """
        else:
            query = """
                SELECT f.id, f.feedback_type, f.content, f.visibility, f.created_at,
                       fe.full_name as from_employee_name,
                       te.full_name as to_employee_name,
                       t.title as task_title
                FROM feedback f
                JOIN employees fe ON f.from_employee_id = fe.id
                JOIN employees te ON f.to_employee_id = te.id
                LEFT JOIN tasks t ON f.related_task_id = t.id
                WHERE f.from_employee_id = %s
                ORDER BY f.created_at DESC
                LIMIT %s;
            """
        
        results = client.execute_query(query, (employee_id, limit))
        client.close()
        
        feedback_list = []
        for row in results:
            feedback_list.append(FeedbackDetails(
                id=str(row['id']),
                from_employee_name=row['from_employee_name'],
                to_employee_name=row['to_employee_name'],
                feedback_type=row['feedback_type'],
                content=row['content'],
                visibility=row['visibility'],
                task_title=row.get('task_title'),
                created_at=str(row['created_at'])
            ))
        
        output = GetFeedbackOutput(
            success=True,
            feedback=feedback_list,
            message=f"Found {len(feedback_list)} feedback entries ({direction})"
        )
        return output.model_dump()
        
    except Exception as e:
        return {"success": False, "feedback": [], "message": f"Error: {str(e)}"}


# ==============================================================================
# LANGCHAIN STRUCTURED TOOLS
# ==============================================================================

postgres_tools = [
    # Employee Management (new unified schema)
    StructuredTool.from_function(
        func=create_employee,
        name="create_employee",
        description="Create a new employee in PostgreSQL. Use when onboarding new team members.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=assign_employee_to_project,
        name="assign_employee_to_project",
        description="Assign an employee to a project with allocation percentage. Use for project staffing.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_employee_by_email,
        name="get_employee_by_email",
        description="Look up employee by email address. Use to find employee UUID and details.",
        return_direct=False
    ),
    
    # Project Management
    StructuredTool.from_function(
        func=create_project,
        name="create_project",
        description="Create a new project in PostgreSQL. Use when starting new projects.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_project_by_id,
        name="get_project_by_id",
        description="Get project details by UUID. Use to fetch project information.",
        return_direct=False
    ),
    
    # Identity Mapping
    StructuredTool.from_function(
        func=add_identity_mapping,
        name="add_identity_mapping",
        description="Map employee to external system (GitHub, Jira, Slack). Use when linking external identities.",
        return_direct=False
    ),
    
    # Task Management
    StructuredTool.from_function(
        func=create_task,
        name="create_task",
        description="Create a new task in a project. Use when adding tasks from Jira or manually.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=update_task_status,
        name="update_task_status",
        description="Update task status and log the event. Use when tasks transition states.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_task,
        name="get_task",
        description="Get task details by ID. Use to fetch task information.",
        return_direct=False
    ),
    
    # Check-ins
    StructuredTool.from_function(
        func=log_check_in,
        name="log_check_in",
        description="Log a daily/weekly check-in for an employee. Records mood, blockers, accomplishments.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_employee_check_ins,
        name="get_employee_check_ins",
        description="Get recent check-ins for an employee. Use to review employee status history.",
        return_direct=False
    ),
    
    # Feedback
    StructuredTool.from_function(
        func=add_feedback,
        name="add_feedback",
        description="Add feedback from one employee to another. Supports praise, constructive, review types.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_employee_feedback,
        name="get_employee_feedback",
        description="Get feedback for an employee (received or given). Use to review feedback history.",
        return_direct=False
    ),
    
    # Vector Embeddings
    StructuredTool.from_function(
        func=upsert_embedding,
        name="upsert_embedding",
        description="Store vector embedding for semantic search. Use after generating embeddings.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=search_embeddings,
        name="search_embeddings",
        description="Semantic search using pgvector. Use to find similar employees/projects.",
        return_direct=False
    ),
    
    # Backward compatibility aliases (use new functions internally)
    StructuredTool.from_function(
        func=create_user,
        name="create_user",
        description="[Legacy] Create a new user - use create_employee instead.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=assign_user_to_project,
        name="assign_user_to_project",
        description="[Legacy] Assign user to project - use assign_employee_to_project instead.",
        return_direct=False
    ),
    StructuredTool.from_function(
        func=get_user_by_email,
        name="get_user_by_email",
        description="[Legacy] Look up user by email - use get_employee_by_email instead.",
        return_direct=False
    ),
]
