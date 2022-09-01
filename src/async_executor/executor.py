import asyncio
import inspect
import os
import traceback
from asyncio import events
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable, Optional, Tuple

from async_executor.task import Task, TaskState
from asyncio.exceptions import CancelledError


class TaskExecutor(object):
    def __init__(self, max_tasks: int = 10, workers: Optional[int] = None) -> None:
        super().__init__()
        self.workers = workers or min(32, os.cpu_count())
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="async_executor"
        )
        self._semaphore = asyncio.Semaphore(max_tasks)
        self._lock = Lock()
        self._count = 0
        self._active_count = 0

        self._futures = []
        self._loops = []
        self._count_tasks = []
        self._threads_running = 0

    def _start_loop(self) -> None:
        loop = events.new_event_loop()
        try:
            events.set_event_loop(loop)
            with self._lock:
                self._loops.append(loop)
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                events.set_event_loop(None)
                loop.close()

    async def _execute(self, task: Task, index: int) -> Tuple[int, Task]:
        async with self._semaphore:
            self._active_count += 1
            try:
                await task.start()
                task.set_state(TaskState.SUCCESSFULL)
            except CancelledError:
                task.set_state(TaskState.CANCELED, f"Task cancelled")
            except Exception as e:
                task.set_state(TaskState.ERROR, f"`{traceback.format_exc()}`")
            self._active_count -= 1

            return (index, task)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait, cancel_futures=True)
        self._count_tasks = 0
        self._threads_running = 0

    @property
    def total_count(self) -> int:
        return self._count

    @property
    def active_count(self) -> int:
        return self._active_count

    def schedule(
        self,
        task: Task,
        on_end_callback: Callable[[Task], None] = None,
        current_thread: bool = True,
    ) -> None:
        if not isinstance(task, Task):
            raise TypeError("the task argument must be a instance from 'Task'")

        # WARNING: From here, this tasks has been owned by this executor
        # task: Task = cls(*args, **kwargs)

        with self._lock:
            self._count += 1

            if current_thread:
                future = asyncio.create_task(self._execute(task, -1))
            else:
                if self._threads_running >= self.workers:
                    # Look for minimun-impact thread for run in their loop
                    u = min(range(self.workers), key=lambda x: self._count_tasks[x])
                else:
                    # Append new thread to pool
                    future = self._executor.submit(self._start_loop)
                    self._futures.append(future)
                    self._count_tasks.append(0)

                    u = self._threads_running
                    self._threads_running += 1

                # Run the coro in the minimun-impact loop
                future = asyncio.run_coroutine_threadsafe(
                    self._execute(task, u), loop=self._loops[u]
                )
                future = asyncio.wrap_future(future)  # wrap to use with await
                self._count_tasks[u] += 1

            # assign task future
            task._future = future

            if future.done():
                if on_end_callback is not None:
                    if inspect.iscoroutinefunction(on_end_callback):
                        asyncio.create_task(on_end_callback(task))
                    else:
                        on_end_callback(task)
                return task

            def at_end(f: Future[Tuple[int, Task]]):
                # Do something with result
                if f.cancelled():
                    return

                index, task = f.result()
                with self._lock:
                    if index != -1:
                        self._count_tasks[index] -= 1

                    if on_end_callback is not None:
                        if inspect.iscoroutinefunction(on_end_callback):
                            asyncio.create_task(on_end_callback(task))
                        else:
                            on_end_callback(task)

            future.add_done_callback(at_end)
            task._executor = self

        return task
