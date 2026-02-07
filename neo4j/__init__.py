"""
Neo4j database module for graph relationships.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from neo4j_client import Neo4jClient

__all__ = ['Neo4jClient']
