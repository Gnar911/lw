from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass
# from lw.waiter.wait_source import WaitSource
# from lw.waiter.event_object import WinEventObject, EventFd
from typing import Protocol, Generic, TypeVar
import multiprocessing as mp 
from multiprocessing import Queue
from multiprocessing import current_process
from queue import Empty
import os
from lw.logger_setup import LOG
import threading
from multiprocessing import current_process
from lw.ipc_channel import IPCChannel

"""
#NOTE: 20260623: This is the common use Queue so it wil use the type Any, but for
        user type restriction when use the class, it supposed to be used with user specific type 
        -> we made it become generic Channel
        MessageChannel = MessageChannel[Any]

    object
    ↓
    pickle
    ↓
    copy bytes
    ↓
    pipe
    ↓
    copy bytes
    ↓
    unpickle
    ↓
    object
"""

T = TypeVar("T")
@dataclass
class _IPCEnvelope(Generic[T]):
    sender: str
    payload: T
    
class MessageChannel(IPCChannel, ABC, Generic[T]):
    """
    Self-signaling message source.

    Windows:
        Queue + Event

    Linux:
        Queue reader fd itself is the wait source.
    """

    def __init__(self, name: str, owner: str, trace: bool = False):
        self.name = name
        self.owner = owner
        self.trace = bool(trace)

        self.queue: mp.Queue = mp.Queue()
        #self.queue = mp.SimpleQueue()

    @abstractmethod
    def mc_send(self, payload: T) -> None:
        ...

    @abstractmethod
    def receive(self) -> T | None:
        """Return payload or None if empty."""
        ...

    @abstractmethod
    def receive_block(self) -> T | None:
        ...

    def _trace(self, direction: str, payload: object, sender: str, action: str) -> None:
        if not self.trace:
            return

        # LOG.critical(
        #     #"[channel=%s] %s %s %s %s fd=%s qsize=%s payload=%r",
        #     #"[channel=%s] %s %s %s %s fd=%s payload=%r",
        #     "%s %s %s %s fd=%s payload=%r",
        #     #self.name,
        #     sender,
        #     direction,
        #     self.owner,
        #     action,
        #     getattr(self, "wait_handle", "?"),
        #     #self.queue.qsize,
        #     type(payload),
        # )


class WinMessageChannel(MessageChannel[T]):
    def __init__(self, name: str, owner: str, trace: bool = False):
        super().__init__(name=name, owner=owner, trace=trace)
        self._event = mp.Event()
        self._lock = mp.Lock()

    @property
    def wait_handle(self):
        return self._event

    def mc_send(self, payload: T) -> None:
        # Always wrap payload into internal envelope with sender identity.
        env = _IPCEnvelope(sender=current_process().name, payload=payload)

        with self._lock:
            self.queue.put(env)
            self._event.set()

        self._trace("->", env.payload, sender=env.sender)

    """ Race condition: Queue empty but event is set -> fine, one more fetch
                        queue has payload but event is clear
    """
    def receive(self) -> T | None:
        with self._lock:
            try:
                env: _IPCEnvelope[T] = self.queue.get_nowait()
            except Empty:
                self._event.clear()
                return None

            if self.queue.empty():
                self._event.clear()

            self._trace("<-", env.payload, sender=env.sender)
            return env.payload


class FdMessageChannel(MessageChannel):
    def __init__(self, name: str, owner: str, trace: bool = False):
        super().__init__(name=name, owner=owner, trace=trace)

    @property
    def wait_handle(self):
        #
        # mp.Queue internally owns a pipe.
        #
        return self.queue._reader.fileno()

    def mc_send(self, payload: T) -> None:
        env = _IPCEnvelope(sender=current_process().name, payload=payload)
        self._trace("->", env.payload, sender=current_process().name, action= "SEND")
        self.queue.put(env)


    def receive(self) -> T | None:
        try:
            env: _IPCEnvelope[T] = self.queue.get_nowait()
            self._trace("<-", env.payload, sender=env.sender, action= "RECV")
            return env.payload
        except Empty:
            self._trace("<-", None, sender="", action= "RECV")
            return None
        
    def receive_block(self) -> T | None:
        try:
            env: _IPCEnvelope[T] = self.queue.get()
            self._trace("<-", env.payload, sender=env.sender, action= "RECV")
            return env.payload
        except Empty:
            self._trace("<-", None, sender="", action= "RECV")
            return None

def create_message_channel(name: str = "", owner: str = "", trace: bool = False) -> MessageChannel[T]:
    if os.name == "nt":
        return WinMessageChannel(name=name, owner=owner, trace=trace)

    return FdMessageChannel(name=name, owner=owner, trace=trace)
