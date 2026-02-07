"""
Neo4j tools with Pydantic validation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_core.tools import StructuredTool
from pydantic import ValidationError
import json

from neo4j_db.neo4j_client import Neo4jClient
from agent.schemas.tool_schemas import (
    CreateDeveloperInput,
    CreateDeveloperOutput,
    AddSkillInput,
    AddSkillOutput,
    AddContributionInput,
    AddContributionOutput,
    CreateProjectDependencyInput,
    CreateProjectDependencyOutput,
    FindDevelopersInput,
    FindDevelopersOutput,
    DeveloperMatch
)


def create_developer_node(
    email: str,
    name: str,
    team_id: str
) -> dict:
    """
    Create a new developer node in Neo4j graph.
    
    Args:
        email: Developer's email address (unique identifier)
        name: Developer's full name
        team_id: Team identifier the developer belongs to
    
    Returns:
        dict: Success status and details
    """
    try:
        # Validate input
        input_data = CreateDeveloperInput(
            email=email,
            name=name,
            team_id=team_id
        )
        
        # Execute Neo4j query
        client = Neo4jClient()
        result = client.execute_write("""
            CREATE (d:Developer {
                email: $email,
                name: $name,
                team_id: $team_id,
                created_at: datetime()
            })
            RETURN d.email as email, elementId(d) as node_id
        """, {
            "email": input_data.email,
            "name": input_data.name,
            "team_id": input_data.team_id
        })
        
        client.close()
        
        # Validate and return output
        if result:
            output = CreateDeveloperOutput(
                success=True,
                message=f"Created developer node for {name}",
                developer_email=email,
                node_id=result[0].get('node_id')
            )
        else:
            output = CreateDeveloperOutput(
                success=False,
                message="Failed to create developer node",
                developer_email=email
            )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "developer_email": email
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "developer_email": email
        }


def add_skill_relationship(
    developer_email: str,
    skill_name: str,
    proficiency: str
) -> dict:
    """
    Add a skill to a developer in Neo4j graph.
    
    Args:
        developer_email: Developer's email address
        skill_name: Name of the skill (e.g., Python, React, FastAPI)
        proficiency: Skill level (beginner, intermediate, advanced, expert)
    
    Returns:
        dict: Success status and details
    """
    try:
        # Validate input
        input_data = AddSkillInput(
            developer_email=developer_email,
            skill_name=skill_name,
            proficiency=proficiency
        )
        
        # Execute Neo4j query
        client = Neo4jClient()
        client.execute_write("""
            MATCH (d:Developer {email: $email})
            MERGE (s:Skill {name: $skill})
            MERGE (d)-[r:HAS_SKILL]->(s)
            ON CREATE SET 
                r.proficiency = $proficiency,
                r.added_at = datetime()
            ON MATCH SET 
                r.proficiency = $proficiency,
                r.updated_at = datetime()
        """, {
            "email": input_data.developer_email,
            "skill": input_data.skill_name,
            "proficiency": input_data.proficiency.value
        })
        
        client.close()
        
        # Return validated output
        output = AddSkillOutput(
            success=True,
            message=f"Added {skill_name} ({proficiency}) to {developer_email}",
            skill_name=skill_name,
            proficiency=proficiency
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "skill_name": skill_name,
            "proficiency": proficiency
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "skill_name": skill_name,
            "proficiency": proficiency
        }


def add_contribution_relationship(
    developer_email: str,
    project_id: str,
    commits: int = 0,
    prs: int = 0,
    reviews: int = 0
) -> dict:
    """
    Record developer contribution to a project in Neo4j.
    
    Args:
        developer_email: Developer's email address
        project_id: Project identifier
        commits: Number of commits
        prs: Number of pull requests
        reviews: Number of code reviews
    
    Returns:
        dict: Success status and details
    """
    try:
        # Validate input
        from agent.schemas.tool_schemas import ContributionMetrics
        
        metrics = ContributionMetrics(
            commits=commits,
            prs=prs,
            reviews=reviews
        )
        
        input_data = AddContributionInput(
            developer_email=developer_email,
            project_id=project_id,
            metrics=metrics
        )
        
        # Execute Neo4j query
        client = Neo4jClient()
        client.execute_write("""
            MATCH (d:Developer {email: $email})
            MERGE (p:Project {id: $project_id})
            MERGE (d)-[r:CONTRIBUTES_TO]->(p)
            ON CREATE SET
                r.commits = $commits,
                r.prs = $prs,
                r.reviews = $reviews,
                r.first_contribution = datetime()
            ON MATCH SET
                r.commits = r.commits + $commits,
                r.prs = r.prs + $prs,
                r.reviews = r.reviews + $reviews,
                r.last_contribution = datetime()
        """, {
            "email": input_data.developer_email,
            "project_id": input_data.project_id,
            "commits": metrics.commits,
            "prs": metrics.prs,
            "reviews": metrics.reviews
        })
        
        client.close()
        
        # Return validated output
        output = AddContributionOutput(
            success=True,
            message=f"Updated contribution for {developer_email} on {project_id}",
            developer_email=developer_email,
            project_id=project_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "developer_email": developer_email,
            "project_id": project_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "developer_email": developer_email,
            "project_id": project_id
        }


def create_project_dependency(
    project_id: str,
    depends_on_id: str,
    dependency_type: str
) -> dict:
    """
    Create dependency relationship between projects in Neo4j.
    
    Args:
        project_id: Project that depends on another
        depends_on_id: Project being depended on
        dependency_type: Type of dependency (blocking, optional, required)
    
    Returns:
        dict: Success status and details
    """
    try:
        # Validate input
        input_data = CreateProjectDependencyInput(
            project_id=project_id,
            depends_on_id=depends_on_id,
            dependency_type=dependency_type
        )
        
        # Execute Neo4j query
        client = Neo4jClient()
        client.execute_write("""
            MERGE (p1:Project {id: $project_id})
            MERGE (p2:Project {id: $depends_on_id})
            MERGE (p1)-[r:DEPENDS_ON]->(p2)
            SET r.type = $dep_type,
                r.created_at = datetime()
        """, {
            "project_id": input_data.project_id,
            "depends_on_id": input_data.depends_on_id,
            "dep_type": input_data.dependency_type.value
        })
        
        client.close()
        
        # Return validated output
        output = CreateProjectDependencyOutput(
            success=True,
            message=f"Created {dependency_type} dependency: {project_id} → {depends_on_id}",
            from_project=project_id,
            to_project=depends_on_id
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "message": f"Validation error: {str(e)}",
            "from_project": project_id,
            "to_project": depends_on_id
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "from_project": project_id,
            "to_project": depends_on_id
        }


def find_available_developers(
    skill: str,
    min_availability: float = 0.3
) -> dict:
    """
    Find developers with specific skill and availability in Neo4j.
    Use this when you need to suggest developers for a task.
    
    Args:
        skill: Required skill name (e.g., Python, React)
        min_availability: Minimum availability threshold (0.0-1.0)
    
    Returns:
        dict: List of available developers with details
    """
    try:
        # Validate input
        input_data = FindDevelopersInput(
            skill=skill,
            min_availability=min_availability
        )
        
        # Execute Neo4j query
        client = Neo4jClient()
        results = client.execute_read("""
            MATCH (d:Developer)-[hs:HAS_SKILL]->(s:Skill {name: $skill})
            OPTIONAL MATCH (d)-[:CONTRIBUTES_TO]->(p:Project)
            WITH d, hs.proficiency as proficiency, COUNT(p) as project_count
            WHERE project_count < 3  // Simple availability heuristic
            OPTIONAL MATCH (d)-[:HAS_SKILL]->(all_skills:Skill)
            WITH d, proficiency, project_count, COLLECT(all_skills.name) as skills
            OPTIONAL MATCH (d)-[:CONTRIBUTES_TO]->(projects:Project)
            WITH d, proficiency, skills, project_count, COLLECT(projects.id) as current_projects
            RETURN 
                d.email as email,
                d.name as name,
                (3 - project_count) / 3.0 as availability,
                proficiency,
                skills,
                current_projects
            ORDER BY availability DESC, proficiency DESC
            LIMIT 10
        """, {"skill": input_data.skill})
        
        client.close()
        
        # Parse results
        matches = []
        for record in results:
            match = DeveloperMatch(
                email=record['email'],
                name=record['name'],
                availability=record['availability'],
                skills=record['skills'],
                current_projects=record['current_projects']
            )
            matches.append(match)
        
        # Filter by minimum availability
        filtered_matches = [m for m in matches if m.availability >= input_data.min_availability]
        
        # Return validated output
        output = FindDevelopersOutput(
            success=True,
            matches=filtered_matches,
            total_found=len(filtered_matches)
        )
        
        return output.model_dump()
        
    except ValidationError as e:
        return {
            "success": False,
            "matches": [],
            "total_found": 0,
            "message": f"Validation error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "matches": [],
            "total_found": 0,
            "message": f"Error: {str(e)}"
        }


# ==============================================================================
# LANGCHAIN STRUCTURED TOOLS
# ==============================================================================

# Create LangChain tools with Pydantic schemas
neo4j_tools = [
    StructuredTool.from_function(
        func=create_developer_node,
        name="create_developer_node",
        description="Create a new developer node in Neo4j graph database. Use when a new developer joins the team.",
        args_schema=CreateDeveloperInput,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=add_skill_relationship,
        name="add_skill_relationship",
        description="Add a skill to a developer in Neo4j. Use when recording developer skills or updating proficiency.",
        args_schema=AddSkillInput,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=add_contribution_relationship,
        name="add_contribution_relationship",
        description="Record developer contribution to a project. Use when processing GitHub commits, PRs, or reviews.",
        # Note: We can't use AddContributionInput directly because of nested model
        return_direct=False
    ),
    StructuredTool.from_function(
        func=create_project_dependency,
        name="create_project_dependency",
        description="Create dependency between projects. Use when one project depends on another.",
        args_schema=CreateProjectDependencyInput,
        return_direct=False
    ),
    StructuredTool.from_function(
        func=find_available_developers,
        name="find_available_developers",
        description="Find developers with a specific skill who have capacity. Use for task assignment recommendations.",
        args_schema=FindDevelopersInput,
        return_direct=False
    )
]
