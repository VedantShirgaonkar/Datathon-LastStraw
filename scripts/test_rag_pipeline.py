"""
Test: Agentic RAG Pipeline (Feature 1.1)
Tests retrieval, grading, generation, and the full pipeline.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# ─────────────────────────────────────────────
# 1. Test retrieval node directly
# ─────────────────────────────────────────────
print("\n═══ 1. Retrieve Node ═══")
from agents.pipelines.rag_pipeline import retrieve_node, RAGState

state: RAGState = {
    "original_query": "Kubernetes cloud infrastructure DevOps",
    "current_query": "Kubernetes cloud infrastructure DevOps",
    "retrieved_docs": [],
    "relevant_docs": [],
    "answer": "",
    "is_hallucinated": False,
    "retry_count": 0,
    "status": "start",
}

result = retrieve_node(state)
docs = result["retrieved_docs"]
check("Retrieved documents", len(docs) > 0)
check("Has similarity scores", all(d["similarity"] > 0 for d in docs))
check("Top result has content", len(docs[0]["content"]) > 10 if docs else False)
if docs:
    print(f"    Top result: {docs[0]['entity_type']}/{docs[0]['entity_id']} sim={docs[0]['similarity']:.3f}")
    print(f"    Content preview: {docs[0]['content'][:120]}...")


# ─────────────────────────────────────────────
# 2. Test grade_documents node
# ─────────────────────────────────────────────
print("\n═══ 2. Grade Documents Node ═══")
from agents.pipelines.rag_pipeline import grade_documents_node

# Use the docs from step 1
state_with_docs = {**state, "retrieved_docs": docs}
grade_result = grade_documents_node(state_with_docs)
relevant = grade_result.get("relevant_docs", [])
check("Grading completed", grade_result.get("status") in ("relevant_found", "no_relevant"))
check("At least 1 relevant doc", len(relevant) >= 1)
print(f"    {len(relevant)}/{len(docs)} marked relevant")
for d in relevant[:3]:
    print(f"      - {d['entity_type']}/{d['entity_id']} sim={d['similarity']:.3f}")


# ─────────────────────────────────────────────
# 3. Test full pipeline end-to-end
# ─────────────────────────────────────────────
print("\n═══ 3. Full RAG Pipeline ═══")
from agents.pipelines.rag_pipeline import rag_query

test_queries = [
    "Who can help with the payment service or billing system?",
    "Find someone with React and TypeScript frontend experience",
    "Which developer knows about data pipelines and real-time processing?",
]

for q in test_queries:
    print(f"\n  Query: {q}")
    t0 = time.time()
    result = rag_query(q)
    elapsed = time.time() - t0
    
    answer = result.get("answer", "")
    n_docs = len(result.get("relevant_docs", []))
    retries = result.get("retry_count", 0)
    hallucinated = result.get("is_hallucinated", False)
    status = result.get("status", "")
    
    check(f"Answer non-empty", len(answer) > 20)
    check(f"Status is done or no_context", status in ("done", "no_context", "answer_generated"))
    
    print(f"    Status: {status} | Docs: {n_docs} | Retries: {retries} | Hallucinated: {hallucinated} | Time: {elapsed:.1f}s")
    print(f"    Answer preview: {answer[:200]}...")


# ─────────────────────────────────────────────
# 4. Test rag_search tool wrapper
# ─────────────────────────────────────────────
print("\n═══ 4. RAG Tool Wrapper ═══")
from agents.tools.rag_tools import rag_search

tool_result = rag_search.invoke({"question": "Who knows about Kubernetes?"})
check("Tool returns string", isinstance(tool_result, str))
check("Tool result non-empty", len(tool_result) > 20)
print(f"    Tool result preview: {tool_result[:200]}...")


# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
print(f"\n{'═'*50}")
print(f"Results: {PASS} passed, {FAIL} failed out of {PASS+FAIL}")
if FAIL == 0:
    print("🎉 All Agentic RAG tests passed!")
else:
    print(f"⚠️  {FAIL} test(s) failed")
print(f"{'═'*50}")
