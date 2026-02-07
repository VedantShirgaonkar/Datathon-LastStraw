# Kafka-to-Database Agent Architecture Plan

> **AI Agent with Featherless AI + LangChain + LangGraph**
>
> Consumes Kafka events → Uses LLM to decide actions → Calls database tools

---

## 🎯 Project Overview

**Agent Purpose:**
- Consume events from Apache Kafka stream
- Use Featherless AI LLM (Qwen3-32B) to understand events
- Make intelligent decisions with tool calling
- Execute database operations (Neo4j, ClickHouse, PostgreSQL, Pinecone)
- Send notifications and trigger workflows

**Tech Stack:**
- **LLM**: Featherless AI (Qwen3-32B) - Native tool calling support
- **Embeddings**: Pinecone Inference API - Generate embeddings via Pinecone
- **Orchestration**: LangGraph (state machine for agent)
- **Framework**: LangChain (tool management)
- **Streaming**: Apache Kafka consumer
- **Databases**: Neo4j, ClickHouse, PostgreSQL, Pinecone

---

## 📁 Project Structure

```
agent/
├── __init__.py
├── config.py                      # Agent configuration
├── kafka_consumer.py              # Kafka event consumer
├── agent.py                       # Main agent with LangGraph
├── tools/
│   ├── __init__.py
│   ├── neo4j_tools.py             # Neo4j operations (12 tools)
│   ├── clickhouse_tools.py        # ClickHouse operations (8 tools)
│   ├── postgres_tools.py          # PostgreSQL operations (10 tools)
│   ├── pinecone_tools.py          # Vector operations (5 tools)
│   ├── notification_tools.py      # Slack/Email notifications (3 tools)
│   └── jira_tools.py              # Jira integration (4 tools)
├── prompts/
│   ├── system_prompt.py           # Agent system prompt
│   └── event_classifier.py        # Event classification prompts
├── models/
│   ├── event_models.py            # Pydantic models for events
│   └── response_models.py         # Response schemas
└── utils/
    ├── featherless_client.py      # Featherless AI wrapper
    └── state_manager.py           # LangGraph state management

tests/
├── test_tools.py
├── test_agent.py
└── test_kafka.py

docker/
├── docker-compose.yml             # Kafka + Zookeeper (if local)
└── Dockerfile                     # Agent containerization
```

---

## 🔧 Agent Architecture (LangGraph)

```
┌─────────────────────────────────────────────────────────────────┐
│                     KAFKA EVENT STREAM                          │
│          (GitHub commits, Jira updates, metrics)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    KAFKA CONSUMER                               │
│              Deserializes event → JSON                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   LANGGRAPH AGENT                               │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STATE: EventClassifier                                 │   │
│  │  ↓                                                       │   │
│  │  LLM classifies event type and intent                   │   │
│  │  → "github_commit" | "jira_issue_update" | etc          │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STATE: ToolSelector                                    │   │
│  │  ↓                                                       │   │
│  │  LLM selects tools needed (with Featherless AI)        │   │
│  │  → [insert_event_clickhouse, update_neo4j_graph]       │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STATE: ToolExecutor                                    │   │
│  │  ↓                                                       │   │
│  │  Execute tools in parallel (async)                      │   │
│  │  → Insert to ClickHouse + Update Neo4j                  │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  STATE: ResponseGenerator                               │   │
│  │  ↓                                                       │   │
│  │  LLM summarizes actions taken                           │   │
│  │  → "Stored commit event, updated Alice's graph"        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │  Log Result   │
                    └───────────────┘
```

---

## 🛠️ Tool Definitions (42 Total Tools)

### 1. Neo4j Tools (12 tools)

