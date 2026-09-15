"""Thread -> asyncio bridge for blocking token generators."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator

from ..prompting.builder import Message

_DONE = object()


async def stream_tokens(
    gen,
    system: str,
    messages: list[Message],
    max_tokens: int,
    *,
    cancel: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Run `gen.stream()` on a worker thread; yield pieces on the event loop.

    Exceptions raised by the generator are re-raised here. Setting `cancel`
    stops the worker between pieces (the caller stops consuming too).
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def put(item) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def worker() -> None:
        try:
            for piece in gen.stream(system, messages, max_tokens):
                if stop.is_set():
                    break
                put(piece)
        except BaseException as exc:  # noqa: BLE001 - forwarded to the consumer
            put(exc)
            return
        put(_DONE)

    thread = threading.Thread(target=worker, name="igihe-generate", daemon=True)
    thread.start()
    try:
        while True:
            if cancel is not None and cancel.is_set():
                stop.set()
                return
            item = await queue.get()
            if item is _DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        stop.set()
