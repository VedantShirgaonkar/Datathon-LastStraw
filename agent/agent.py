"""
Agent workflow with LangGraph state machine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
import json

from agent.config import get_config
from agent.tools.neo4j_tools import neo4j_tools
from agent.tools.clickhouse_tools import clickhouse_tools
from agent.tools.postgres_tools import postgres_tools
from agent.tools.executor_tools import executor_tools
from agent.tools.analytics_tools import analytics_tools
from agent.event_router import get_suggested_actions, format_actions_for_prompt
from agent.schemas.tool_schemas import (
    KafkaEvent,
    EventClassification,
    ToolCall,
    ToolResult,
    AgentResponse,
    EventSource
)


# ==============================================================================
# AGENT STATE
# ==============================================================================

class AgentState(TypedDict):
    """LangGraph agent state"""
    # Input
    event: KafkaEvent
    
    # Classification
    classification: EventClassification | None
    
    # Tool execution
    tool_calls: List[ToolCall]
    tool_results: List[ToolResult]
    
    # Output
    response: AgentResponse | None
    
    # Messages for LLM
    messages: List[HumanMessage | AIMessage | SystemMessage]


# ==============================================================================
# AGENT NODES
# ==============================================================================

def classify_event(state: AgentState) -> AgentState:
    """
    Classify incoming Kafka event to determine what actions to take.
    Uses Featherless AI with structured output.
    """
    config = get_config()
    
    # Initialize Featherless AI (OpenAI-compatible)
    llm = ChatOpenAI(
        model=config.featherless_model,
        api_key=config.featherless_api_key,
        base_url=config.featherless_base_url,
        temperature=config.featherless_temperature
    )
    
    # Create structured output LLM
    classifier = llm.with_structured_output(EventClassification)
    
    # Classification prompt
    system_prompt = """You are an event classification expert for engineering intelligence platform.
Analyze incoming events and classify them with relevant metadata.

Event Sources:
- github: Commits, PRs, code reviews
- jira: Issues, sprints, status changes
- notion: Documentation updates
- prometheus: System metrics
- ai_agent: AI-generated insights

Extract:
- source: Event source system
- event_type: Specific event type (commit_pushed, pr_merged, issue_created, etc.)
- developer_email: Developer's email if present
- project_id: Project identifier if present
- confidence: Classification confidence (0.0-1.0)
"""
    
    event_json = state["event"].model_dump_json(indent=2)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Classify this event:\n\n{event_json}")
    ]
    
    # Classify with structured output
    classification = classifier.invoke(messages)
    
    state["classification"] = classification
    state["messages"] = messages + [AIMessage(content=f"Classified as: {classification.event_type}")]
    
    return state


def select_tools(state: AgentState) -> AgentState:
    """
    Select appropriate tools based on event classification.
    Uses Featherless AI with tool binding.
    """
    config = get_config()
    
    # Initialize LLM with all tools
    llm = ChatOpenAI(
        model=config.featherless_model,
        api_key=config.featherless_api_key,
        base_url=config.featherless_base_url,
        temperature=config.featherless_temperature
    )
    
    # Bind all tools (database + executor + analytics)
    all_tools = neo4j_tools + clickhouse_tools + postgres_tools + executor_tools + analytics_tools
    llm_with_tools = llm.bind_tools(all_tools)
    
    # Tool selection prompt
    classification = state["classification"]
    event = state["event"]
    
    system_prompt = """You are a tool selection expert for database operations AND cross-platform actions.
Based on the classified event, determine which tools to call.

## DATABASE TOOLS (Recording/Querying):
1. For commit/PR events: insert_commit_event or insert_pr_event in ClickHouse
2. For new developers: create_developer_node in Neo4j
3. For skill updates: add_skill_relationship in Neo4j
4. For contributions: add_contribution_relationship in Neo4j + event in ClickHouse
5. For Jira issues: insert_jira_event in ClickHouse
6. For queries: find_available_developers, get_developer_activity_summary, get_project_dora_metrics

## EXECUTOR TOOLS (Cross-Platform Actions):
Use these to create/update items in external systems via Lambda:

### When to use JIRA executor tools:
- jira_create_issue: When GitHub issue needs a corresponding Jira ticket
- jira_add_comment: When GitHub PR/commit should be logged on related Jira issue
- jira_assign_issue: When auto-assigning based on contributor or workload
- jira_transition_issue: When PR merged → move Jira to "Done"

### When to use GITHUB executor tools:
- github_create_issue: When Jira bug should create GitHub issue for tracking
- github_add_comment: When Jira/Notion updates should be synced to GitHub
- github_close_issue: When Jira issue resolved → close linked GitHub issue

### When to use NOTION executor tools:
- notion_create_page: When new project/sprint needs documentation page
- notion_update_status: When Jira status changes → sync to Notion
- notion_assign_task: When assigning documentation tasks

## CROSS-PLATFORM SYNC RULES:
- GitHub PR merged → jira_transition_issue (move to Done) + notion_update_status
- Jira issue created with High priority → github_create_issue (if code-related)
- Notion task completed → jira_add_comment (sync status)