```python
# neo4j_tools.py

from langchain.tools import tool
from neo4j.neo4j_client import Neo4jClient

@tool
def create_developer_node(email: str, name: str, team_id: str) -> str:
    """
    Create a new developer node in Neo4j.
    
    Args:
        email: Developer email (unique)
        name: Developer full name
        team_id: Team identifier
    
    Returns:
        Success message with node details
    """
    client = Neo4jClient()
    result = client.execute_write("""
        CREATE (d:Developer {
            email: $email,
            name: $name,
            team_id: $team_id,
            created_at: datetime()
        })
        RETURN d
    """, email=email, name=name, team_id=team_id)
    client.close()
    return f"Created developer node for {name} ({email})"

@tool
def add_skill_relationship(developer_email: str, skill_name: str, proficiency: str) -> str:
    """
    Add a skill to a developer in Neo4j graph.
    
    Args:
        developer_email: Developer's email
        skill_name: Name of the skill (e.g., Python, React)
        proficiency: Skill level (beginner, intermediate, expert)
    
    Returns:
        Success message
    """
    client = Neo4jClient()
    client.execute_write("""
        MATCH (d:Developer {email: $email})
        MERGE (s:Skill {name: $skill})
        MERGE (d)-[r:HAS_SKILL]->(s)
        ON CREATE SET r.proficiency = $proficiency, r.added_at = datetime()
        ON MATCH SET r.proficiency = $proficiency, r.updated_at = datetime()
    """, email=developer_email, skill=skill_name, proficiency=proficiency)
    client.close()
    return f"Added {skill_name} ({proficiency}) to {developer_email}"

@tool
def add_contribution_relationship(developer_email: str, project_id: str, metrics: dict) -> str:
    """
    Record developer contribution to a project.
    
    Args:
        developer_email: Developer's email
        project_id: Project identifier
        metrics: Dictionary with commits, prs, reviews counts
    
    Returns:
        Success message
    """
    client = Neo4jClient()
    client.execute_write("""
        MATCH (d:Developer {email: $email})
        MATCH (p:Project {id: $project_id})
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
    """, email=developer_email, project_id=project_id, **metrics)
    client.close()
    return f"Updated contribution for {developer_email} on {project_id}"

@tool
def create_project_dependency(project_id: str, depends_on_id: str, dependency_type: str) -> str:
    """
    Create dependency relationship between projects.
    
    Args:
        project_id: Project that depends
        depends_on_id: Project being depended on
        dependency_type: Type (blocking, optional, required)
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def find_available_developers(skill: str, min_availability: float = 0.3) -> str:
    """
    Find developers with specific skill and availability.
    Use this when you need to suggest developers for a task.
    
    Args:
        skill: Required skill name
        min_availability: Minimum availability (0.0-1.0)
    
    Returns:
        JSON list of available developers
    """
    # Implementation with actual query
    pass

# ... 7 more Neo4j tools (get_team_structure, find_project_dependencies, etc.)
```

---

### 2. ClickHouse Tools (8 tools)

