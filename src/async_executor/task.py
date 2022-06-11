import asyncio
import time
from enum import Enum
from threading import Lock
from typing import Tuple, Union


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
        self._last_point = None
        self._last_time = None
        self._eta = None
        self._speed = None

        self.stop = None
        self.result = None
        self.future = None
        self.kwargs = kwargs

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

    def eta(self) -> Union[float, None]:
        with self._lock:
            return self._eta

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

    def _set_state(self, state: TaskState, description: str = None) -> None:
        with self._lock:
            self._state = (state, description)
        return None

    def _make_progress(self, current: int, total: int, *args, **kwargs) -> None:
        with self._lock:
            self._progress = (current, total)

            try:
                if self._last_time == None:
                    self._last_time = time.monotonic()
                    self._last_point = current
                    return

                # compute eta
                self._speed = kwargs.get(
                    "speed",
                    (current - self._last_point) / (time.monotonic() - self._last_time),
                )
                self._eta = kwargs.get("eta", (total - current) / self._speed)
            except Exception:
                self._eta = None
                self._speed = None

        return None

    def __hash__(self) -> int:
        return self.id