Call multiple tools if needed for cross-platform synchronization.
Extract all required parameters from the event raw data.
"""
    
    # Get suggested actions from event router
    suggested_actions = get_suggested_actions(
        source=str(classification.source.value) if hasattr(classification.source, 'value') else str(classification.source),
        event_type=classification.event_type,
        raw=event.raw
    )
    suggested_actions_text = format_actions_for_prompt(suggested_actions)
    
    event_summary = f"""
Event Classification:
- Source: {classification.source}
- Type: {classification.event_type}
- Developer: {classification.developer_email or 'N/A'}
- Project: {classification.project_id or 'N/A'}
- Confidence: {classification.confidence}

Event Raw Data:
{json.dumps(event.raw, indent=2)}

{suggested_actions_text}

Based on the event and suggested actions above, determine which tools to call.
Extract all required parameters from the raw event data.
"""
    
    messages = state["messages"] + [
        SystemMessage(content=system_prompt),
        HumanMessage(content=event_summary)
    ]
    
    # Get tool calls from LLM
    response = llm_with_tools.invoke(messages)
    
    # Parse tool calls
    tool_calls = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            tool_call = ToolCall(
                tool_name=tc['name'],
                arguments=tc['args'],
                call_id=tc['id']
            )
            tool_calls.append(tool_call)
    
    state["tool_calls"] = tool_calls
    state["messages"] = messages + [response]
    
    return state


def execute_tools(state: AgentState) -> AgentState:
    """
    Execute selected tools and collect results.
    Includes database tools AND executor tools for cross-platform actions.
    """
    tool_results = []
    
    # Map tool names to actual tool functions (database + executor)
    all_tools = neo4j_tools + clickhouse_tools + postgres_tools + executor_tools
    tool_map = {tool.name: tool for tool in all_tools}
    
    # Execute each tool call
    for tool_call in state["tool_calls"]:
        try:
            tool = tool_map.get(tool_call.tool_name)
            
            if not tool:
                result = ToolResult(
                    tool_name=tool_call.tool_name,
                    call_id=tool_call.call_id,
                    success=False,
                    result=None,
                    error=f"Tool {tool_call.tool_name} not found"
                )
            else:
                # Execute tool
                output = tool.invoke(tool_call.arguments)
                
                result = ToolResult(
                    tool_name=tool_call.tool_name,
                    call_id=tool_call.call_id,
                    success=output.get('success', False),
                    result=output,
                    error=output.get('message') if not output.get('success') else None
                )
            
            tool_results.append(result)
            
        except Exception as e:
            result = ToolResult(
                tool_name=tool_call.tool_name,
                call_id=tool_call.call_id,
                success=False,
                result=None,
                error=str(e)
            )
            tool_results.append(result)
    
    state["tool_results"] = tool_results
    
    return state


def generate_response(state: AgentState) -> AgentState:
    """
    Generate final agent response summarizing actions taken.
    """
    classification = state["classification"]
    tool_results = state["tool_results"]
    
    # Summarize results
    actions_taken = []
    errors = []
    
    for result in tool_results:
        if result.success:
            actions_taken.append(f"{result.tool_name}: {result.result.get('message', 'Success')}")
        else:
            errors.append(f"{result.tool_name}: {result.error}")
    
    # Create response
    response = AgentResponse(
        summary=f"Processed {classification.event_type} event from {classification.source}",
        actions_taken=actions_taken,
        tools_executed=len(tool_results),
        errors=errors,
        success=all(r.success for r in tool_results)
    )
    
    state["response"] = response
    
    return state


# ==============================================================================
# BUILD WORKFLOW
# ==============================================================================

def create_agent_workflow() -> StateGraph:
    """
    Create LangGraph workflow with 4 nodes.
    
    Flow:
    1. classify_event: Classify incoming Kafka event
    2. select_tools: Determine which tools to call
    3. execute_tools: Execute tools in parallel
    4. generate_response: Summarize results
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("classify_event", classify_event)
    workflow.add_node("select_tools", select_tools)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("generate_response", generate_response)
    
    # Define edges
    workflow.set_entry_point("classify_event")
    workflow.add_edge("classify_event", "select_tools")
    workflow.add_edge("select_tools", "execute_tools")
    workflow.add_edge("execute_tools", "generate_response")
    workflow.add_edge("generate_response", END)
    
    # Compile workflow
    app = workflow.compile()
    
    return app


# ==============================================================================
# AGENT INTERFACE
# ==============================================================================

class DatabaseAgent:
    """
    Main agent interface for processing Kafka events.
    """
    
    def __init__(self):
        self.workflow = create_agent_workflow()
    
    def process_event(self, event: KafkaEvent) -> AgentResponse:
        """
        Process a Kafka event through the agent workflow.
        
        Args:
            event: Validated Kafka event
        
        Returns:
            AgentResponse with summary of actions taken
        """
        # Initialize state
        initial_state: AgentState = {
            "event": event,
            "classification": None,
            "tool_calls": [],
            "tool_results": [],
            "response": None,
            "messages": []
        }
        
        # Run workflow
        final_state = self.workflow.invoke(initial_state)
        
        return final_state["response"]
