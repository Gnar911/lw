from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import os
import socket
from typing import Generic, TypeVar

""" Haikei
Domain: The explanation for the wait socket receive and IOCP theory.

TCP Socket: When package comes, it put into the queue, the socket fd of the queue is waked up
-> user call socket.receive to read bytes
NIC
 ↓
Kernel TCP stack
 ↓
Kernel receive buffer (message queue with payload/bytes)
 ↓
socket fd (socket fileno() fd)


Vendor's driver layer: When vendors own the queue
USB CAN Adapter
 ↓
Firmware
 ↓
Vendor Driver
 ↓
Vendor DLL
 ↓
Application

"""

class EventSouce(ABC):
    """
    Something that can wake an event loop.

    Examples:
        EventFd
        TimerFd
        SocketCanSource
        TcpSocketSource
        QueueSource
    """

    @property
    @abstractmethod
    def wait_handle(self) -> object:
        """
        OS waitable object.

        Linux:
            eventfd
            timerfd
            socket fd

        Windows:
            socket
            HANDLE
        """
        ...


T = TypeVar("T")

class WaitSource(ABC, Generic[T]):
    @property
    @abstractmethod
    def wait_handle(self) -> object:
        ...

    @abstractmethod
    def receive(self) -> T:
        ...

class InterruptEvent(WaitSource):
	pass


"""timerfd + epoll helpers — nanosecond-precision absolute timers for Linux.

Wraps ``timerfd_create`` / ``timerfd_settime`` via ctypes so the RT sender
can arm a CLOCK_MONOTONIC timer at an *absolute* ``perf_counter`` timestamp
and have epoll wake it with no millisecond rounding.

Usage::

    from native_sdk.timerfd_api import TimerFd

    tfd = TimerFd()                       # creates the fd
    tfd.arm_abs(deadline - SPIN_MARGIN)   # arm at absolute mono time
    os.read(tfd.fileno(), 8)              # blocks until timer fires
    tfd.close()
"""
import ctypes
import ctypes.util
import os

# ── libc binding ──────────────────────────────────────────────────────
_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)

# int timerfd_create(int clockid, int flags);
_timerfd_create = _libc.timerfd_create
_timerfd_create.argtypes = (ctypes.c_int, ctypes.c_int)
_timerfd_create.restype = ctypes.c_int

# int timerfd_settime(int fd, int flags,
#                     const struct itimerspec *new_value,
#                     struct itimerspec *old_value);
_timerfd_settime = _libc.timerfd_settime
_timerfd_settime.argtypes = (
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
)
_timerfd_settime.restype = ctypes.c_int

# ── constants ─────────────────────────────────────────────────────────
CLOCK_MONOTONIC = 1
TFD_NONBLOCK = 0o4000
TFD_CLOEXEC = 0o2000000
TFD_TIMER_ABSTIME = 1


# ── struct itimerspec ─────────────────────────────────────────────────
class _timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]


class _itimerspec(ctypes.Structure):
    _fields_ = [("it_interval", _timespec), ("it_value", _timespec)]


# ── public API ────────────────────────────────────────────────────────
class TimerFd(WaitSource):
    """Thin wrapper around a Linux ``timerfd`` file descriptor."""

    __slots__ = ("_fd",)

    def __init__(self) -> None:
        fd = _timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC)
        if fd < 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        self._fd = fd

    def fileno(self) -> int:
        return self._fd
    
    @property
    def wait_handle(self) -> int:
        return self._fd

    def arm_abs(self, t_abs_mono: float) -> None:
        """Arm the timer to fire once at absolute CLOCK_MONOTONIC *t_abs_mono*.

        *t_abs_mono* is in the same clock domain as ``time.perf_counter()``
        on Linux (both use CLOCK_MONOTONIC under the hood).
        """
        sec = int(t_abs_mono)
        nsec = int((t_abs_mono - sec) * 1_000_000_000)
        if nsec < 0:
            sec -= 1
            nsec += 1_000_000_000

        spec = _itimerspec(
            it_interval=_timespec(0, 0),
            it_value=_timespec(sec, nsec),
        )
        rc = _timerfd_settime(self._fd, TFD_TIMER_ABSTIME, ctypes.byref(spec), None)
        if rc != 0:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))

    def disarm(self) -> None:
        """Disarm the timer (set to zero)."""
        spec = _itimerspec(
            it_interval=_timespec(0, 0),
            it_value=_timespec(0, 0),
        )
        _timerfd_settime(self._fd, 0, ctypes.byref(spec), None)

    def receive(self) -> int:
        """Read and clear the timer.  Returns expiration count."""
        try:
            data = os.read(self._fd, 8)
            return int.from_bytes(data, "little")
        except BlockingIOError:
            return 0

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __del__(self) -> None:
        self.close()



""" NOTE 20260607
A pipe is a byte stream between processes.
Linux developers realized everyone was abusing pipes.

People were writing

write(fd, "x", 1);

millions of times without caring about the byte.

So Linux 2.6 introduced

eventfd()

which literally means

"I don't want a byte stream.
I just want an event."
"""
class LinuxWakeup(WaitSource):
    def __init__(self):

        self.read_fd, self.write_fd = os.pipe()
    @property
    def wait_handle(self) -> int:
        return self.read_fd

    def signal_object(self):
        return self.write_fd

    def receive(self):
        try:
            os.read(self.read_fd, 4096)
        except OSError:
            pass

    def close(self):

        try:
            os.close(self.read_fd)
        except OSError:
            pass

        try:
            os.close(self.write_fd)
        except OSError:
            pass

    def signal(self):

        os.write(
            self.write_fd,
            b"1",
        )

    