```python
# clickhouse_tools.py

from langchain.tools import tool
from clickhouse.clickhouse_client import ClickHouseClient

@tool
def insert_commit_event(project_id: str, developer_email: str, commit_data: dict) -> str:
    """
    Insert GitHub commit event into ClickHouse.
    
    Args:
        project_id: Project identifier
        developer_email: Developer who made the commit
        commit_data: Dict with sha, message, files_changed, lines_added, lines_deleted
    
    Returns:
        Success message with event ID
    """
    client = ClickHouseClient()
    client.insert_event({
        'source': 'github',
        'event_type': 'commit',
        'project_id': project_id,
        'actor_id': developer_email,
        'entity_id': commit_data['sha'],
        'entity_type': 'commit',
        'metadata': commit_data
    })
    client.close()
    return f"Inserted commit event for {developer_email} on {project_id}"

@tool
def insert_pr_event(project_id: str, developer_email: str, pr_data: dict) -> str:
    """
    Insert GitHub PR event (opened, merged, reviewed).
    
    Args:
        project_id: Project identifier
        developer_email: Developer email
        pr_data: Dict with pr_number, action, review_time_hours, lines_changed
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def insert_jira_event(project_id: str, developer_email: str, issue_data: dict) -> str:
    """
    Insert Jira issue event into ClickHouse.
    
    Args:
        project_id: Project key
        developer_email: User who triggered event
        issue_data: Dict with issue_key, event_type, status_from, status_to, story_points
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def get_developer_activity_summary(developer_email: str, days: int = 30) -> str:
    """
    Get developer activity summary from ClickHouse.
    Use this to check workload before assigning new tasks.
    
    Args:
        developer_email: Developer's email
        days: Number of days to look back
    
    Returns:
        JSON with commits, prs, reviews counts
    """
    client = ClickHouseClient()
    activity = client.get_developer_activity(developer_email, days)
    client.close()
    return json.dumps(activity)

@tool
def get_project_dora_metrics(project_id: str, days: int = 30) -> str:
    """
    Get DORA metrics for a project.
    Use this to assess project health.
    
    Args:
        project_id: Project identifier
        days: Number of days for metrics
    
    Returns:
        JSON with deployment frequency, lead time, etc.
    """
    # Implementation
    pass

# ... 3 more ClickHouse tools
```

---

### 3. PostgreSQL Tools (10 tools)

```python
# postgres_tools.py

from langchain.tools import tool
from postgres.postgres_client import PostgresClient

@tool
def create_user_profile(email: str, name: str, team_id: str, skills: list) -> str:
    """
    Create user profile in PostgreSQL.
    
    Args:
        email: User email (unique)
        name: Full name
        team_id: Team identifier
        skills: List of skill names
    
    Returns:
        Success message with user ID
    """
    # Implementation
    pass

@tool
def update_user_skills(email: str, skills: list) -> str:
    """
    Update user's skill list.
    
    Args:
        email: User email
        skills: Updated list of skills
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def find_similar_developers(skill_description: str, top_k: int = 5) -> str:
    """
    Find developers with similar skills using pgvector.
    Use this for skill-based task assignment.
    
    Args:
        skill_description: Description of required skills
        top_k: Number of matches to return
    
    Returns:
        JSON list of matching developers with similarity scores
    """
    # Implementation with pgvector similarity search
    pass

@tool
def get_user_by_email(email: str) -> str:
    """
    Get user details from PostgreSQL.
    
    Args:
        email: User email
    
    Returns:
        JSON with user details
    """
    # Implementation
    pass

# ... 6 more PostgreSQL tools
```

---

### 4. Pinecone Tools (5 tools)

```python
# pinecone_tools.py

from langchain.tools import tool
from pinecone import Pinecone

@tool
def upsert_developer_embedding(developer_email: str, profile_text: str) -> str:
    """
    Generate and store developer profile embedding in Pinecone.
    Uses Pinecone's inference API for embeddings.
    
    Args:
        developer_email: Developer email (used as ID)
        profile_text: Text summary of skills, projects, experience
    
    Returns:
        Success message
    """
    # Initialize Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index("engineering-intelligence")
    
    # Generate embedding using Pinecone's inference API
    embedding_response = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[profile_text],
        parameters={"input_type": "passage"}
    )
    embedding = embedding_response[0].values
    
    # Store in Pinecone
    index.upsert(
        vectors=[{
            'id': developer_email,
            'values': embedding,
            'metadata': {'email': developer_email, 'text': profile_text}
        }],
        namespace='developer_profiles'
    )
    
    return f"Embedded and stored profile for {developer_email}"

@tool
def search_similar_developers_vector(query: str, top_k: int = 5) -> str:
    """
    Semantic search for developers using Pinecone.
    Better than keyword search for skill matching.
    
    Args:
        query: Natural language query (e.g., "expert in React and Node.js")
        top_k: Number of results
    
    Returns:
        JSON list of matching developers
    """
    # Initialize Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index("engineering-intelligence")
    
    # Generate query embedding
    embedding_response = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[query],
        parameters={"input_type": "query"}
    )
    query_embedding = embedding_response[0].values
    
    # Search
    results = index.query(
        namespace="developer_profiles",
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True
    )
    
    return json.dumps([{
        'email': match.metadata['email'],
        'score': match.score
    } for match in results.matches])

# ... 3 more Pinecone tools
```

