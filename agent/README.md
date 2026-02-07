# Database Agent with LangGraph

AI-powered Kafka event processor for engineering intelligence platform. Uses LangGraph for orchestration, Featherless AI (Qwen3-32B) for reasoning, and Pydantic for validation.

## Architecture

```
Kafka Event → Agent Workflow → Database Operations
                  ↓
         ┌────────┴────────┐
         │  1. Classify    │  (Featherless AI + Structured Output)
         │  2. Select Tools│  (LLM with Tool Binding)
         │  3. Execute     │  (Pydantic Validation)
         │  4. Respond     │  (Summary Generation)
         └─────────────────┘
                  ↓
     ┌──────────┬──────────┬──────────┐
     │  Neo4j   │ClickHouse│ Pinecone │
     └──────────┴──────────┴──────────┘
```

## Features

- **LangGraph Workflow**: 4-node state machine for event processing
- **Pydantic Validation**: Type-safe inputs/outputs for all tools
- **Structured Output**: LLM responses validated with Pydantic schemas
- **Multi-Database**: Neo4j (graph), ClickHouse (time-series), Pinecone (vectors)
- **Tool Calling**: Native tool support with Featherless AI (Qwen3-32B)
- **Event Streaming**: Real-time Kafka consumption with error handling

## Project Structure

```
agent/
├── agent.py                    # LangGraph workflow (4 nodes)
├── kafka_consumer.py           # Event ingestion
├── config.py                   # Configuration with validation
├── schemas/
│   ├── tool_schemas.py         # Pydantic I/O schemas
│   └── __init__.py
├── tools/
│   ├── neo4j_tools.py          # Graph database tools (5)
│   ├── clickhouse_tools.py     # Time-series tools (5)
│   └── __init__.py
├── prompts/                    # System prompts (future)
├── utils/                      # Helper functions (future)
└── test_agent.py               # Test suite
```

## Tools Implemented

### Neo4j Tools (5)
1. **create_developer_node** - Create developer in graph
2. **add_skill_relationship** - Add skill to developer
3. **add_contribution_relationship** - Record project contribution
4. **create_project_dependency** - Link dependent projects
5. **find_available_developers** - Query available devs with skill

### ClickHouse Tools (5)
1. **insert_commit_event** - Record git commit
2. **insert_pr_event** - Record PR (for DORA metrics)
3. **insert_jira_event** - Record Jira issue event
4. **get_developer_activity_summary** - Get dev productivity
5. **get_project_dora_metrics** - Get DORA metrics

## Setup

### 1. Install Dependencies

```bash
cd c:\PF\Projects\DataThon
uv pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in:

```env
# Featherless AI (Required)
FEATHERLESS_API_KEY=your_api_key_here
FEATHERLESS_MODEL=Qwen/Qwen3-32B

# Neo4j Aura (Required)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password

# ClickHouse Cloud (Required)
CLICKHOUSE_HOST=xxxxx.aws.clickhouse.cloud
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=your_password

# Kafka (Required)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=engineering-events
KAFKA_GROUP_ID=database-agent-group

# Optional
PINECONE_API_KEY=
SLACK_WEBHOOK_URL=
JIRA_API_TOKEN=
GITHUB_TOKEN=
```

### 3. Test Agent

```bash
python agent/test_agent.py
```

This validates:
- ✅ Event classification with structured output
- ✅ Tool selection and parameter extraction
- ✅ Pydantic schema validation
- ✅ Database operations (Neo4j + ClickHouse)
- ✅ LangGraph workflow orchestration

## Usage

### Start Kafka Consumer

```bash
python agent/kafka_consumer.py
```

The agent will:
1. Connect to Kafka topic `engineering-events`
2. Consume events in real-time
3. Classify each event with Featherless AI
4. Select appropriate tools based on event type
5. Execute tools with Pydantic validation
6. Log results and errors

### Programmatic Usage

```python
from agent import DatabaseAgent
from agent.schemas import KafkaEvent, EventSource
from datetime import datetime, timezone

# Create event
event = KafkaEvent(
    source=EventSource.GITHUB,
    event_type="commit_pushed",
    timestamp=datetime.now(timezone.utc),
    payload={
        "project_id": "proj-api",
        "developer": {"email": "alice@company.com"},
        "commit": {
            "sha": "abc123",
            "message": "Add feature",
            "files_changed": 3,
            "lines_added": 150
        }
    }
)

# Process with agent
agent = DatabaseAgent()
response = agent.process_event(event)

