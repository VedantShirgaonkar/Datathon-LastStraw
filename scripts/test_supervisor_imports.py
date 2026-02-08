"""Quick smoke test for supervisor module + specialist factories with model override."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. Test that the supervisor compiles and imports correctly
from agents.supervisor import SupervisorAgent, create_supervisor_graph, members
print("✅ Supervisor imports OK")
print(f"  Members: {members}")

# 2. Test that the model router is accessible from supervisor
from agents.utils.model_router import route_query
sel = route_query("What are the DORA metrics?")
print(f"  route_query works: {sel.display_name} ({sel.task_type.value})")

# 3. Test that specialist factories accept model_override
from agents.specialists.dora_agent import create_dora_agent
from agents.specialists.resource_agent import create_resource_agent
from agents.specialists.insights_agent import create_insights_agent

a1 = create_dora_agent(model_override="test-model", temperature_override=0.5)
print("✅ DORA agent factory with override: OK")
a2 = create_resource_agent(model_override="test-model", temperature_override=0.2)
print("✅ Resource agent factory with override: OK")
a3 = create_insights_agent(model_override="test-model", temperature_override=0.3)
print("✅ Insights agent factory with override: OK")

# 4. Verify the AgentState has model_selection field
from agents.supervisor import AgentState
annotations = AgentState.__annotations__
assert "model_selection" in annotations, "model_selection not in AgentState"
print("✅ AgentState has model_selection field")

print("\n🎉 All supervisor module checks passed!")
