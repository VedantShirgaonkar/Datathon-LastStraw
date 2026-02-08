"""
Supervisor Agent - Main Orchestrator
Central agent that routes user queries to specialized sub-agents.
Implements a Hierarchical Multi-Agent System using LangGraph
with intelligent multi-model routing via Featherless.ai.
"""

from typing import Annotated, TypedDict, Sequence, Literal, List, Optional, Generator
import operator
import functools
import time
import uuid

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langgraph.graph import StateGraph, END, START

from agents.utils.logger import get_logger, PhaseLogger, log_agent_decision, log_llm_call
from agents.utils.config import get_config
from agents.utils.model_router import (
    route_query, classify_task, select_model,
    ModelSelection, TaskType,
)
from agents.utils.memory import get_conversation_memory, ConversationMemory
from agents.utils.streaming import (
    StreamEvent, StreamEventType, StreamBuffer, render_stream_to_console,
)

# Import specialist agent *factories* (not singletons — we now create with dynamic models)
from agents.specialists.dora_agent import create_dora_agent
from agents.specialists.resource_agent import create_resource_agent
from agents.specialists.insights_agent import create_insights_agent

logger = get_logger(__name__, "SUPERVISOR")


# ============================================================================
# State Definition
# ============================================================================

class AgentState(TypedDict):
    """State that persists across agent execution."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str                                      # The next agent to route to
    model_selection: Optional[dict]                # Current model selection info


# ============================================================================
# Routing Logic
# ============================================================================

members = ["DORA_Pro", "Resource_Planner", "Insights_Specialist"]
options = ["FINISH"] + members

class RouteResponse(BaseModel):
    """Structured response for routing."""
    next: Literal["FINISH", "DORA_Pro", "Resource_Planner", "Insights_Specialist"]

SYSTEM_PROMPT = """You are the Lead Engineering Supervisor.
You manage a team of specialized experts:

1. **DORA_Pro**: Analyzes deployment frequency, lead time, failure rates, and MTTR. Use for any questions about deployment stability, DORA metrics, or anomaly detection.
2. **Resource_Planner**: Manages project status, deadlines, developer workload, team capacity, and **1:1 meeting preparation**. Use for questions about projects, assignments, "who is busy?", or "prepare for my 1:1 with [developer]".
3. **Insights_Specialist**: Knows about developer skills, profiles, and collaboration patterns. Use for "who knows X?", "find me a developer", "who works with Y?", or **"find an expert in Z"** (Graph RAG expert discovery).

Your job is to route the user's request to the correct specialist.
- If the user asks to prepare for a 1:1, meeting prep, talking points, or anything about a one-on-one meeting, route to **Resource_Planner**.
- If the specialist has answered the question and no further action is needed, route to FINISH.
- If the last message is from a specialist and it provides the requested information, verify it answers the user's question and route to FINISH.
- If the user greets you or asks a general question, you can answer directly (though routing to FINISH is preferred if complete).
- Do NOT try to answer data questions yourself. ALWAYS route to a specialist.
- Do NOT route back to the same specialist immediately unless there is a clear error or missing information.

OUTPUT INSTRUCTION:
You must respond with a valid JSON object {"next": "AGENT_NAME"}.
Do not add any conversational text.
"""


def create_supervisor_llm():
    """Create the supervisor LLM (always Qwen 72B — routing needs best reasoning)."""
    config = get_config()
    return ChatOpenAI(
        model=config.featherless.model_primary,
        api_key=config.featherless.api_key,
        base_url=config.featherless.base_url,
        temperature=0,
    )


def _extract_user_query(messages: Sequence[BaseMessage]) -> str:
    """Pull the latest HumanMessage text for task classification."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


def supervisor_node(state: AgentState):
    """The supervisor decides which agent calls next AND selects the optimal model."""
    messages = state["messages"]

    # ── 1. Classify the task & select model ─────────────────
    user_query = _extract_user_query(messages)
    model_sel: ModelSelection = route_query(user_query)

    log_llm_call(
        logger,
        model=model_sel.display_name,
        prompt_preview=f"task={model_sel.task_type.value} | {model_sel.reason}",
    )

    # ── 2. Ask supervisor LLM to pick next agent ───────────
    llm = create_supervisor_llm()
    full_messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)

    try:
        logger.debug("Supervisor deciding next step...")
        response = llm.with_structured_output(RouteResponse).invoke(full_messages)
        next_agent = response.next
    except Exception as e:
        logger.error(f"Routing failed, defaulting to FINISH: {e}")
        next_agent = "FINISH"

    log_agent_decision(logger, "SUPERVISOR", f"Routing to {next_agent}")

    # Pack model selection into state so the agent node can use it
    model_info = {
        "model_name": model_sel.model_name,
        "display_name": model_sel.display_name,
        "task_type": model_sel.task_type.value,
        "reason": model_sel.reason,
        "temperature": model_sel.temperature,
        "emoji": model_sel.emoji,
    }

    return {"next": next_agent, "model_selection": model_info}


