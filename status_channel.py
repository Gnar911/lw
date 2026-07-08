from __future__ import annotations

import multiprocessing as mp
import os
from abc import ABC, abstractmethod
from ctypes import c_int
from typing import Generic, TypeVar
from lw.ipc_channel import IPCChannel
from lw.waiter.event_object import *

class StatusChannel(IPCChannel[int]):
    """
    Shared status + wakeup notification.

    Producer:
        channel.send(PARSER_STATUS_DONE)

    Consumer:
        status = channel.receive()
    """

    def __init__(self, initial: int = 0):

        # payload
        self._status = mp.Value(c_int, initial)

        # wakeup
        if os.name == "nt":
            self._event = WindowsWakeup()
        else:
            self._event = EventFd()

    @property
    def wait_handle(self):
        return self._event.wait_handle

    def mc_send(self, value: int) -> None:
        self._status.value = value
        self._event.set()

    def receive(self) -> int:
        self._event.unset()  ### NOTE: Auto un-set event on Window
        return self._status.value

    def close(self) -> None:
        self._event.close()