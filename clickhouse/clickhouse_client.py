"""
ClickHouse client for time-series analytics and event storage.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, date
import json

import clickhouse_connect
from clickhouse_connect.driver import Client

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config


class ClickHouseClient:
    """
    ClickHouse Cloud client for analytics queries and event storage.
    
    Usage:
        client = ClickHouseClient()
        
        # Insert events
        client.insert_event({
            'source': 'github',
            'event_type': 'commit',
            'project_id': 'proj123',
            'actor_id': 'john@company.com',
            'metadata': {'lines_added': 50}
        })
        
        # Query events
        results = client.query('''
            SELECT actor_id, count() as commits
            FROM events
            WHERE event_type = 'commit'
            GROUP BY actor_id
        ''')
    """
    
    def __init__(self):
        """Initialize ClickHouse client with connection pooling"""
        self.config = config.clickhouse
        self._client: Optional[Client] = None
    
    @property
    def client(self) -> Client:
        """Get or create ClickHouse client (lazy loading)"""
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                database=self.config.database,
                secure=True  # Use HTTPS
            )
        return self._client
    
    def verify_connection(self) -> Dict[str, Any]:
        """
        Test connection and return server info.
        
        Returns:
            Dictionary with server version and status
        """
        try:
            result = self.client.query("SELECT version()")
            version = result.result_rows[0][0]
            
            return {
                'connected': True,
                'version': version,
                'host': self.config.host,
                'database': self.config.database
            }
        except Exception as e:
            return {
                'connected': False,
                'error': str(e)
            }
    
    def query(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute SELECT query and return results as list of dictionaries.
        
        Args:
            sql: SQL query string
            parameters: Optional query parameters (use %(name)s in SQL)
        
        Returns:
            List of dictionaries, one per row
        
        Example:
            results = client.query('''
                SELECT actor_id, count() as cnt
                FROM events
                WHERE project_id = %(project)s
                GROUP BY actor_id
            ''', {'project': 'proj123'})
        """
        result = self.client.query(sql, parameters=parameters or {})
        
        # Convert to list of dictionaries
        columns = result.column_names
        rows = []
        for row in result.result_rows:
            rows.append(dict(zip(columns, row)))
        
        return rows
    
    def command(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Execute DDL or DML command (CREATE, INSERT, ALTER, etc).
        
        Args:
            sql: SQL command string
            parameters: Optional parameters
        
        Example:
            client.command("INSERT INTO events (event_id, timestamp, source) ...")
        """
        self.client.command(sql, parameters=parameters or {})
    
    def insert_event(self, event: Dict[str, Any]) -> None:
        """
        Insert a single event into the events table.
        
        Args:
            event: Dictionary with event data
                Required: source, event_type, project_id, actor_id
                Optional: entity_id, entity_type, metadata, timestamp
        
        Example:
            client.insert_event({
                'source': 'github',
                'event_type': 'commit',
                'project_id': 'proj123',
                'actor_id': 'john@company.com',
                'entity_id': 'abc123def',
                'entity_type': 'commit',
                'metadata': {'lines_added': 50, 'lines_deleted': 10}
            })
        """
        # Generate event_id and timestamp if not provided
        timestamp = event.get('timestamp', datetime.utcnow())
        
        # Convert metadata dict to JSON string
        metadata = event.get('metadata', {})
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)
        
        self.client.insert(
            'events',
            [[
                event['source'],
                event['event_type'],
                timestamp,
                event['project_id'],
                event['actor_id'],
                event.get('entity_id', ''),
                event.get('entity_type', ''),
                metadata
            ]],
            column_names=[
                'source', 'event_type', 'timestamp', 'project_id',
                'actor_id', 'entity_id', 'entity_type', 'metadata'
            ]
        )
    
    def insert_events_batch(self, events: List[Dict[str, Any]]) -> None:
        """
        Insert multiple events in a single batch (much faster).
        
        Args:
            events: List of event dictionaries
        
        Example:
            client.insert_events_batch([
                {'source': 'github', 'event_type': 'commit', ...},
                {'source': 'jira', 'event_type': 'issue_updated', ...},
            ])
        """
        if not events:
            return
        
        rows = []
        for event in events:
            timestamp = event.get('timestamp', datetime.utcnow())
            metadata = event.get('metadata', {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata)
            
            rows.append([
                event['source'],
                event['event_type'],
                timestamp,
                event['project_id'],
                event['actor_id'],
                event.get('entity_id', ''),
                event.get('entity_type', ''),
                metadata
            ])
        
        self.client.insert(
            'events',
            rows,
            column_names=[
                'source', 'event_type', 'timestamp', 'project_id',
                'actor_id', 'entity_id', 'entity_type', 'metadata'
            ]
        )
    
    def get_dora_metrics(
        self,
        project_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get DORA metrics for a project from materialized view.
        
        Args:
            project_id: Project identifier
            days: Number of days to look back (default 30)
        
        Returns:
            List of daily metrics
        
        Example:
            metrics = client.get_dora_metrics('proj123', days=30)
        """
        return self.query('''
            SELECT 
                date,
                deployments,
                avg_lead_time_hours,
                prs_merged,
                story_points_completed
            FROM dora_daily_metrics
            WHERE project_id = %(project_id)s
              AND date >= today() - %(days)s
            ORDER BY date
        ''', {'project_id': project_id, 'days': days})
    
    def get_developer_activity(
        self,
        actor_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get developer activity summary.
        
        Args:
            actor_id: Developer email or username
            days: Number of days to look back (default 30)
        
        Returns:
            Dictionary with activity counts
        
        Example:
            activity = client.get_developer_activity('john@company.com', days=30)
        """
        results = self.query('''
            SELECT 
                countIf(event_type = 'commit') as commits,
                countIf(event_type = 'pr_opened') as prs_opened,
                countIf(event_type = 'pr_merged') as prs_merged,
                countIf(event_type = 'pr_reviewed') as reviews,
                countIf(event_type = 'issue_completed') as issues_completed
            FROM events
            WHERE actor_id = %(actor_id)s
              AND timestamp >= now() - INTERVAL %(days)s DAY
        ''', {'actor_id': actor_id, 'days': days})
        
        return results[0] if results else {}
    
    def get_event_count(self) -> int:
        """Get total number of events in database"""
        result = self.query("SELECT count() as cnt FROM events")
        return result[0]['cnt'] if result else 0
    
    def get_recent_events(
        self,
        limit: int = 10,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get most recent events.
        
        Args:
            limit: Number of events to return
            source: Optional source filter (github, jira, etc)
        
        Returns:
            List of recent events
        """
        where_clause = f"WHERE source = %(source)s" if source else ""
        
        return self.query(f'''
            SELECT 
                timestamp,
                source,
                event_type,
                project_id,
                actor_id,
                entity_id
            FROM events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT %(limit)s
        ''', {'limit': limit, 'source': source})
    
    def close(self):
        """Close the database connection"""
        if self._client:
            self._client.close()
            self._client = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# Example usage
if __name__ == "__main__":
    client = ClickHouseClient()
    
    # Test connection
    info = client.verify_connection()
    print(f"Connected: {info}")
    
    # Get event count
    count = client.get_event_count()
    print(f"Total events: {count}")
