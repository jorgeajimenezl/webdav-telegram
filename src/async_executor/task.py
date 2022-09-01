import time
import asyncio
import functools
from enum import Enum
from threading import Lock
from typing import Callable, List, Tuple, Union
from uuid import UUID, uuid4


class TaskState(Enum):
    UNKNOW = 0
    STARTING = 1
    WORKING = 2
    SUCCESSFULL = 3
    WAITING = 4
    ERROR = 5
    CANCELED = 6


class Task(object):
    def __init__(self, **kwargs) -> None:
        self.id: UUID = uuid4()

        self._state = (TaskState.UNKNOW, None)
        self._progress: Tuple[str, str] = (None, None)
        self._lock = Lock()
        self._last_point: int = None
        self._last_time: int = None
        self._eta: int = None
        self._speed: int = None
        self._executor = None
        self._childs: List[Task] = []
        self._future = None

        self.kwargs = kwargs

    def cancel(self) -> None:
        self.cancel_childs()
        self._future.cancel()

    def cancel_childs(self) -> None:
        if self._future is None:
            raise Exception("Unable to cancel a task that hasn't been scheduled")
        if len(self._childs) > 0:
            for child in self._childs:
                child.cancel()

    async def start(self) -> None:
        # Body of the rutine to task execute
        raise NotImplementedError

    def schedule_child(
        self,
        task: "Task",
    ) -> None:
        self._executor.schedule(task, lambda t: self._childs.remove(t))
        self._childs.append(task)

    def childs(self) -> List["Task"]:
        return self._childs

    async def wait_for_childs(self) -> None:
        if self._future is None:
            raise Exception("Unable to wait a task that hasn't been scheduled")

        if len(self._childs) > 0:
            await asyncio.wait([asyncio.create_task(x.wait()) for x in self._childs])

    async def wait(self) -> None:
        await self.wait_for_childs()
        await self._future

    @property
    def state(self) -> Tuple[TaskState, str]:
        with self._lock:
            return self._state

    @property
    def progress(self) -> Tuple[int, int]:
        with self._lock:
            return self._progress

    @property
    def eta(self) -> Union[float, None]:
        with self._lock:
            return self._eta

    @property
    def speed(self) -> Union[float, None]:
        with self._lock:
            return self._speed

    def reset_stats(self) -> None:
        with self._lock:
            self._last_point = None
            self._last_time = None
            self._eta = None
            self._speed = None
            self._progress = (None, None)

    def set_state(self, state: TaskState, description: str = None) -> None:
        with self._lock:
            self._state = (state, description)
        return None

    def make_progress(self, current: int, total: int, *args, **kwargs) -> None:
        with self._lock:
            self._progress = (current, total)

            try:
                if self._last_time is None:
                    self._last_time = time.monotonic()
                    self._last_point = current
                    return

                # compute eta
                if current is not None:
                    self._speed = kwargs.get(
                        "speed",
                        (current - self._last_point)
                        / (time.monotonic() - self._last_time),
                    )
                    self._eta = kwargs.get("eta", (total - current) / self._speed)
            except Exception:
                self._eta = None
                self._speed = None

        return None

    def __hash__(self) -> int:
        return hash(self.id)


async def function_to_task(coro, *args, **kwargs) -> Task:
    task = Task(*args, **kwargs)
    task.start = coro
    return task


def to_task(func: Callable, **ctx) -> Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        task = Task(**ctx)
        task.start = functools.partial(func, *args, **kwargs)
        return task

    return wrapper