print(f"Success: {response.success}")
print(f"Actions: {response.actions_taken}")
```

## Event Schemas

### GitHub Commit Event

```json
{
  "source": "github",
  "event_type": "commit_pushed",
  "timestamp": "2025-01-15T10:30:00Z",
  "payload": {
    "project_id": "proj-api",
    "developer": {
      "email": "alice@company.com",
      "name": "Alice Johnson"
    },
    "commit": {
      "sha": "abc123def",
      "message": "Add OAuth2",
      "files_changed": 3,
      "lines_added": 150,
      "lines_deleted": 20
    }
  }
}
```

### GitHub PR Merged

```json
{
  "source": "github",
  "event_type": "pull_request_merged",
  "payload": {
    "project_id": "proj-api",
    "pull_request": {
      "number": 42,
      "author": {"email": "bob@company.com"},
      "merged_by": {"email": "alice@company.com"},
      "review_time_hours": 2.5,
      "lines_changed": 250
    }
  }
}
```

### Jira Issue Completed

```json
{
  "source": "jira",
  "event_type": "issue_completed",
  "payload": {
    "project_id": "proj-api",
    "issue": {
      "key": "API-123",
      "assignee": {"email": "alice@company.com"},
      "status_from": "In Progress",
      "status_to": "Done",
      "story_points": 8
    }
  }
}
```

## LangGraph Workflow

The agent uses a 4-node state machine:

### 1. classify_event

- **Input**: Raw Kafka event
- **Process**: Featherless AI with structured output
- **Output**: `EventClassification` (source, type, confidence)
- **Schema**: Pydantic validation

### 2. select_tools

- **Input**: Classified event + payload
- **Process**: LLM with tool binding (all 10 tools)
- **Output**: List of `ToolCall` with arguments
- **Features**: Multi-tool selection, parameter extraction

### 3. execute_tools

- **Input**: Tool calls from previous node
- **Process**: Execute each tool with Pydantic validation
- **Output**: List of `ToolResult` (success/error)
- **Error Handling**: Individual tool failures don't stop workflow

### 4. generate_response

- **Input**: All tool results
- **Process**: Summarize actions and errors
- **Output**: `AgentResponse` with summary
- **Format**: Human-readable summary for logging

## Configuration

Agent configuration uses `pydantic-settings`:

```python
from agent.config import get_config

config = get_config()

# Access settings
print(config.featherless_model)  # Qwen/Qwen3-32B
print(config.featherless_temperature)  # 0.1
print(config.max_tool_retries)  # 3
```

All settings validated on load with helpful error messages.

## Development

### Adding New Tools

1. **Define Schema** in `schemas/tool_schemas.py`:

```python
class MyToolInput(BaseModel):
    param1: str = Field(..., description="Required param")
    param2: int = Field(default=10, ge=0)

class MyToolOutput(BaseModel):
    success: bool
    result: Any
```

2. **Implement Tool** in `tools/my_tools.py`:

```python
def my_tool_function(param1: str, param2: int) -> dict:
    """Tool description for LLM."""
    input_data = MyToolInput(param1=param1, param2=param2)
    # ... logic ...
    output = MyToolOutput(success=True, result=...)
    return output.model_dump()

my_tool = StructuredTool.from_function(
    func=my_tool_function,
    name="my_tool",
    description="When to use this tool",
    args_schema=MyToolInput
)
```

3. **Register Tool** in `tools/__init__.py`:

```python
from agent.tools.my_tools import my_tool
all_tools = neo4j_tools + clickhouse_tools + [my_tool]
```

Tools automatically available to LLM!

### Testing

Run specific test:

```bash
python agent/test_agent.py
```

Test individual tools:

```python
from agent.tools.neo4j_tools import create_developer_node

result = create_developer_node(
    email="test@company.com",
    name="Test Developer",
    team_id="team-test"
)

print(result)  # Validated output
```

## Monitoring

Agent logs include:
- Event classification results
- Tool selections with parameters
- Execution results per tool
- Errors with stack traces
- Performance metrics (future)

Example output:

```
2025-01-15 10:30:00 - agent - INFO - Received event from partition 0, offset 1234
2025-01-15 10:30:01 - agent - INFO - Processing commit_pushed event from github
2025-01-15 10:30:02 - agent - INFO - ✅ Event processed successfully
2025-01-15 10:30:02 - agent - INFO - Summary: Processed commit_pushed event from github
2025-01-15 10:30:02 - agent - INFO - Actions: 2
2025-01-15 10:30:02 - agent - INFO -   - insert_commit_event: Inserted commit abc123 for alice@company.com
2025-01-15 10:30:02 - agent - INFO -   - add_contribution_relationship: Updated contribution for alice@company.com on proj-api
```

## Troubleshooting

### "Validation error" messages

- Check event payload matches expected schema
- Verify required fields present (email, project_id, etc.)
- Review Pydantic error details

### "Tool not found" errors

- Ensure tool registered in `tools/__init__.py`
- Check tool name matches LLM output
- Verify tool imported correctly

### Database connection failures

- Validate `.env` credentials
- Check database connectivity from server
- Review database client initialization

### LLM not calling tools

- Increase temperature (0.1 → 0.3)
- Improve tool descriptions
- Add more examples in prompts

## Next Steps

- [ ] Add PostgreSQL + pgvector tools (10 tools)
- [ ] Add Pinecone vector search tools (5 tools)
- [ ] Add notification tools (Slack, email) (3 tools)
- [ ] Add Jira integration tools (4 tools)
- [ ] Implement retry logic for failed tools
- [ ] Add async tool execution
- [ ] Create monitoring dashboard
- [ ] Add performance metrics
- [ ] Implement circuit breakers
- [ ] Add rate limiting

## License

Internal hackathon project
