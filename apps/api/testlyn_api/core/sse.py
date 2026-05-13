from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any


async def heartbeat_generator(
    source: AsyncGenerator[dict[str, Any]],
    interval: float = 10.0,
) -> AsyncGenerator[str]:
    """
    Wraps an async data generator with SSE-formatted output.
    Emits a heartbeat comment every `interval` seconds when no data arrives.

    Each yielded value is a complete SSE chunk (including trailing newlines).
    """
    heartbeat_task: asyncio.Task[Any] | None = None
    source_task: asyncio.Task[Any] | None = None

    async def _next_event() -> dict[str, Any] | None:
        try:
            return await source.__anext__()
        except StopAsyncIteration:
            return None

    try:
        while True:
            if source_task is None or source_task.done():
                source_task = asyncio.create_task(_next_event())
            if heartbeat_task is None or heartbeat_task.done():
                heartbeat_task = asyncio.create_task(asyncio.sleep(interval))

            done, _ = await asyncio.wait(
                {source_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if source_task in done:
                result = source_task.result()
                source_task = None
                if result is None:
                    # Stream exhausted
                    yield _sse_event("done", {})
                    return
                yield _sse_data(result)
            else:
                # Heartbeat fired
                yield ": heartbeat\n\n"
    finally:
        if source_task and not source_task.done():
            source_task.cancel()
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()


def _sse_data(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
