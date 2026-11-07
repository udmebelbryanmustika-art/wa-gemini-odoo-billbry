"""Private draft preparation only. Does not send WhatsApp messages."""
import asyncio
from vercel.queue import Message, subscribe
from nara_followup import TOPIC, prepare_draft

@subscribe(topic=TOPIC, consumer_group='nara-drafts', retry_after=30,
           max_attempts=3, max_concurrency=1)
async def prepare_followup(message: Message[dict[str, object]]) -> None:
    await asyncio.to_thread(prepare_draft, message.payload)
