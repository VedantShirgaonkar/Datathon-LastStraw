"""
ClickHouse database module for time-series analytics and event storage.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from clickhouse_client import ClickHouseClient

__all__ = ['ClickHouseClient']
