from asyncio import tasks
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock

import asyncio, os, inspect
from typing import Callable
from task import Task


class TaskExecutor(object):
    def __init__(self, max_tasks: int = 10) -> None:
        super().__init__()
        self._lock = Lock()
        self._count = 0
        self._semaphore = asyncio.Semaphore(max_tasks)

    async def _execute(self, task: Task):
        async with self._semaphore:
            await task.start()
            return task

    def add(self, cls: type, on_end_callback: Callable[[Task], None], *args,
            **kwargs) -> Task:
        if not issubclass(cls, Task):
            raise TypeError("the task argument must be a subclass from 'Task'")

        # Instantiate task
        task = cls(id=self._count, *args, **kwargs)
        self._count += 1

        with self._lock:
            future = asyncio.create_task(self._execute(task))
            task.cancel = future.cancel

            if future.done():
                # Fast end
                pass

            def at_end(f: Future[Task]):
                # Do something with result
                if f.cancelled():
                    return

                task = f.result()
                with self._lock:
                    if inspect.iscoroutinefunction(on_end_callback):
                        asyncio.create_task(on_end_callback(task))
                    else:
                        on_end_callback()

            future.add_done_callback(at_end)

        return task
