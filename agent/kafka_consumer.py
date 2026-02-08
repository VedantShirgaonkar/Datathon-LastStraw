"""
Lambda handler for AWS MSK event processing.
Automatically triggered by AWS MSK (no manual Kafka consumer needed).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import base64
import logging
from datetime import datetime, timezone
from pydantic import ValidationError

from agent.config import get_config
from agent.agent import DatabaseAgent
from agent.schemas.tool_schemas import KafkaEvent, EventSource
from agent.embedding_pipeline import process_event_for_embeddings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EventProcessor:
    """
    AWS Lambda event processor with agent integration.
    Processes events from MSK trigger (no manual Kafka consumer).
    """
    
    def __init__(self):
        self.config = get_config()
        self.agent = DatabaseAgent()
        
        logger.info(f"Initialized EventProcessor with model: {self.config.featherless_model}")
    
    def process_lambda_event(self, lambda_event: dict) -> dict:
        """
        Process Lambda event triggered by AWS MSK.
        
        Lambda MSK Event Format:
        {
            'eventSource': 'aws:kafka',
            'records': {
                'events.github-0': [
                    {
                        'topic': 'events.github',
                        'partition': 0,
                        'offset': 123,
                        'timestamp': 1234567890,
                        'key': 'base64key',
                        'value': 'base64value'
                    }
                ]
            }
        }
        
        Args:
            lambda_event: Event from AWS Lambda MSK trigger
        
        Returns:
            dict: Processing results
        """
        try:
            logger.info("=" * 80)
            logger.info("Processing MSK Lambda Event")
            logger.info("=" * 80)
            
            total_records = 0
            successful = 0
            failed = 0
            
            # Process records from all topics/partitions
            records_by_topic = lambda_event.get('records', {})
            
            for topic_partition, messages in records_by_topic.items():
                logger.info(f"Processing {len(messages)} messages from {topic_partition}")
                
                for message in messages:
                    total_records += 1
                    try:
                        # Decode base64 value
                        value_bytes = base64.b64decode(message['value'])
                        raw_event = json.loads(value_bytes)
                        
                        logger.info(f"Record {total_records}: partition={message['partition']}, offset={message['offset']}")
                        
                        # Process the message
                        success = self._process_message(raw_event)
                        
                        if success:
                            successful += 1
                        else:
                            failed += 1
                            
                    except Exception as e:
                        failed += 1
                        logger.error(f"Error processing record {total_records}: {e}", exc_info=True)
                        continue
            
            # Summary
            logger.info("=" * 80)
            logger.info(f"Processing complete: {successful}/{total_records} successful, {failed} failed")
            logger.info("=" * 80)
            
            return {
                'statusCode': 200,
                'body': {
                    'total': total_records,
                    'successful': successful,
                    'failed': failed
                }
            }
            
        except Exception as e:
            logger.error(f"Fatal error in process_lambda_event: {e}", exc_info=True)
            return {
                'statusCode': 500,
                'body': {'error': str(e)}
            }
    
    def _process_message(self, raw_event: dict) -> bool:
        """
        Process a single Kafka message.
        
        Args:
            raw_event: Raw event dictionary from MSK
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.debug(f"Raw event: {json.dumps(raw_event, indent=2)}")
            
            # Validate event schema
            event = self._validate_event(raw_event)
            
            if not event:
                logger.warning("Event validation failed, skipping")
                return False
            
            # Process through agent
            logger.info(f"Processing {event.event_type} event from {event.source}")
            response = self.agent.process_event(event)
            
            # Log results
            if response.success:
                logger.info(f"✅ Event processed successfully")
                logger.info(f"Summary: {response.summary}")
                logger.info(f"Actions: {len(response.actions_taken)}")
                for action in response.actions_taken:
                    logger.info(f"  - {action}")
            else:
                logger.error(f"❌ Event processing failed")
                logger.error(f"Errors: {response.errors}")
                return False
            
            # Generate embeddings for semantic search
            try:
                source_str = event.source.value if hasattr(event.source, 'value') else str(event.source)
                embedding_results = process_event_for_embeddings(
                    source=source_str,
                    event_type=event.event_type,
                    raw=event.raw
                )
                if embedding_results:
                    succeeded = sum(1 for r in embedding_results if r.get('success'))
                    logger.info(f"📊 Generated {succeeded}/{len(embedding_results)} embeddings for semantic search")
            except Exception as e:
                logger.warning(f"Embedding generation failed (non-blocking): {e}")
            
            logger.info("-" * 80)
            return True
            
        except Exception as e:
            logger.error(f"Error in _process_message: {e}", exc_info=True)
            return False
    
    def _validate_event(self, raw_event: dict) -> KafkaEvent | None:
        """
        Validate and parse raw Kafka event from MSK.
        
        MSK Event Format:
        {
            "event_id": "uuid",
            "source": "github|jira|notion",
            "event_type": "push|jira:issue_created|...",
            "timestamp": "2026-02-07T12:56:27Z",
            "raw": { /* original payload */ }
        }
        
        Args:
            raw_event: Raw event dictionary from Kafka/MSK
        
        Returns:
            Validated KafkaEvent or None if validation fails
        """
        try:
            # Extract required fields (MSK format)
            event_id = raw_event.get('event_id')
            source = raw_event.get('source', 'unknown')
            event_type = raw_event.get('event_type', raw_event.get('type', 'unknown'))
            timestamp_str = raw_event.get('timestamp')
            raw_payload = raw_event.get('raw', raw_event)  # Fall back to entire event if no 'raw'
            
            # Parse timestamp
            if timestamp_str:
                if isinstance(timestamp_str, str):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromtimestamp(timestamp_str, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)
            
            # Validate source
            try:
                event_source = EventSource(source.lower())
            except ValueError:
                logger.warning(f"Unknown event source: {source}, using AI_AGENT")
                event_source = EventSource.AI_AGENT
            
            # Create validated event with MSK format
            event = KafkaEvent(
                event_id=event_id,
                source=event_source,
                event_type=event_type,
                timestamp=timestamp,
                raw=raw_payload
            )
            
            return event
            
        except ValidationError as e:
            logger.error(f"Event validation error: {e}")
            return None
        
        except Exception as e:
            logger.error(f"Error validating event: {e}", exc_info=True)
            return None


