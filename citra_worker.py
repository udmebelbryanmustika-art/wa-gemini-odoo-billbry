"""Private Vercel Queue subscriber. No public unauthenticated worker route."""
import asyncio
import logging
from vercel.queue import Message, subscribe
from zapclaw_bridge import TOPIC, Store, process_job


@subscribe(topic=TOPIC, consumer_group='citra-replies', retry_after=20,
           max_attempts=4, max_concurrency=1)
async def reply_to_customer(message: Message[dict[str, object]]) -> None:
    try:
        await asyncio.to_thread(process_job, message.payload)
    except Exception:
        if message.metadata.delivery_count >= 4:
            store = Store()
            store.command('SET', message.payload['chat'] + ':handoff', 'processing_failed', 'EX', 86400)
            logging.getLogger(__name__).warning('zapclaw_processing_failed')
            return
        raise
