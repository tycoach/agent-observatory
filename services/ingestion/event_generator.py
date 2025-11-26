import asyncio
import aiohttp
import random
import time
from datetime import datetime, timedelta
from typing import List
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EventGenerator:
    """
    High-performance event generator 
    """
    
    AGENT_TYPES = [
        "gpt-researcher", "data-analyzer", "code-reviewer",
        "content-writer", "web-scraper", "image-generator",
        "audio-processor", "video-analyzer", "sentiment-analyzer",
        "translation-agent"
    ]
    
    EVENT_TYPES = [
        "api_call", "decision", "error", "completion",
        "retry", "timeout", "cache_hit", "cache_miss"
    ]
    
    MODELS = [
        "gpt-4", "gpt-3.5-turbo", "claude-3-opus",
        "claude-3-sonnet", "llama-2-70b", "mistral-large"
    ]
    
    def __init__(self, api_url: str, num_agents: int = 100):
        self.api_url = api_url
        self.num_agents = num_agents
        self.agent_ids = [
            f"{agent_type}-{i:04d}"
            for agent_type in self.AGENT_TYPES
            for i in range(num_agents // len(self.AGENT_TYPES))
        ]
        self.total_sent = 0
        self.total_errors = 0
        
    def generate_event(self) -> dict:
        """Generate a realistic event"""
        agent_id = random.choice(self.agent_ids)
        event_type = random.choice(self.EVENT_TYPES)
        
        # 90% success rate
        success = random.random() < 0.9
        
        # Error events are always failures
        if event_type == "error":
            success = False
        
        metadata = {
            "model": random.choice(self.MODELS),
            "tokens_used": random.randint(50, 2000),
            "latency_ms": random.randint(200, 5000),
            "cost_usd": round(random.uniform(0.001, 0.1), 4),
            "success": success,
            "timestamp_ms": int(time.time() * 1000)
        }
        
        # Add error details for failures
        if not success:
            metadata["error_code"] = random.choice([
                "timeout", "rate_limit", "invalid_input",
                "service_unavailable", "auth_failed"
            ])
            metadata["error_message"] = f"Simulated error: {metadata['error_code']}"
        
        return {
            "agent_id": agent_id,
            "event_type": event_type,
            "metadata": metadata
        }
    
    async def send_event(self, session: aiohttp.ClientSession, event: dict):
        """Send a single event"""
        try:
            async with session.post(
                f"{self.api_url}/events",
                json=event,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 201:
                    self.total_sent += 1
                    return True
                else:
                    self.total_errors += 1
                    return False
        except Exception as e:
            self.total_errors += 1
            return False
    
    async def send_batch(self, session: aiohttp.ClientSession, batch_size: int):
        """Send a batch of events concurrently"""
        events = [self.generate_event() for _ in range(batch_size)]
        tasks = [self.send_event(session, event) for event in events]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run(
        self,
        total_events: int,
        batch_size: int = 100,
        delay_between_batches: float = 0.1
    ):
        """
        Run the event generator
        
        Args:
            total_events: Total number of events to generate
            batch_size: Number of concurrent requests per batch
            delay_between_batches: Delay in seconds between batches
        """
        logger.info(f"Starting event generator...")
        logger.info(f"  Target: {total_events:,} events")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Number of agents: {len(self.agent_ids)}")
        
        start_time = time.time()
        
        connector = aiohttp.TCPConnector(limit=500)
        async with aiohttp.ClientSession(connector=connector) as session:
            batches = (total_events + batch_size - 1) // batch_size
            
            for batch_num in range(batches):
                current_batch_size = min(batch_size, total_events - batch_num * batch_size)
                
                await self.send_batch(session, current_batch_size)
                
                # Progress update every 10 batches
                if (batch_num + 1) % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = self.total_sent / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"Progress: {self.total_sent:,}/{total_events:,} events "
                        f"({rate:.0f} events/sec, {self.total_errors} errors)"
                    )
                
                # Small delay to prevent overwhelming the system
                if delay_between_batches > 0:
                    await asyncio.sleep(delay_between_batches)
        
        elapsed = time.time() - start_time
        final_rate = self.total_sent / elapsed if elapsed > 0 else 0
        
        logger.info("\n" + "="*70)
        logger.info("INGESTION COMPLETE")
        logger.info("="*70)
        logger.info(f"  Total sent: {self.total_sent:,} events")
        logger.info(f"  Total errors: {self.total_errors:,}")
        logger.info(f"  Duration: {elapsed:.2f} seconds")
        logger.info(f"  Throughput: {final_rate:.0f} events/second")
        logger.info("="*70)


async def main():
    parser = argparse.ArgumentParser(description="Event Generator for Agent Observatory")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API URL"
    )
    parser.add_argument(
        "--events",
        type=int,
        default=10000,
        help="Total number of events to generate"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of concurrent requests per batch"
    )
    parser.add_argument(
        "--agents",
        type=int,
        default=100,
        help="Number of unique agents to simulate"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Delay between batches (seconds)"
    )
    
    args = parser.parse_args()
    
    generator = EventGenerator(
        api_url=args.api_url,
        num_agents=args.agents
    )
    
    await generator.run(
        total_events=args.events,
        batch_size=args.batch_size,
        delay_between_batches=args.delay
    )


if __name__ == "__main__":
    asyncio.run(main())