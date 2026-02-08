"""
Agent workflow with LangGraph state machine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from typing import Annotated, TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agent.config import get_config
from agent.tools.neo4j_tools import neo4j_tools
from agent.tools.clickhouse_tools import clickhouse_tools
from agent.tools.postgres_tools import postgres_tools
from agent.tools.executor_tools import executor_tools
# Note: analytics_tools are NOT used here - analytics runs on separate agent/schedule
from agent.event_router import get_suggested_actions, format_actions_for_prompt
from agent.schemas.webhook_schemas import (
    WebhookEvent,
    EventClassification,
    ToolCall,
    ToolResult,
    AgentResponse,
    EventSource
)

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ==============================================================================
# AGENT STATE
# ==============================================================================

class AgentState(TypedDict):
    """LangGraph agent state"""
    # Input
    event: WebhookEvent
    
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
    Classify incoming webhook event to determine what actions to take.
    Uses Groq AI with structured output.
    """
    config = get_config()
    
    # Choose model. If the serialized event is very large and a fallback model
    # is configured, use the fallback model to avoid token-limit errors.
    event_json = state["event"].model_dump_json(indent=2)
    # crude token estimate: 1 token ~= 4 chars (rough heuristic)
    estimated_tokens = max(1, len(event_json) // 4)
    chosen_model = config.groq_model
    fallback = getattr(config, 'groq_fallback_model', None)
    if fallback and estimated_tokens > 10000:
        chosen_model = fallback
        logger.info(f"Large event detected (~{estimated_tokens} tokens). Using fallback model: {chosen_model}")

    # Get API config (auto-detects OpenAI vs Groq based on model name)
    api_key, base_url = config.get_api_config(chosen_model)
    if not api_key:
        raise ValueError(f"No API key configured for model: {chosen_model}")

    # Initialize LLM (OpenAI-compatible)
    llm = ChatOpenAI(
        model=chosen_model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0  # Use 0 temperature for deterministic JSON output
    )
    
    # Create structured output LLM
    classifier = llm.with_structured_output(EventClassification, method="json_mode")
    
    # Classification prompt
    system_prompt = """You are an event classification expert for engineering intelligence platform.
Your task is to analyze incoming events and output a JSON classification.

CRITICAL INSTRUCTIONS:
1. Output ONLY valid JSON matching the schema
2. Do NOT include any thinking process, explanations, or commentary  
3. Do NOT use <think> tags or any other markup
4. Start your response immediately with the opening brace {
5. End your response with the closing brace }
6. Use null (not empty string or "N/A") for missing optional fields

Event Sources:
- github: Commits, PRs, code reviews
- jira: Issues, sprints, status changes
- notion: Documentation updates
- prometheus: System metrics
- ai_agent: AI-generated insights

Required JSON Schema:
{
  "source": "github|jira|notion|prometheus|ai_agent",
  "event_type": "specific_event_type",
  "developer_email": "email_if_present" OR null,
  "project_id": "project_if_present" OR null,
  "confidence": 0.0-1.0
}

IMPORTANT: Use null (not "", not "N/A") for developer_email and project_id if not present.
"""
    
    # event_json already prepared above
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Classify this event:\n\n{event_json}")
    ]
    
    # Classify with structured output
    classification = classifier.invoke(messages)
    
    # DEBUG: Log classification result
    logger.info(f"🔍 EVENT CLASSIFIED: source={classification.source}, type={classification.event_type}, developer={classification.developer_email}, project={classification.project_id}, confidence={classification.confidence}")
    
    state["classification"] = classification
    state["messages"] = messages + [AIMessage(content=f"Classified as: {classification.event_type}")]
    
    return state


