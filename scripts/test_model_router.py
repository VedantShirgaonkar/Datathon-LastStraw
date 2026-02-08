"""
Test: Multi-Model Routing (Feature 4.3)
Tests task classification, model selection, and end-to-end routing.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.model_router import classify_task, select_model, route_query, TaskType

PASS = 0
FAIL = 0

def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}")


# ────────────────────────────────────────────────
# 1. Task Classification
# ────────────────────────────────────────────────
print("\n═══ 1. Task Classification ═══")

# Code / SQL
tt, _ = classify_task("Generate a SQL query to find overdue projects")
check("SQL query → CODE_ANALYSIS", tt == TaskType.CODE_ANALYSIS)

tt, _ = classify_task("Write a Cypher query for the collaboration graph")
check("Cypher query → CODE_ANALYSIS", tt == TaskType.CODE_ANALYSIS)

tt, _ = classify_task("The CI/CD pipeline is failing on staging")
check("CI/CD failure → CODE_ANALYSIS", tt == TaskType.CODE_ANALYSIS)

# Analytics / Metrics
tt, _ = classify_task("What are the DORA metrics for the API Gateway project?")
check("DORA metrics → ANALYTICS", tt == TaskType.ANALYTICS)

tt, _ = classify_task("Show me deployment frequency trends for last month")
check("Deployment frequency → ANALYTICS", tt == TaskType.ANALYTICS)

tt, _ = classify_task("Which project has the highest change failure rate?")
check("Change failure rate → ANALYTICS", tt == TaskType.ANALYTICS)

tt, _ = classify_task("Show developer activity for last week")
check("Developer activity → ANALYTICS", tt == TaskType.ANALYTICS)

tt, _ = classify_task("Are there any anomalies in commit volume?")
check("Anomaly detection → ANALYTICS", tt == TaskType.ANALYTICS)

# Planning / Reasoning
tt, _ = classify_task("Which developers are overallocated and need rebalancing?")
check("Overallocation → PLANNING", tt == TaskType.PLANNING)

tt, _ = classify_task("Help me plan resource allocation for Q4")
check("Resource planning → PLANNING", tt == TaskType.PLANNING)

tt, _ = classify_task("What's the capacity of the platform team?")
check("Team capacity → PLANNING", tt == TaskType.PLANNING)

tt, _ = classify_task("Recommend staffing changes for at-risk projects")
check("Staffing recommendation → PLANNING", tt == TaskType.PLANNING)

# Quick Lookup
tt, _ = classify_task("Who is Priya Sharma?")
check("Who is X → QUICK_LOOKUP", tt == TaskType.QUICK_LOOKUP)

tt, _ = classify_task("List all developers on the backend team")
check("List developers → QUICK_LOOKUP", tt == TaskType.QUICK_LOOKUP)

tt, _ = classify_task("Find me a developer with Kubernetes expertise")
check("Find developer skills → QUICK_LOOKUP", tt == TaskType.QUICK_LOOKUP)

tt, _ = classify_task("Who collaborates with Alex on the data pipeline?")
check("Collaboration query → QUICK_LOOKUP", tt == TaskType.QUICK_LOOKUP)

# General / fallback
tt, _ = classify_task("Hello, how are you?")
check("Greeting → GENERAL", tt == TaskType.GENERAL)

tt, _ = classify_task("Thanks for the help!")
check("Thanks → GENERAL", tt == TaskType.GENERAL)


# ────────────────────────────────────────────────
# 2. Model Selection
# ────────────────────────────────────────────────
print("\n═══ 2. Model Selection ═══")

sel = select_model(TaskType.CODE_ANALYSIS)
check("CODE_ANALYSIS → DeepSeek Coder", "DeepSeek" in sel.display_name or "deepseek" in sel.model_name.lower())

sel = select_model(TaskType.ANALYTICS)
check("ANALYTICS → Llama 3.1 70B", "Llama" in sel.display_name or "llama" in sel.model_name.lower())

sel = select_model(TaskType.PLANNING)
check("PLANNING → Qwen 72B", "Qwen" in sel.display_name or "qwen" in sel.model_name.lower())

sel = select_model(TaskType.QUICK_LOOKUP)
check("QUICK_LOOKUP → Hermes 3 8B", "Hermes" in sel.display_name or "hermes" in sel.model_name.lower())

sel = select_model(TaskType.GENERAL)
check("GENERAL → Qwen 72B", "Qwen" in sel.display_name or "qwen" in sel.model_name.lower())


# ────────────────────────────────────────────────
# 3. End-to-End route_query
# ────────────────────────────────────────────────
print("\n═══ 3. End-to-End route_query ═══")

sel = route_query("What are the DORA metrics for the Mobile App?")
check("DORA query → Llama (analytics)", "Llama" in sel.display_name)
check("  task_type is ANALYTICS", sel.task_type == TaskType.ANALYTICS)
check("  has emoji", sel.emoji == "📊")

sel = route_query("Generate SQL for top-performing developers")
check("SQL query → DeepSeek (code)", "DeepSeek" in sel.display_name)
check("  task_type is CODE_ANALYSIS", sel.task_type == TaskType.CODE_ANALYSIS)
check("  has emoji", sel.emoji == "💻")

sel = route_query("Who is the frontend lead?")
check("Profile lookup → Hermes (fast)", "Hermes" in sel.display_name)
check("  task_type is QUICK_LOOKUP", sel.task_type == TaskType.QUICK_LOOKUP)
check("  has emoji", sel.emoji == "⚡")

sel = route_query("Plan the resource allocation for next sprint, considering deadlines and risks")
check("Planning → Qwen (reasoning)", "Qwen" in sel.display_name)
check("  task_type is PLANNING", sel.task_type == TaskType.PLANNING)
check("  has emoji", sel.emoji == "🧠")


# ────────────────────────────────────────────────
# 4. ModelSelection dataclass fields
# ────────────────────────────────────────────────
print("\n═══ 4. ModelSelection fields ═══")
sel = route_query("Show commit statistics for last 2 weeks")
check("model_name is non-empty string", isinstance(sel.model_name, str) and len(sel.model_name) > 5)
check("display_name is non-empty", isinstance(sel.display_name, str) and len(sel.display_name) > 2)
check("reason is non-empty", isinstance(sel.reason, str) and len(sel.reason) > 5)
check("temperature is float", isinstance(sel.temperature, float))
check("temperature in [0, 1]", 0 <= sel.temperature <= 1)


# ────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────
print(f"\n{'═'*50}")
print(f"Results: {PASS} passed, {FAIL} failed out of {PASS+FAIL}")
if FAIL == 0:
    print("🎉 All model routing tests passed!")
else:
    print(f"⚠️  {FAIL} test(s) failed")
print(f"{'═'*50}")