---

### 5. Notification Tools (3 tools)

```python
# notification_tools.py

from langchain.tools import tool
import requests

@tool
def send_slack_notification(channel: str, message: str) -> str:
    """
    Send notification to Slack channel.
    
    Args:
        channel: Slack channel name or user email
        message: Message to send
    
    Returns:
        Success message
    """
    # Implementation with Slack API
    pass

@tool
def send_email_notification(to: str, subject: str, body: str) -> str:
    """
    Send email notification.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body (plain text)
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def create_github_comment(repo: str, pr_number: int, comment: str) -> str:
    """
    Post comment on GitHub PR.
    
    Args:
        repo: Repository name (owner/repo)
        pr_number: PR number
        comment: Comment text
    
    Returns:
        Success message
    """
    # Implementation
    pass
```

---

### 6. Jira Tools (4 tools)

```python
# jira_tools.py

from langchain.tools import tool
import requests

@tool
def assign_jira_issue(issue_key: str, assignee_email: str) -> str:
    """
    Assign Jira issue to a developer.
    
    Args:
        issue_key: Jira issue key (e.g., PROJ-123)
        assignee_email: Assignee email
    
    Returns:
        Success message
    """
    # Implementation with Jira API
    pass

@tool
def add_jira_comment(issue_key: str, comment: str) -> str:
    """
    Add comment to Jira issue.
    
    Args:
        issue_key: Jira issue key
        comment: Comment text
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def update_jira_status(issue_key: str, status: str) -> str:
    """
    Update Jira issue status.
    
    Args:
        issue_key: Issue key
        status: New status (To Do, In Progress, Done)
    
    Returns:
        Success message
    """
    # Implementation
    pass

@tool
def get_unassigned_issues(project_key: str) -> str:
    """
    Get list of unassigned issues in a project.
    
    Args:
        project_key: Jira project key
    
    Returns:
        JSON list of unassigned issues
    """
    # Implementation
    pass
```

---

## 🤖 Agent Implementation (LangGraph)

### Main Agent File