def lambda_handler(event, context):
    """
    AWS Lambda handler - entry point for MSK trigger.
    
    Args:
        event: Lambda event from MSK trigger
        context: Lambda context object
    
    Returns:
        dict: Status and processing results
    """
    logger.info("Lambda function invoked")
    logger.info(f"Function: {context.function_name if context else 'local'}")
    logger.info(f"Request ID: {context.aws_request_id if context else 'N/A'}")
    
    try:
        processor = EventProcessor()
        result = processor.process_lambda_event(event)
        return result
    
    except Exception as e:
        logger.error(f"Fatal error in lambda_handler: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }


# For local testing
if __name__ == "__main__":
    """
    Local testing with sample MSK event format.
    """
    logger.info("=" * 80)
    logger.info("Local Testing Mode - MSK Lambda Handler")
    logger.info("=" * 80)
    
    # Sample MSK event format
    sample_event = {
        'eventSource': 'aws:kafka',
        'records': {
            'events.github-0': [
                {
                    'topic': 'events.github',
                    'partition': 0,
                    'offset': 123,
                    'timestamp': 1234567890,
                    'key': base64.b64encode(b'test-key').decode('utf-8'),
                    'value': base64.b64encode(json.dumps({
                        'event_id': 'test-123',
                        'source': 'github',
                        'event_type': 'push',
                        'timestamp': '2026-02-08T12:00:00Z',
                        'raw': {
                            'ref': 'refs/heads/main',
                            'commits': [{'id': 'abc123', 'message': 'Test commit'}],
                            'repository': {'name': 'test-repo'}
                        }
                    }).encode('utf-8')).decode('utf-8')
                }
            ]
        }
    }
    
    # Mock Lambda context
    class MockContext:
        function_name = "local-test"
        request_id = "local-test-123"
    
    result = lambda_handler(sample_event, MockContext())
    logger.info(f"Test result: {json.dumps(result, indent=2)}")
