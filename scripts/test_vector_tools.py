"""Test vector_tools with real cosine similarity against pgvector."""
import sys
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
import json

from agents.tools.vector_tools import semantic_search, find_developer_by_skills

print("=" * 60)
print("TEST 1: semantic_search('Kubernetes cloud infrastructure')")
print("=" * 60)
result = semantic_search.invoke({"query": "Kubernetes cloud infrastructure"})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 2: semantic_search('data pipeline real-time', type='project_doc')")
print("=" * 60)
result = semantic_search.invoke({
    "query": "data pipeline real-time processing",
    "embedding_type": "project_doc",
    "limit": 3,
})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 3: find_developer_by_skills('Python backend API')")
print("=" * 60)
result = find_developer_by_skills.invoke({"skills": "Python backend API development"})
print(json.dumps(result, indent=2, default=str))

print("\n" + "=" * 60)
print("TEST 4: find_developer_by_skills('React TypeScript frontend')")
print("=" * 60)
result = find_developer_by_skills.invoke({"skills": "React TypeScript frontend development"})
print(json.dumps(result, indent=2, default=str))

print("\n✅ All vector_tools tests completed!")
