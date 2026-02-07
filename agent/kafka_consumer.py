"""
Kafka consumer for ingesting engineering events.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
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
    Kafka event processor with agent integration.
    """
    
    def __init__(self):
        self.config = get_config()
        self.agent = DatabaseAgent()
        self.consumer = None
        
        logger.info(f"Initialized EventProcessor with model: {self.config.featherless_model}")
    
    def start(self):
        """
        Start consuming events from Kafka/MSK.
        Supports multiple topics and SSL/TLS for MSK.
        """
        try:
            # Parse topics list
            topics = [t.strip() for t in self.config.kafka_topics.split(',')]
            
            # Build consumer config
            consumer_config = {
                'bootstrap_servers': self.config.kafka_bootstrap_servers.split(','),
                'group_id': self.config.kafka_group_id,
                'auto_offset_reset': 'latest',
                'enable_auto_commit': True,
                'value_deserializer': lambda m: json.loads(m.decode('utf-8'))
            }
            
            # Add SSL config for MSK
            if self.config.kafka_ssl_enabled:
                consumer_config.update({
                    'security_protocol': self.config.kafka_security_protocol,
                    'ssl_check_hostname': True,
                })
            
            # Initialize Kafka consumer
            self.consumer = KafkaConsumer(**consumer_config)
            self.consumer.subscribe(topics)
            
            logger.info(f"Connected to Kafka: {self.config.kafka_bootstrap_servers}")
            logger.info(f"Subscribed to topics: {topics}")
            logger.info(f"Security: {self.config.kafka_security_protocol}")
            logger.info("Waiting for events...")
            
            # Consume messages
            for message in self.consumer:
                try:
                    self._process_message(message)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    continue
        
        except KafkaError as e:
            logger.error(f"Kafka error: {e}", exc_info=True)
            raise
        
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        
        finally:
            if self.consumer:
                self.consumer.close()
                logger.info("Kafka consumer closed")
    
    def _process_message(self, message):
        """
        Process a single Kafka message.
        
        Args:
            message: Kafka message with event data
        """
        try:
            # Extract message data
            raw_event = message.value
            
            logger.info(f"Received event from partition {message.partition}, offset {message.offset}")
            logger.debug(f"Raw event: {json.dumps(raw_event, indent=2)}")
            
            # Validate event schema
            event = self._validate_event(raw_event)
            
            if not event:
                logger.warning("Event validation failed, skipping")
                return
            
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
            
        except Exception as e:
            logger.error(f"Error in _process_message: {e}", exc_info=True)
    
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


def main():
    """
    Main entry point for Kafka consumer.
    """
    logger.info("=" * 80)
    logger.info("Database Agent - Kafka Event Processor")
    logger.info("=" * 80)
    
    try:
        processor = EventProcessor()
        processor.start()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