```python
# agent/agent.py

from langchain_featherless_ai import ChatFeatherlessAi
from langgraph.graph import StateGraph, END
from langchain.tools import tool
from typing import TypedDict, Annotated, Sequence
import operator
from pinecone import Pinecone

# Import all tools
from tools.neo4j_tools import *
from tools.clickhouse_tools import *
from tools.postgres_tools import *
from tools.pinecone_tools import *
from tools.notification_tools import *
from tools.jira_tools import *

# Define agent state
class AgentState(TypedDict):
    """State that persists through agent execution"""
    event: dict  # Kafka event
    event_type: str  # Classified event type
    tool_calls: Sequence[dict]  # Tools to call
    tool_results: Sequence[dict]  # Results from tools
    response: str  # Final response
    errors: Sequence[str]  # Any errors

# Initialize Featherless AI LLM
llm = ChatFeatherlessAi(
    api_key=FEATHERLESS_API_KEY,
    base_url="https://api.featherless.ai/v1",
    model="Qwen/Qwen3-32B",  # Supports native tool calling
    temperature=0.1
)

# Collect all tools
ALL_TOOLS = [
    # Neo4j tools
    create_developer_node,
    add_skill_relationship,
    add_contribution_relationship,
    find_available_developers,
    # ClickHouse tools
    insert_commit_event,
    insert_pr_event,
    insert_jira_event,
    get_developer_activity_summary,
    # PostgreSQL tools
    create_user_profile,
    find_similar_developers,
    # Pinecone tools
    upsert_developer_embedding,
    search_similar_developers_vector,
    # Notification tools
    send_slack_notification,
    send_email_notification,
    # Jira tools
    assign_jira_issue,
    add_jira_comment,
]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(ALL_TOOLS)

# Define agent nodes
def classify_event(state: AgentState) -> AgentState:
    """
    LLM classifies the Kafka event type and determines intent.
    """
    event = state['event']
    
    prompt = f"""
    You are an event classifier for an engineering intelligence platform.
    
    Analyze this event and determine:
    1. Event source (github, jira, notion, prometheus)
    2. Event type (commit, pr_merged, issue_updated, etc.)
    3. Primary entity (developer email, project ID)
    
    Event data:
    {json.dumps(event, indent=2)}
    
    Respond with JSON:
    {{
        "source": "github",
        "event_type": "commit",
        "developer_email": "alice@company.com",
        "project_id": "proj-api"
    }}
    """
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    classification = json.loads(response.content)
    
    state['event_type'] = f"{classification['source']}.{classification['event_type']}"
    return state

def select_tools(state: AgentState) -> AgentState:
    """
    LLM determines which tools to call based on event type.
    Uses Featherless AI's native tool calling.
    """
    event = state['event']
    event_type = state['event_type']
    
    prompt = f"""
    You are an intelligent agent managing database operations for an engineering platform.
    
    Event Type: {event_type}
    Event Data: {json.dumps(event, indent=2)}
    
    Your task:
    1. Store this event in the appropriate database(s)
    2. Update relationships if needed
    3. Send notifications if important
    
    Available tools: {len(ALL_TOOLS)} database and notification tools
    
    Choose the right tools to handle this event efficiently.
    """
    
    response = llm_with_tools.invoke([{"role": "user", "content": prompt}])
    
    # Extract tool calls
    if hasattr(response, 'tool_calls') and response.tool_calls:
        state['tool_calls'] = response.tool_calls
    
    return state

def execute_tools(state: AgentState) -> AgentState:
    """
    Execute all selected tools (can be parallel).
    """
    tool_calls = state.get('tool_calls', [])
    results = []
    errors = []
    
    for tool_call in tool_calls:
        try:
            # Find and execute tool
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            
            # Find tool function
            tool_func = next(t for t in ALL_TOOLS if t.name == tool_name)
            result = tool_func.invoke(tool_args)
            
            results.append({
                'tool': tool_name,
                'result': result
            })
        except Exception as e:
            errors.append(f"Tool {tool_name} failed: {str(e)}")
    
    state['tool_results'] = results
    state['errors'] = errors
    return state

def generate_response(state: AgentState) -> AgentState:
    """
    LLM generates summary of actions taken.
    """
    results = state['tool_results']
    errors = state['errors']
    
    prompt = f"""
    Summarize the actions taken for this event:
    
    Event Type: {state['event_type']}
    Tools Executed: {len(results)}
    Results: {json.dumps(results, indent=2)}
    Errors: {errors if errors else 'None'}
    
    Provide a concise summary of what was done.
    """
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    state['response'] = response.content
    
    return state

# Build LangGraph workflow
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("classify", classify_event)
workflow.add_node("select_tools", select_tools)
workflow.add_node("execute_tools", execute_tools)
workflow.add_node("respond", generate_response)

# Define edges
workflow.set_entry_point("classify")
workflow.add_edge("classify", "select_tools")
workflow.add_edge("select_tools", "execute_tools")
workflow.add_edge("execute_tools", "respond")
workflow.add_edge("respond", END)

# Compile graph
agent = workflow.compile()
```

---

## 📡 Kafka Consumer

