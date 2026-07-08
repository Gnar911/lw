from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import multiprocessing as mp
from queue import Empty
from threading import RLock
import time
from typing import Any


class ServiceState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


@dataclass(slots=True)
class ServiceLifecycleEvent:
    service_name: str
    state: ServiceState
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    """Process-safe event channel for service/domain events.

    This is intentionally IPC-focused and does not keep in-process callback
    registries.
    """

    def __init__(self, ipc_queue: mp.Queue | None = None):
        self._queue = ipc_queue or mp.Queue()

    @property
    def ipc_queue(self) -> mp.Queue:
        return self._queue

    def publish(self, event: Any) -> None:
        self._queue.put(event)

    def recv(self, timeout_s: float | None = None) -> Any:
        if timeout_s is None:
            return self._queue.get()
        return self._queue.get(timeout=max(0.0, float(timeout_s)))

    def recv_nowait(self) -> Any:
        return self._queue.get_nowait()

    def drain(self, max_items: int = 256) -> list[Any]:
        items: list[Any] = []
        limit = max(1, int(max_items))
        for _ in range(limit):
            try:
                items.append(self._queue.get_nowait())
            except Empty:
                break
        return items


class BaseService(ABC):
    """Shared lifecycle skeleton for service-layer components."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.state = ServiceState.STOPPED
        self.event_bus = EventBus()
        self._lock = RLock()

    def poll_events(self, max_items: int = 256) -> list[Any]:
        return self.event_bus.drain(max_items=max_items)

    def start(self) -> None:
        with self._lock:
            if self.state in (ServiceState.STARTING, ServiceState.RUNNING):
                return
            self.state = ServiceState.STARTING
            self.event_bus.publish(ServiceLifecycleEvent(self.service_name, self.state))
            try:
                self._do_start()
                self.state = ServiceState.RUNNING
                self.event_bus.publish(ServiceLifecycleEvent(self.service_name, self.state))
            except Exception as exc:
                self.state = ServiceState.FAILED
                self.event_bus.publish(
                    ServiceLifecycleEvent(
                        self.service_name,
                        self.state,
                        payload={"error": str(exc)},
                    )
                )
                raise

    def stop(self) -> None:
        with self._lock:
            if self.state in (ServiceState.STOPPED, ServiceState.STOPPING):
                return
            self.state = ServiceState.STOPPING
            self.event_bus.publish(ServiceLifecycleEvent(self.service_name, self.state))
            try:
                self._do_stop()
            finally:
                self.state = ServiceState.STOPPED
                self.event_bus.publish(ServiceLifecycleEvent(self.service_name, self.state))

    def restart(self) -> None:
        self.stop()
        self.start()

    @abstractmethod
    def _do_start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _do_stop(self) -> None:
        raise NotImplementedError
