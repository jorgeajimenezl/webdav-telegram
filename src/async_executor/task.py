import asyncio
from typing import Tuple
from threading import Lock
from enum import Enum


class TaskState(Enum):
    UNKNOW = 0
    STARTING = 1
    WORKING = 2
    SUCCESSFULL = 3
    WAITING = 4
    ERROR = 5
    CANCELED = 6


class Task(object):
    def __init__(self, id: int, *args, **kwargs) -> None:
        self.id = id

        self._state = (TaskState.UNKNOW, None)
        self._progress = (None, None)
        self._lock = Lock()
        
        self.stop = None
        self.result = None
        self.future = None

    def cancel(self):
        if self.future != None:
            self.future.cancel()

    async def start(self) -> None:
        raise NotImplementedError

    def state(self) -> Tuple[TaskState, str]:
        with self._lock:
            return self._state

    def progress(self) -> Tuple[int, int]:
        with self._lock:
            return self._progress

    def _set_state(self, state: TaskState, description: str = None) -> None:
        with self._lock:
            self._state = (state, description)
        return None

    def _make_progress(self, current: int, total: int) -> None:
        with self._lock:
            self._progress = (current, total)
        return None

    def __hash__(self) -> int:
        return self.id