```python
# agent/kafka_consumer.py

from kafka import KafkaConsumer
import json
import logging
from agent import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_kafka_consumer():
    """
    Start Kafka consumer and process events through agent.
    """
    consumer = KafkaConsumer(
        'engineering-events',  # Topic name
        bootstrap_servers=['localhost:9092'],  # Kafka brokers
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='database-agent-group'
    )
    
    logger.info("🚀 Kafka consumer started. Listening for events...")
    
    for message in consumer:
        try:
            event = message.value
            logger.info(f"📨 Received event: {event.get('event_type', 'unknown')}")
            
            # Process through LangGraph agent
            result = agent.invoke({
                'event': event,
                'event_type': '',
                'tool_calls': [],
                'tool_results': [],
                'response': '',
                'errors': []
            })
            
            logger.info(f"✅ Agent response: {result['response']}")
            
            if result['errors']:
                logger.error(f"❌ Errors: {result['errors']}")
        
        except Exception as e:
            logger.error(f"💥 Error processing event: {e}")
            continue

if __name__ == "__main__":
    start_kafka_consumer()
```

---

## 📝 Implementation Plan (Step-by-Step)

### Phase 1: Setup & Dependencies (Day 1 - Morning)

**Step 1.1: Install Dependencies**
```bash
uv pip install langchain langgraph langchain-featherless-ai kafka-python pinecone-client
```

**Step 1.2: Get API Keys**

1. **Featherless AI (for LLM):**
   - Sign up at https://featherless.ai/register
   - Get API key from https://featherless.ai/account/api-keys
   - Add to `.env`: `FEATHERLESS_API_KEY=your_key_here`

2. **Pinecone (for embeddings + vector DB):**
   - Sign up at https://www.pinecone.io/
   - Create free serverless index: `engineering-intelligence`
   - Get API key from dashboard
   - Add to `.env`:
     ```bash
     PINECONE_API_KEY=your_key_here
     PINECONE_ENVIRONMENT=us-east-1-aws
     PINECONE_INDEX_NAME=engineering-intelligence
     ```

**Step 1.3: Create Agent Directory Structure**
```bash
mkdir agent agent/tools agent/prompts agent/models agent/utils
```

---

### Phase 2: Build Tools (Day 1 - Afternoon)

**Step 2.1: Implement Neo4j Tools**
- Create `agent/tools/neo4j_tools.py`
- Implement 12 tools (start with 5 most important)
- Test each tool individually

**Step 2.2: Implement ClickHouse Tools**
- Create `agent/tools/clickhouse_tools.py`
- Implement 8 tools
- Test with sample events

**Step 2.3: Implement PostgreSQL Tools**
- Create `agent/tools/postgres_tools.py`
- Implement 10 tools
- Test vector similarity search

**Step 2.4: Implement Pinecone Tools**
- Create `agent/tools/pinecone_tools.py`
- Implement 5 tools
- Test embedding generation

**Step 2.5: Implement Notification & Jira Tools**
- Create `agent/tools/notification_tools.py`
- Create `agent/tools/jira_tools.py`
- Test with mock data

---

### Phase 3: Build Agent (Day 2 - Morning)

**Step 3.1: Create LangGraph Agent**
- Implement `agent/agent.py`
- Define state graph with 4 nodes
- Test with hardcoded events

**Step 3.2: Create Featherless AI Client**
- Implement `agent/utils/featherless_client.py`
- Test tool calling with simple example
- Verify Qwen3-32B model works

**Step 3.3: Write System Prompts**
- Create `agent/prompts/system_prompt.py`
- Define event classification prompts
- Define tool selection prompts

---

### Phase 4: Kafka Integration (Day 2 - Afternoon)

**Step 4.1: Create Kafka Consumer**
- Implement `agent/kafka_consumer.py`
- Connect to existing Kafka cluster
- Test message consumption

**Step 4.2: End-to-End Testing**
- Send test events to Kafka
- Verify agent processes correctly
- Check database writes

**Step 4.3: Error Handling & Logging**
- Add comprehensive logging
- Implement retry logic
- Add dead letter queue

---

### Phase 5: Testing & Deployment (Day 3)

