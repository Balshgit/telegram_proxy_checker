import asyncio
from collections.abc import Awaitable
from typing import Any


async def run_async(*coros: Awaitable[Any], timeout: float = 10) -> tuple[Any, ...]:
    if not coros:
        raise ValueError("Set of Tasks/Futures is empty", coros)

    futures = [asyncio.ensure_future(coro) for coro in coros]

    # use task name to sort results later
    for i, future in enumerate(futures):
        future.set_name(i)

    done, pending = await asyncio.wait(futures, timeout=timeout, return_when=asyncio.FIRST_EXCEPTION)

    # all tasks done, return results
    if not pending:
        result = list(done)
        result.sort(key=lambda item: int(item.get_name()))
        return tuple(await asyncio.gather(*result))

    # timeout or error happened, cancel other tasks
    for task in pending:
        task.cancel()

    # if error happened, throw exception
    for task in done:
        task.result()

    pending_tasks = [task._coro.__qualname__ for task in pending]  # type: ignore[attr-defined]
    raise TimeoutError(f"Timeout to run async tasks {pending_tasks}", timeout)


async def run_async_assoc(coros: dict[str, Awaitable[Any]]) -> dict[str, Any]:
    results = await run_async(*coros.values())
    return dict(zip(coros.keys(), results, strict=True))
