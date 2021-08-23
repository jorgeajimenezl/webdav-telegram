from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock

import asyncio, os, inspect
from asyncio import events
from typing import Callable, Optional, Tuple
from task import Task

class TaskExecutor(object):
    def __init__(self, max_tasks: int = 10, workers: Optional[int] = None) -> None:
        super().__init__()
        self.workers = workers or min(32, os.cpu_count())
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="async_executor")
        self._semaphore = asyncio.Semaphore(max_tasks)
        self._lock = Lock()
        self._count = 0

        self._futures = []
        self._loops = []
        self._count_tasks = []
        self._threads_running = 0
    
    def _start_loop(self):
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


    async def _execute(self, task: Task, index: int):
        async with self._semaphore:
            await task.start()
            return (index, task)

    def shutdown():
        raise NotImplementedError

    def add(self, cls: type, on_end_callback: Callable[[Task], None], current_thread: bool = True, *args, **kwargs) -> Task:
        if not issubclass(cls, Task):
            raise TypeError("the task argument must be a subclass from 'Task'")

        # Instantiate task
        task = cls(id=self._count, *args, **kwargs)  
        self._count += 1

        with self._lock:
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
                future = asyncio.run_coroutine_threadsafe(self._execute(task, u), loop=self._loops[u])
                future = asyncio.wrap_future(future) # wrap to use with await
                self._count_tasks[u] += 1
            task.cancel = future.cancel
            if future.done():
                if inspect.iscoroutinefunction(on_end_callback):
                    asyncio.create_task(on_end_callback(task))
                else:
                    on_end_callback()
                return (task, None)

            def at_end(f: Future[Tuple[int, Task]]):
                # Do something with result
                if f.cancelled():
                    return

                index, task = f.result()
                with self._lock:
                    if index != -1:
                        self._count_tasks[index] -= 1
 
                    if inspect.iscoroutinefunction(on_end_callback):
                        asyncio.create_task(on_end_callback(task))
                    else:
                        on_end_callback()

            future.add_done_callback(at_end)
        
        return (task, future)

    
    