**Step 5.1: Unit Tests**
- Test each tool independently
- Test agent state transitions
- Test Kafka consumer

**Step 5.2: Integration Tests**
- Test full flow: Kafka → Agent → Databases
- Test multiple event types
- Test error scenarios

**Step 5.3: Deployment**
- Containerize with Docker
- Deploy to production
- Set up monitoring

---

## 🎯 Key Features to Implement

### 1. **Smart Event Routing**
- LLM classifies events and routes to appropriate DBs
- Example: GitHub commit → ClickHouse + Neo4j + update embeddings

### 2. **Intelligent Task Assignment**
- New Jira issue → Agent finds best developer using vector search
- Automatically assigns and notifies

### 3. **Proactive Notifications**
- Detects patterns (e.g., high workload) → Sends Slack alert
- Suggests rebalancing tasks

### 4. **Context-Aware Decisions**
- Agent queries multiple DBs to understand context
- Makes informed decisions about actions

### 5. **Audit Trail**
- All actions logged to ClickHause
- Full traceability

---

## 📊 Event Examples

### Example 1: GitHub Commit Event
```json
{
  "source": "github",
  "event_type": "push",
  "repository": "api-gateway",
  "commits": [{
    "sha": "abc123",
    "author": {
      "email": "alice@company.com",
      "name": "Alice Johnson"
    },
    "message": "Add OAuth2 authentication",
    "stats": {
      "additions": 150,
      "deletions": 20,
      "total": 170
    },
    "files": ["auth/oauth.py", "tests/test_auth.py"]
  }]
}
```

**Agent Actions:**
1. Insert event to ClickHouse (`insert_commit_event`)
2. Update Neo4j contribution graph (`add_contribution_relationship`)
3. Update developer embedding in Pinecone using Pinecone inference API (`upsert_developer_embedding`)

---

### Example 2: Jira Issue Created
```json
{
  "source": "jira",
  "event_type": "issue_created",
  "issue": {
    "key": "PROJ-456",
    "summary": "Implement real-time notifications",
    "description": "Build WebSocket server for push notifications using FastAPI and Redis",
    "issue_type": "Story",
    "priority": "High",
    "story_points": 8,
    "project": "api-gateway"
  },
  "user": {
    "email": "pm@company.com"
  }
}
```

**Agent Actions:**
1. Insert event to ClickHouse (`insert_jira_event`)
2. Find best developer using vector search (`search_similar_developers_vector`)
3. Auto-assign issue (`assign_jira_issue`)
4. Send notification to developer (`send_slack_notification`)

---

## 🔒 Security Considerations

1. **API Keys**: Store in `.env`, never commit
2. **Kafka Auth**: Use SASL/SSL for production
3. **Database Access**: Use read-write users for agent, read-only for queries
4. **Rate Limiting**: Implement for Featherless AI and Pinecone API calls
5. **Audit Logging**: Log all actions to ClickHouse

---

## 📈 Performance Optimization

1. **Batch Tool Calls**: Execute independent tools in parallel
2. **Cache Embeddings**: Don't regenerate for same text
3. **Connection Pooling**: Reuse database connections
4. **Async Processing**: Use async/await for I/O operations
5. **Dead Letter Queue**: Handle failed events separately

---

## 🚀 Next Steps

1. **Review this plan** - Understand the full architecture
2. **Set up Featherless AI account** - Get API key
3. **Install dependencies** - Run `uv pip install` commands
4. **Start with tools** - Implement Neo4j tools first
5. **Build agent** - Create LangGraph workflow
6. **Test with Kafka** - Send test events
7. **Deploy** - Containerize and run in production

---

**Estimated Timeline:**
- Day 1: Tools implementation (6-8 hours)
- Day 2: Agent + Kafka (6-8 hours)
- Day 3: Testing + Deployment (4-6 hours)
- **Total: 2-3 days for MVP**

Ready to start implementation? Let me know which part you want to tackle first!
