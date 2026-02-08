"""Quick verification that re-seeded embeddings produce meaningful similarity."""
import sys, json
sys.path.insert(0, "/Users/rahul/Desktop/Datathon")
from agents.tools.vector_tools import semantic_search, find_developer_by_skills

print("TEST: semantic_search('data pipeline real-time processing', type='project_doc')")
result = semantic_search.invoke({"query": "data pipeline real-time processing", "embedding_type": "project_doc", "limit": 5})
for r in result:
    print(f"  sim={r['similarity']:.4f}  {r['title']}")

print("\nTEST: find_developer_by_skills('Kubernetes cloud DevOps infrastructure')")
result = find_developer_by_skills.invoke({"skills": "Kubernetes cloud DevOps infrastructure"})
for r in result:
    print(f"  sim={r['similarity']:.4f}  {r['full_name']} ({r['role']}) - {r['team_name']}")

print("\nTEST: find_developer_by_skills('React TypeScript frontend UI')")
result = find_developer_by_skills.invoke({"skills": "React TypeScript frontend UI development"})
for r in result:
    print(f"  sim={r['similarity']:.4f}  {r['full_name']} ({r['role']}) - {r['team_name']}")

print("\n✅ Similarity verification complete!")
