"""
Supervisor Agent - Main Orchestrator
Central agent that routes user queries to specialized sub-agents.
Implements a Hierarchical Multi-Agent System using LangGraph.
"""

from typing import Annotated, TypedDict, Sequence, Literal, List
import operator
import functools

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from langgraph.graph import StateGraph, END, START

from agents.utils.logger import get_logger, PhaseLogger, log_agent_decision
from agents.utils.config import get_config

# Import specialist agents
from agents.specialists.dora_agent import get_dora_agent
from agents.specialists.resource_agent import get_resource_agent
from agents.specialists.insights_agent import get_insights_agent

logger = get_logger(__name__, "SUPERVISOR")


# ============================================================================
# State Definition
# ============================================================================

class AgentState(TypedDict):
    """State that persists across agent execution."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str  # The next agent to route to


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

1. **DORA_Pro**: Analyzes deployment frequency, lead time, failure rates, and MTTR. Use for any questions about deployment stability or DORA metrics.
2. **Resource_Planner**: Manages project status, deadlines, developer workload, and team capacity. Use for questions about projects, assignments, or "who is busy?".
3. **Insights_Specialist**: Knows about developer skills, profiles, and collaboration patterns. Use for "who knows X?", "find me a developer", or "who works with Y?".

Your job is to route the user's request to the correct specialist.
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
    """Create the supervisor LLM (Qwen 72B)."""
    config = get_config()
    return ChatOpenAI(
        model=config.featherless.model_primary,
        api_key=config.featherless.api_key,
        base_url=config.featherless.base_url,
        temperature=0,
    )


def supervisor_node(state: AgentState):
    """The supervisor decides which agent calls next."""
    messages = state["messages"]
    
    # Simple router: ask LLM to pick next agent
    llm = create_supervisor_llm()
    
    # We use function calling/structured output to force a choice
    # Qwen 2.5 72B generally supports tool calling
    
    # Construct the message history with system prompt
    full_messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
    
    try:
        # Get the response
        logger.debug("Supervisor deciding next step...")
        response = llm.with_structured_output(RouteResponse).invoke(full_messages)
        next_agent = response.next
    except Exception as e:
        logger.error(f"Routing failed, defaulting to FINISH: {e}")
        next_agent = "FINISH"
        
    log_agent_decision(logger, "SUPERVISOR", f"Routing to {next_agent}")
    return {"next": next_agent}


# ============================================================================
# Sub-Agent Nodes
# ============================================================================

def create_agent_node(agent, name):
    """Create a graceful node for a sub-agent."""
    def agent_node(state: AgentState):
        logger.info(f"▶ Handoff to {name}")
        # Invoke the sub-agent
        result = agent.invoke(state)
        # We need to return the last message from the sub-agent
        # The sub-agent returns a state dict, we extract 'messages'
        last_message = result["messages"][-1]
        
        # Ensure it's an AIMessage
        if not isinstance(last_message, AIMessage):
            last_message = AIMessage(content=str(last_message.content))
            
        logger.info(f"✓ {name} completed task")
        return {
            "messages": [
                AIMessage(
                    content=last_message.content, 
                    name=name
                )
            ]
        }
    return agent_node


# ============================================================================
# Graph Builder
# ============================================================================

def create_supervisor_graph():
    """Create the hierarchical multi-agent graph."""
    logger.info("Creating multi-agent supervisor graph...")
    
    with PhaseLogger(logger, "Graph Construction"):
        workflow = StateGraph(AgentState)
        
        # Add supervisor node
        workflow.add_node("supervisor", supervisor_node)
        
        # Add specialist nodes
        workflow.add_node("DORA_Pro", create_agent_node(get_dora_agent(), "DORA_Pro"))
        workflow.add_node("Resource_Planner", create_agent_node(get_resource_agent(), "Resource_Planner"))
        workflow.add_node("Insights_Specialist", create_agent_node(get_insights_agent(), "Insights_Specialist"))
        
        # Route logic
        for member in members:
            # After a specialist finishes, go back to supervisor 
            # (to decide if more work is needed or to finish)
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
        
        graph = workflow.compile()
        logger.info("✓ Multi-agent graph compiled successfully")
        
    return graph


# ============================================================================
# Main Interface (Preserved)
# ============================================================================

class SupervisorAgent:
    """High-level interface for the supervisor agent."""
    
    def __init__(self):
        self.graph = None
        self._initialized = False
    
    def initialize(self):
        """Initialize the agent (lazy loading)."""
        if not self._initialized:
            with PhaseLogger(logger, "Supervisor Initialization"):
                self.graph = create_supervisor_graph()
                self._initialized = True
        return self
    
    def query(self, user_message: str) -> str:
        """Process a user query."""
        if not self._initialized:
            self.initialize()
            
        logger.info(f"Processing query: {user_message[:100]}...")
        
        try:
            initial_state = {
                "messages": [HumanMessage(content=user_message)],
                "next": "supervisor"
            }
            
            final_state = self.graph.invoke(initial_state)
            
            # Get final response
            return final_state["messages"][-1].content
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return f"Error: {str(e)}"

    def stream_query(self, user_message: str):
        """Process a query with streaming."""
        if not self._initialized:
            self.initialize()
            
        initial_state = {"messages": [HumanMessage(content=user_message)]}
        
        for event in self.graph.stream(initial_state):
            for node_name, state_update in event.items():
                if node_name == "supervisor":
                    next_agent = state_update.get("next")
                    if next_agent and next_agent != "FINISH":
                        yield {"type": "routing", "agent": next_agent}
                elif node_name in members:
                    # Specialist finished
                    messages = state_update.get("messages", [])
                    if messages:
                        yield {"type": "response", "content": messages[-1].content}

# Global instance
_supervisor = None

def get_supervisor() -> SupervisorAgent:
    global _supervisor
    if _supervisor is None:
        _supervisor = SupervisorAgent()
    return _supervisor