def select_tools(state: AgentState) -> AgentState:
    """
    Select appropriate tools based on event classification.
    Uses LLM with tool binding (supports OpenAI and Groq).
    """
    config = get_config()
    
    # Get API config (auto-detects OpenAI vs Groq based on model name)
    api_key, base_url = config.get_api_config(config.groq_model)
    if not api_key:
        raise ValueError(f"No API key configured for model: {config.groq_model}")
    
    # Initialize LLM with all tools
    llm = ChatOpenAI(
        model=config.groq_model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0  # Zero temperature for deterministic tool calling
    )
    
    # Bind all tools (database + executor) - NO analytics, that's a separate agent
    all_tools = neo4j_tools + clickhouse_tools + postgres_tools + executor_tools
    
    # Groq has native tool calling support
    llm_with_tools = llm.bind_tools(
        all_tools,
        tool_choice="auto"  # Qwen3 needs explicit tool_choice
    )
    
    # Tool selection prompt
    classification = state["classification"]
    event = state["event"]
    
    system_prompt = """You are a tool caller for an engineering intelligence platform.

CRITICAL: You MUST call tools using proper function calling format. Do NOT output raw JSON.

TASK: Based on the event, call the required database tools first.

MANDATORY DATABASE TOOLS (call first):
1. For GitHub commits → insert_commit_event(project_id, developer_email, sha, message, files_changed, lines_added, lines_deleted)
2. For GitHub PRs → insert_pr_event(project_id, developer_email, pr_number, action, review_time_hours, lines_changed)
3. For Jira issues → insert_jira_event(project_id, developer_email, issue_key, event_type, status_from, status_to, story_points)
4. For new developers → create_developer_node(email, name, team_id)
5. For contributions → add_contribution_relationship(developer_email, project_id, commits, prs, reviews)

OPTIONAL SYNC TOOLS (call if relevant):
- If PR merged with Jira key → jira_transition_issue(issue_key, status)
- If Jira created → github_create_issue(title, body, labels)
- If status changed → notion_update_status(page_id, status)

Extract all parameters from the event data below and call the appropriate tools.
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
    
    # DEBUG: Log raw LLM response
    logger.info(f"🤖 LLM RESPONSE: {response}")
    
    # Parse tool calls
    tool_calls = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        logger.info(f"🛠️  TOOLS SELECTED: {len(response.tool_calls)} tools")
        for tc in response.tool_calls:
            tool_call = ToolCall(
                tool_name=tc['name'],
                arguments=tc['args'],
                call_id=tc['id']
            )
            tool_calls.append(tool_call)
            logger.info(f"   - {tc['name']} with args: {tc['args']}")
    
    # FALLBACK: Parse invalid_tool_calls (Qwen3 concatenated JSON fix)
    elif hasattr(response, 'invalid_tool_calls') and response.invalid_tool_calls:
        logger.warning("⚠️  Attempting to parse invalid_tool_calls (Qwen3 fallback)")
        for itc in response.invalid_tool_calls:
            try:
                # Extract the LAST complete JSON object from concatenated string
                args_str = itc.get('args', '')
                
                # Find all JSON objects by looking for }{ boundaries
                json_objects = []
                depth = 0
                start = 0
                for i, char in enumerate(args_str):
                    if char == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            json_objects.append(args_str[start:i+1])
                
                # Use the LAST complete JSON (most complete arguments)
                if json_objects:
                    last_json = json_objects[-1]
                    parsed_args = json.loads(last_json)
                    
                    tool_call = ToolCall(
                        tool_name=itc['name'],
                        arguments=parsed_args,
                        call_id=itc['id']
                    )
                    tool_calls.append(tool_call)
                    logger.info(f"✅ RECOVERED: {itc['name']} with args: {parsed_args}")
            except Exception as e:
                logger.error(f"❌ Failed to parse invalid_tool_call: {e}")
    else:
        logger.warning("⚠️  NO TOOLS SELECTED by LLM")
    
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
    logger.info(f"⚙️  EXECUTING {len(state['tool_calls'])} TOOLS...")
    for tool_call in state["tool_calls"]:
        try:
            tool = tool_map.get(tool_call.tool_name)
            
            if not tool:
                logger.error(f"❌ Tool not found: {tool_call.tool_name}")
                result = ToolResult(
                    tool_name=tool_call.tool_name,
                    call_id=tool_call.call_id,
                    success=False,
                    result=None,
                    error=f"Tool {tool_call.tool_name} not found"
                )
            else:
                # Execute tool
                logger.info(f"🔧 Executing: {tool_call.tool_name}")
                output = tool.invoke(tool_call.arguments)
                
                result = ToolResult(
                    tool_name=tool_call.tool_name,
                    call_id=tool_call.call_id,
                    success=output.get('success', False),
                    result=output,
                    error=output.get('message') if not output.get('success') else None
                )
                
                if result.success:
                    logger.info(f"✅ {tool_call.tool_name}: {output.get('message', 'Success')}")
                else:
                    logger.error(f"❌ {tool_call.tool_name} FAILED: {result.error}")
            
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


def run_analytics_sync(state: AgentState) -> AgentState:
    """
    Automatically run analytics sync after database logging.
    This syncs ClickHouse events to PostgreSQL analytics tables.
    """
    from agent.analytics_processor import AnalyticsProcessor
    
    # Only run if we successfully executed database tools
    successful_db_tools = [
        r for r in state["tool_results"] 
        if r.success and r.tool_name in ['insert_commit_event', 'insert_pr_event', 'insert_jira_event']
    ]
    
    if successful_db_tools:
        logger.info("📊 Running automatic analytics sync...")
        processor = AnalyticsProcessor()
        try:
            result = processor.run_full_sync(since_hours=1)  # Sync last hour
            if result.get('success'):
                logger.info(f"✅ Analytics sync complete: {result.get('message', 'Done')}")
            else:
                logger.warning(f"⚠️  Analytics sync partial: {result.get('message', 'Some issues')}")
        except Exception as e:
            logger.error(f"❌ Analytics sync failed: {e}")
        finally:
            processor.close()
    else:
        logger.info("📊 Skipping analytics sync (no DB tools executed)")
    
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
    Create LangGraph workflow with 5 nodes.
    
    Flow:
    1. classify_event: Classify incoming webhook event
    2. select_tools: Determine which tools to call
    3. execute_tools: Execute tools (database logging)
    4. run_analytics_sync: Sync ClickHouse → PostgreSQL
    5. generate_response: Summarize results
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("classify_event", classify_event)
    workflow.add_node("select_tools", select_tools)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("run_analytics_sync", run_analytics_sync)
    workflow.add_node("generate_response", generate_response)
    
    # Define edges
    workflow.set_entry_point("classify_event")
    workflow.add_edge("classify_event", "select_tools")
    workflow.add_edge("select_tools", "execute_tools")
    workflow.add_edge("execute_tools", "run_analytics_sync")
    workflow.add_edge("run_analytics_sync", "generate_response")
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
    
    def process_event(self, event: WebhookEvent) -> AgentResponse:
        """
        Process a webhook event through the agent workflow.
        
        Args:
            event: Validated webhook event
        
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
