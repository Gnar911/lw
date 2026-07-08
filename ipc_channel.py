# NOTE
# IPC_Channel
# ├── Payload storage
# │   ├── mp.Queue
# │   ├── mp.Value
# │   ├── SharedMemory
# │   └── RingBuffer
# └── Wakeup
#     ├── EventFd
#     ├── WinEvent

# class MessageChannel(WaitSource, Generic[T]):
#     queue: MessageQueue[T]
#     wakeup: EventObject

# class StatusChannel(WaitSource, Generic[T]):
#     value: SharedValue[T]
#     wakeup: EventObject


from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from lw.waiter.wait_source import WaitSource

T = TypeVar("T")

""" 20260707
    NOTE IPC Channel is more detail concept from waitsouce socket internet
    because this is using as shared-ablle object between processes, not SoC, system
"""
class IPCChannel(WaitSource, ABC, Generic[T]):
    @property
    @abstractmethod
    def wait_handle(self) -> object:
        """Object registered with QSocketNotifier/QWinEventNotifier."""
        ...

    @abstractmethod
    def mc_send(self, value: T) -> None:
        ...

    @abstractmethod
    def receive(self) -> T:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