# ============================================================================
# Sub-Agent Nodes (with dynamic model selection)
# ============================================================================

# Map agent name → factory function
_AGENT_FACTORIES = {
    "DORA_Pro": create_dora_agent,
    "Resource_Planner": create_resource_agent,
    "Insights_Specialist": create_insights_agent,
}

# Cache: (agent_name, model_name) → compiled agent
_agent_cache: dict[tuple[str, str], object] = {}


def _get_or_create_agent(name: str, model_name: str, temperature: float):
    """Get a cached agent or create one with the specified model."""
    cache_key = (name, model_name)
    if cache_key not in _agent_cache:
        factory = _AGENT_FACTORIES[name]
        _agent_cache[cache_key] = factory(
            model_override=model_name,
            temperature_override=temperature,
        )
        logger.info(f"Created {name} agent with model {model_name}")
    return _agent_cache[cache_key]


def create_agent_node(name: str):
    """
    Create a graph node for a specialist agent.
    The model is determined dynamically from state['model_selection'].
    """
    def agent_node(state: AgentState):
        model_info = state.get("model_selection") or {}
        model_name = model_info.get("model_name")
        temperature = model_info.get("temperature", 0.1)
        display_name = model_info.get("display_name", "default")
        emoji = model_info.get("emoji", "🤖")

        logger.info(
            f"▶ Handoff to {name}  |  {emoji} Model: {display_name}"
        )

        # Get (or create) the agent compiled with the chosen model
        if model_name:
            agent = _get_or_create_agent(name, model_name, temperature)
        else:
            # Fallback: use default model for this agent
            agent = _get_or_create_agent(
                name,
                _get_default_model(name),
                temperature,
            )

        result = agent.invoke(state)
        last_message = result["messages"][-1]

        if not isinstance(last_message, AIMessage):
            last_message = AIMessage(content=str(last_message.content))

        # Prepend model attribution to the response
        header = f"{emoji} *[{display_name}]*\n\n"

        logger.info(f"✓ {name} completed task ({display_name})")
        return {
            "messages": [
                AIMessage(
                    content=header + last_message.content,
                    name=name,
                )
            ]
        }

    return agent_node


def _get_default_model(agent_name: str) -> str:
    """Return the default model for an agent when no routing info is present."""
    config = get_config()
    defaults = {
        "DORA_Pro": config.featherless.model_analytics,
        "Resource_Planner": config.featherless.model_primary,
        "Insights_Specialist": config.featherless.model_fast,
    }
    return defaults.get(agent_name, config.featherless.model_primary)


# ============================================================================
# Graph Builder
# ============================================================================

def create_supervisor_graph(checkpointer=None):
    """
    Create the hierarchical multi-agent graph with dynamic model routing.

    Args:
        checkpointer: Optional LangGraph checkpointer for conversation memory.
                      If provided, the graph will support multi-turn threads.
    """
    logger.info("Creating multi-agent supervisor graph (with multi-model routing)...")
    
    with PhaseLogger(logger, "Graph Construction"):
        workflow = StateGraph(AgentState)
        
        # Add supervisor node
        workflow.add_node("supervisor", supervisor_node)
        
        # Add specialist nodes — agents are now created dynamically inside the node
        workflow.add_node("DORA_Pro", create_agent_node("DORA_Pro"))
        workflow.add_node("Resource_Planner", create_agent_node("Resource_Planner"))
        workflow.add_node("Insights_Specialist", create_agent_node("Insights_Specialist"))
        
        # Route logic
        for member in members:
            workflow.add_edge(member, "supervisor")
        
        # Conditional logic from supervisor
        conditional_map = {k: k for k in members}
        conditional_map["FINISH"] = END
        
        workflow.add_conditional_edges(
            "supervisor", 
            lambda x: x["next"], 
            conditional_map
        )
        
        # Entry point
        workflow.add_edge(START, "supervisor")
        
        graph = workflow.compile(checkpointer=checkpointer)

        has_memory = checkpointer is not None
        logger.info(
            f"✓ Multi-agent graph compiled (model-routing=✅, memory={'✅' if has_memory else '❌'})"
        )
        
    return graph


# ============================================================================
# Main Interface (Preserved)
# ============================================================================

