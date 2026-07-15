from __future__ import annotations

import os
import multiprocessing.reduction as mp_reduction
from abc import ABC, abstractmethod
from typing import Any
from .wait_source import WaitSource, EventSouce
from typing import Protocol
import multiprocessing as mp 
from multiprocessing import Queue
from queue import Empty

""" An EventObject is self-signalable, serializable source. 
    eventfd
    threading.Event
    multiprocessing.Event
    Win32 Event
"""
class EventObject(EventSouce, ABC):
    @abstractmethod
    def set(self) -> None:
        ...

    @abstractmethod
    def unset(self) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @property
    @abstractmethod
    def wait_handle(self) -> object:
        ...

class EventFd(EventObject):
    """
        EventFd
    Trigger:
        user calls set()

    OS state:
        counter > 0

    Wakeup:
        eventfd_read()
    """
    def __init__(self) -> None:
        flags = os.EFD_NONBLOCK | os.EFD_CLOEXEC
        self._fd = os.eventfd(0, flags)

    def __getstate__(self):
        if self._fd < 0:
            raise OSError("EventFd is closed")
        # NOTE #BUG the os.fd is not share-able with spawn multi processing in python -> need to make it shared 
        # by duplicate the fd through multiprocessing's resource sharer so spawned children receive a valid descriptor.
        return {"fd": mp_reduction.DupFd(self._fd)}

    def __setstate__(self, state):
        self._fd = state["fd"].detach()

    def set(self) -> None:
        os.eventfd_write(self._fd, 1)

    def unset(self) -> None:
        try:
            while True:
                os.eventfd_read(self._fd)
        except BlockingIOError:
            pass

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    @property
    def wait_handle(self) -> int:
        return self._fd

""" NOTE: This should not being used alone, instead it is being used with the MessageChannel at Window mode"""
class WinEventObject(EventObject):
    def __init__(self) -> None:
        self._event = mp.Event()

    def set(self) -> None:
        self._event.set()

    def unset(self) -> None:
        self._event.clear()

    def close(self) -> None:
        pass

    @property
    def wait_handle(self):
        return self._event
    
def create_event_object() -> EventObject:
    if os.name == "nt":
        return WinEventObject()

    if hasattr(os, "eventfd"):
        return EventFd()

    raise NotImplementedError(
        f"No EventObject implementation for {os.name}"
    )

if os.name == "nt":
    import ctypes

    kernel32 = ctypes.windll.kernel32

    CreateEventW = kernel32.CreateEventW
    SetEvent = kernel32.SetEvent
    CloseHandle = kernel32.CloseHandle

    class WindowsWakeup(EventObject):

        def __init__(self):

            self.handle = CreateEventW(
                None,
                False,
                False,
                None,
            )

        @property
        def wait_handle(self):
            return self.handle

        def unset(self):
            pass

        def close(self):
            CloseHandle(self.handle)

        def set(self):
            ctypes.windll.kernel32.SetEvent(
                self.handle
            )