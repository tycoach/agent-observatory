import os
import json
import time
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
import redis
from collections import defaultdict
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'redpanda:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'agent-events')
KAFKA_CONSUMER_GROUP = 'analytics-processor'
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')

# Analytics aggregation window
WINDOW_SIZE = 60  # seconds


class AnalyticsProcessor:
    """
    Processes events for real-time analytics
    Computes metrics and stores in Redis
    """
    
    def __init__(self):
        self.consumer = None
        self.redis_client = None
        self.metrics = defaultdict(lambda: defaultdict(int))
        self.window_start = time.time()
        
    def connect_kafka(self):
        """Connect to Kafka"""
        logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
        
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.consumer = KafkaConsumer(
                    KAFKA_TOPIC,
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    group_id=KAFKA_CONSUMER_GROUP,
                    auto_offset_reset='latest',  # Only process new events
                    enable_auto_commit=True,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
                )
                logger.info(f"✓ Connected to Kafka, subscribed to topic: {KAFKA_TOPIC}")
                return True
            except KafkaError as e:
                logger.error(f"Kafka connection attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return False
    
    def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            logger.info(" Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False
    
    def process_event(self, event: dict):
        """Process single event for analytics"""
        agent_id = event.get('agent_id')
        event_type = event.get('event_type')
        metadata = event.get('metadata', {})
        
        # Update metrics
        self.metrics['total']['events'] += 1
        self.metrics['by_agent'][agent_id] += 1
        self.metrics['by_type'][event_type] += 1
        
        # Track errors
        if not metadata.get('success', True):
            self.metrics['total']['errors'] += 1
            self.metrics['errors_by_agent'][agent_id] += 1
        
        # Track token usage
        if 'tokens_used' in metadata:
            self.metrics['total']['tokens'] += metadata['tokens_used']
            self.metrics['tokens_by_agent'][agent_id] += metadata['tokens_used']
        
        # Track costs
        if 'cost_usd' in metadata:
            self.metrics['total']['cost'] += metadata['cost_usd']
            self.metrics['cost_by_agent'][agent_id] += metadata['cost_usd']
    
    def flush_metrics(self):
        """Flush metrics to Redis"""
        try:
            timestamp = int(time.time())
            
            # Store metrics with timestamps
            pipe = self.redis_client.pipeline()
            
            # Total metrics
            pipe.hincrby('analytics:total:events', timestamp, self.metrics['total']['events'])
            pipe.hincrby('analytics:total:errors', timestamp, self.metrics['total']['errors'])
            pipe.hincrby('analytics:total:tokens', timestamp, self.metrics['total']['tokens'])
            pipe.hincrbyfloat('analytics:total:cost', timestamp, self.metrics['total']['cost'])
            
            # Per-agent metrics (top 100 agents)
            for agent_id, count in list(self.metrics['by_agent'].items())[:100]:
                pipe.hincrby(f'analytics:agent:{agent_id}:events', timestamp, count)
            
            # Event type distribution
            for event_type, count in self.metrics['by_type'].items():
                pipe.hincrby(f'analytics:event_type:{event_type}', timestamp, count)
            
            # Execute pipeline
            pipe.execute()
            
            # Set expiry on keys (keep 24 hours of data)
            expiry = 86400
            for key in self.redis_client.keys('analytics:*'):
                self.redis_client.expire(key, expiry)
            
            logger.info(
                f"✓ Flushed metrics: {self.metrics['total']['events']} events, "
                f"{self.metrics['total']['errors']} errors"
            )
            
            # Reset metrics
            self.metrics = defaultdict(lambda: defaultdict(int))
            self.window_start = time.time()
            
        except Exception as e:
            logger.error(f"Failed to flush metrics: {e}")
    
    def run(self):
        """Main processing loop"""
        logger.info("Analytics processor starting...")
        
        if not self.connect_kafka():
            return
        
        if not self.connect_redis():
            return
        
        logger.info(" All connections established. Processing events...")
        
        try:
            for message in self.consumer:
                try:
                    event = message.value
                    self.process_event(event)
                    
                    # Flush metrics every window
                    if time.time() - self.window_start >= WINDOW_SIZE:
                        self.flush_metrics()
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue
        
        except KeyboardInterrupt:
            logger.info("Shutdown signal received")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            # Final flush
            if self.metrics['total']['events'] > 0:
                self.flush_metrics()
            
            if self.consumer:
                self.consumer.close()
            if self.redis_client:
                self.redis_client.close()
            
            logger.info("Analytics processor stopped")


if __name__ == "__main__":
    processor = AnalyticsProcessor()
    processor.run()