class SupervisorAgent:
    """
    High-level interface for the supervisor agent.
    
    Supports thread-based conversation memory for multi-turn interactions.
    Each thread maintains its own conversation history via a LangGraph
    checkpointer, so the agent remembers previous messages within a thread.
    """
    
    def __init__(self):
        self.graph = None
        self._initialized = False
        self._memory: Optional[ConversationMemory] = None
    
    def initialize(self):
        """Initialize the agent with conversation memory (lazy loading)."""
        if not self._initialized:
            with PhaseLogger(logger, "Supervisor Initialization"):
                self._memory = get_conversation_memory()
                self.graph = create_supervisor_graph(
                    checkpointer=self._memory.checkpointer
                )
                self._initialized = True
                logger.info("✓ Supervisor ready with conversation memory")
        return self

    @property
    def memory(self) -> ConversationMemory:
        """Access the conversation memory manager."""
        if not self._initialized:
            self.initialize()
        return self._memory

    def new_thread(self, title: str = "") -> str:
        """Create a new conversation thread and return its ID."""
        return self.memory.new_thread(title)

    def list_threads(self) -> list[dict]:
        """List all conversation threads."""
        return self.memory.list_threads()

    def delete_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread."""
        return self.memory.delete_thread(thread_id)

    def query(self, user_message: str, thread_id: Optional[str] = None) -> str:
        """
        Process a user query.
        
        Args:
            user_message: The user's question or command.
            thread_id:    Optional conversation thread for multi-turn context.
                          If None, an ephemeral single-shot thread is created.
        """
        if not self._initialized:
            self.initialize()

        # When a checkpointer is attached, LangGraph always needs a thread_id.
        # Generate an ephemeral one for stateless calls so callers don't have to.
        effective_thread = thread_id or f"_ephemeral_{uuid.uuid4().hex[:8]}"
            
        logger.info(
            f"Processing query (thread={thread_id or 'ephemeral'}): "
            f"{user_message[:100]}..."
        )
        
        try:
            initial_state = {
                "messages": [HumanMessage(content=user_message)],
                "next": "supervisor"
            }
            
            config = self._memory.get_config(effective_thread)
            final_state = self.graph.invoke(initial_state, config=config)

            # Update thread metadata (only for explicit threads)
            if thread_id:
                msg_count = len(final_state.get("messages", []))
                self._memory.touch_thread(thread_id, msg_count)
            else:
                # Clean up ephemeral thread so it doesn't accumulate
                self._memory.delete_thread(effective_thread)
            
            return final_state["messages"][-1].content
            
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            return f"Error: {str(e)}"

    def stream_query(
        self,
        user_message: str,
        thread_id: Optional[str] = None,
    ) -> Generator[StreamEvent, None, None]:
        """
        Process a query with **rich streaming** — token-level output,
        tool call visualisation, routing events, and model selection info.

        Yields ``StreamEvent`` objects that the consumer (CLI / SSE endpoint)
        can render however it likes.

        Streaming modes used:
        - ``stream_mode="updates"`` on the *outer* supervisor graph gives us
          per-node state diffs (routing decisions, agent final responses).
        - Inside each specialist we inspect the ``messages`` key for
          ``AIMessageChunk`` / ``ToolMessage`` to emit token / tool events.
        """
        if not self._initialized:
            self.initialize()

        effective_thread = thread_id or f"_ephemeral_{uuid.uuid4().hex[:8]}"
        config = self._memory.get_config(effective_thread)

        initial_state = {"messages": [HumanMessage(content=user_message)]}

        # Emit stream_start
        yield StreamEvent.stream_start(query=user_message, thread_id=thread_id or "")

        stream_start_time = time.time()
        total_tokens = 0
        active_agent: Optional[str] = None
        agent_start_time: float = 0.0

        try:
            for event in self.graph.stream(
                initial_state,
                config=config,
            ):
                for node_name, state_update in event.items():

                    # ── Supervisor routing ──────────────────────
                    if node_name == "supervisor":
                        next_agent = state_update.get("next")
                        model_info = state_update.get("model_selection") or {}

                        # Emit model selection
                        if model_info and next_agent and next_agent != "FINISH":
                            yield StreamEvent.model_selection(
                                model=model_info.get("display_name", "Unknown"),
                                emoji=model_info.get("emoji", "🤖"),
                                task_type=model_info.get("task_type", ""),
                                reason=model_info.get("reason", ""),
                            )

                        # Emit routing
                        if next_agent and next_agent != "FINISH":
                            yield StreamEvent.routing(agent=next_agent)

                    # ── Specialist agent node ───────────────────
                    elif node_name in members:
                        messages = state_update.get("messages", [])
                        if not messages:
                            continue

                        # Emit agent_start if this is a new agent
                        if node_name != active_agent:
                            if active_agent:
                                # close previous agent
                                yield StreamEvent.agent_end(
                                    agent=active_agent,
                                    elapsed_s=time.time() - agent_start_time,
                                )
                            active_agent = node_name
                            agent_start_time = time.time()
                            model_info = state_update.get("model_selection") or {}
                            yield StreamEvent.agent_start(
                                agent=node_name,
                                model=model_info.get("display_name", ""),
                            )

                        # Walk through messages for tool calls & tokens
                        for msg in messages:
                            # ── Tool messages (results) ────────
                            if isinstance(msg, ToolMessage):
                                preview = str(msg.content)[:200] if msg.content else ""
                                yield StreamEvent.tool_end(
                                    tool_name=msg.name or "unknown_tool",
                                    result_preview=preview,
                                    elapsed_s=0,  # individual tool timing not available here
                                )

                            # ── AI messages ────────────────────
                            elif isinstance(msg, AIMessage):
                                # Check for tool_calls (tool invocations)
                                if hasattr(msg, "tool_calls") and msg.tool_calls:
                                    for tc in msg.tool_calls:
                                        yield StreamEvent.tool_start(
                                            tool_name=tc.get("name", "unknown"),
                                            args=tc.get("args", {}),
                                        )

                                # Emit the response content as a single response event
                                # (LangGraph "updates" mode gives us the complete message,
                                #  not individual tokens — true token-level streaming
                                #  requires stream_mode="messages" which we handle in
                                #  stream_query_tokens() below.)
                                if msg.content:
                                    content = str(msg.content)
                                    total_tokens += len(content.split())
                                    yield StreamEvent.response(content=content)

            # Close last agent
            if active_agent:
                yield StreamEvent.agent_end(
                    agent=active_agent,
                    elapsed_s=time.time() - agent_start_time,
                )

        except Exception as e:
            logger.error(f"Streaming failed: {e}", exc_info=True)
            yield StreamEvent.error(message=str(e))

        # Emit stream_end
        elapsed = time.time() - stream_start_time
        yield StreamEvent.stream_end(total_tokens=total_tokens, elapsed_s=elapsed)

        # Maintain thread metadata
        if thread_id:
            self._memory.touch_thread(thread_id)
        else:
            self._memory.delete_thread(effective_thread)

    def stream_query_tokens(
        self,
        user_message: str,
        thread_id: Optional[str] = None,
    ) -> Generator[StreamEvent, None, None]:
        """
        Token-level streaming using LangGraph's ``stream_mode="messages"``.

        This yields individual ``TOKEN`` events as the LLM generates each
        token, plus tool start/end events.  Ideal for the most responsive
        real-time UX.

        Falls back to ``stream_query()`` if ``stream_mode="messages"`` is
        not supported by the current LangGraph version.
        """
        if not self._initialized:
            self.initialize()

        effective_thread = thread_id or f"_ephemeral_{uuid.uuid4().hex[:8]}"
        config = self._memory.get_config(effective_thread)
        initial_state = {"messages": [HumanMessage(content=user_message)]}

        yield StreamEvent.stream_start(query=user_message, thread_id=thread_id or "")

        stream_start_time = time.time()
        total_tokens = 0
        active_tools: dict[str, float] = {}  # tool_name → start_time

        try:
            for msg, metadata in self.graph.stream(
                initial_state,
                config=config,
                stream_mode="messages",
            ):
                node = metadata.get("langgraph_node", "")

                # ── AI message chunks (tokens) ─────────────────
                if hasattr(msg, "content") and isinstance(msg, AIMessage):
                    # Check for tool calls in the chunk
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            t_name = tc.get("name", "unknown")
                            active_tools[t_name] = time.time()
                            yield StreamEvent.tool_start(
                                tool_name=t_name,
                                args=tc.get("args", {}),
                            )

                    # Token content
                    if msg.content:
                        text = str(msg.content)
                        total_tokens += 1
                        yield StreamEvent.token(text=text, agent=node)

                # ── Tool result messages ───────────────────────
                elif isinstance(msg, ToolMessage):
                    t_name = msg.name or "unknown_tool"
                    start = active_tools.pop(t_name, time.time())
                    preview = str(msg.content)[:200] if msg.content else ""
                    yield StreamEvent.tool_end(
                        tool_name=t_name,
                        result_preview=preview,
                        elapsed_s=time.time() - start,
                    )

        except TypeError:
            # Older LangGraph versions may not support stream_mode="messages"
            logger.warning(
                "stream_mode='messages' not supported — "
                "falling back to stream_query()"
            )
            yield from self.stream_query(user_message, thread_id=thread_id)
            return
        except Exception as e:
            logger.error(f"Token streaming failed: {e}", exc_info=True)
            yield StreamEvent.error(message=str(e))

        elapsed = time.time() - stream_start_time
        yield StreamEvent.stream_end(total_tokens=total_tokens, elapsed_s=elapsed)

        if thread_id:
            self._memory.touch_thread(thread_id)
        else:
            self._memory.delete_thread(effective_thread)

# Global instance
_supervisor = None

def get_supervisor() -> SupervisorAgent:
    global _supervisor
    if _supervisor is None:
        _supervisor = SupervisorAgent()
    return _supervisor
