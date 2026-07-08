from __future__ import annotations

import ctypes
import ctypes.wintypes
import multiprocessing as mp
import os
import selectors
import select
import time
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
# from lw.waiter.event_object import EventObject, EventFd, WinEventObject
from lw.waiter.wait_source import WaitSource
from lw.waiter.event_object import EventFd
from lw.logger_setup import LOG
TEvent = TypeVar("TEvent", bound=WaitSource)

"""
20260614
There are 2 ways to to the abstraction:
1. Using the abstract class + base object
class EventLoopWaiter(ABC):

    @abstractmethod
    def set_event(
        self,
        source: EventObject,
    ) -> None:
        ...

class EpollEventLoopWaiter(EventLoopWaiter):
    def set_event(self, source: EventObject) -> None:
    
2. Using genetic type
class EventLoopWaiter(ABC, Generic[TEvent]):

    @abstractmethod
    def set_event(self, source: TEvent) -> None:
        ...

class EpollEventLoopWaiter(EventLoopWaiter[EventFd]):

    def set_event(self, source: EventFd) -> None:
        ...
"""
class EventLoopWaiter(ABC, Generic[TEvent]):

    @abstractmethod
    def set_event(
        self,
        source: WaitSource,
    ) -> None:
        ...

    @abstractmethod
    def wait_event(self) -> WaitSource:
        ...

    @abstractmethod
    def wait_events(self) -> list[WaitSource]:
        ...

    @abstractmethod
    def close(self):
        ...

    """ This is for the unstable socket fd
    """
    @abstractmethod
    def unset_event(self, source: WaitSource) -> None:
        ...


""" 
    Cross-platform
"""
class SelectEventLoopWaiter(EventLoopWaiter[WaitSource]):
    def __init__(self) -> None:
        self._selector = selectors.DefaultSelector()

        """ selectors is designed around:
            socket
            pipe file object
            eventfd wrapper
            not raw fd integers.        

            THen using the state here only for silent fallback check duplicate
            The select it self will raise KeyError, so in development phase we dont
            want to silent fail here
        """
        #self._registered_sources: set[WaitSource] = set()
        self._registered: dict[WaitSource, object] = {}

    def set_event(self, source: WaitSource) -> None:
        if source in self._registered:
            raise RuntimeError(f"{source} already registered")

        handle = source.wait_handle
        self._selector.register(
            handle,
            selectors.EVENT_READ,
            source,
        )
        self._registered[source] = handle

    """ NOTE: We do not unregister with the source.handle because the eventloop already tracking
              the state of registering
                A = CANDevice(device_id="can0")   # fd = 17
                B = CANDevice(device_id="can0")   # fd = 42
                A == B   # True by __hash, __eq

                -> unregister with the fd 17
    """
    def unset_event(self, source: WaitSource) -> None:
        if source not in self._registered:
            raise RuntimeError(f"{source} was not registered") 
           
        #handle = source.wait_handle
        handle = self._registered.pop(source)
        self._selector.unregister(handle)


    """ Selector already maintains the registration state.
        20260618
        poll(), select() return fd only -> need to maintain fd -> object dict look up
        epoll add the epoll_event.data for store void*, return fd -> void*
        python selectors return fd -> key.data'
        Qt event loop return fd -> QOject
        Boost.Asio return fd -> handler
        libuv (NodeJS) return uv_handle_t* contains void* data which is user state
        
        OS Wait Handle
            ↓
        User Object
    """
    def wait_events(self) -> list[WaitSource]:
        events = self._selector.select(timeout=None)
        if not events:
            raise RuntimeError("selector returned no events")
        
        #20260623 BUG: Return only one events -> user iterates it 
        # key, _ = events[0]
        # return key.data
        return [key.data for key, _ in events]

    def wait_event(self) -> WaitSource:
        """Wait for a single event and return its associated WaitSource.

        This is a convenience for callers that expect a single wakeup.
        It uses the same underlying selector but returns only the first
        ready WaitSource.
        """
        events = self._selector.select(timeout=None)
        if not events:
            raise RuntimeError("selector returned no events")

        key, _ = events[0]
        return key.data

    def close(self) -> None:
        self._selector.close()
        self._registered.clear()

    def has_registered_type(self, cls: type) -> bool:
        return any(
            isinstance(key.data, cls)
            for key in self._selector.get_map().values()
        )


"""
20260613
We have 2 types of sending a command:
1. Wake up (by Event/self pipe trick Qt/epoll fd, WFWO) + read shared Value for int Enum without payload
2. Wake up (by Event/self pipe trick Qt/epoll fd, WFWO) + a shared payload (message queue, mmap file, shared mem)

To receive the command, we need to design a wait event loop, this will wait for
timeout, command event 

epoll fd → EventFd object
"""
class EpollEventLoopWaiter(EventLoopWaiter[WaitSource]):
    def __init__(self):
        self._ep = select.epoll()
        self._sources: dict[int, WaitSource] = {}
        self._registered_fds: set[int] = set()

    def set_event(self, source: WaitSource) -> None:
        fd = int(source.wait_handle)
        self._sources[fd] = source
        if fd in self._registered_fds:
            LOG.error("Event register Duplicated !")
            return

        self._ep.register(
            fd,
            select.EPOLLIN,
        )
        self._registered_fds.add(fd)

    def unset_event(self, source: WaitSource) -> None:
        fd = int(source.wait_handle)
        if fd not in self._registered_fds:
            LOG.error("Event registered Not existed")
            return

        try:
            self._ep.unregister(fd)
        except FileNotFoundError:
            pass
        except OSError:
            # Fd may already be closed/unregistered; keep teardown resilient.
            pass
        finally:
            self._registered_fds.discard(fd)
            self._sources.pop(fd, None)

    def wait_events(self) -> list[WaitSource]:
        events = self._ep.poll(timeout=None)
        if not events:
            raise RuntimeError("unexpected selector returned no events")

        # LOG.critical(
        # "EPOLL %s",
        # [(fd, mask) for fd, mask in events],
        # )
        #BUG: Return only one events -> user iterates it 
        # fd, _ = events[0]
        # return self._sources[fd]
        # `events` is a list of (fd, eventmask) tuples; map fd -> WaitSource
        return [self._sources[int(fd)] for fd, _ in events]

    def wait_event(self) -> WaitSource:
        """Wait for a single epoll event and return its associated WaitSource.

        Returns the first ready WaitSource from the poll result.
        """
        events = self._ep.poll(timeout=None)
        if not events:
            raise RuntimeError("unexpected selector returned no events")

        fd, _ = events[0]
        return self._sources[int(fd)]
    
    def close(self) -> None:
        self._ep.close()

if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _winmm = ctypes.WinDLL("winmm")
    _ntdll = ctypes.WinDLL("ntdll")
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 258
    INFINITE = 0xFFFFFFFF
    CREATE_WAITABLE_TIMER_HIGH_RESOLUTION = 0x00000002
    TIMER_ALL_ACCESS = 0x001F0003

    # winmm: timeBeginPeriod / timeEndPeriod
    _winmm.timeBeginPeriod.argtypes = (ctypes.wintypes.UINT,)
    _winmm.timeBeginPeriod.restype = ctypes.wintypes.UINT
    _winmm.timeEndPeriod.argtypes = (ctypes.wintypes.UINT,)
    _winmm.timeEndPeriod.restype = ctypes.wintypes.UINT

    # ntdll: NtSetTimerResolution(DesiredResolution_100ns, SetResolution, CurrentResolution)
    _ntdll.NtSetTimerResolution.argtypes = (
        ctypes.c_ulong,
        ctypes.c_bool,
        ctypes.POINTER(ctypes.c_ulong),
    )
    _ntdll.NtSetTimerResolution.restype = ctypes.c_long

    _kernel32.CreateWaitableTimerExW.argtypes = (
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.DWORD,
    )
    _kernel32.CreateWaitableTimerExW.restype = ctypes.wintypes.HANDLE

    _kernel32.SetWaitableTimer.argtypes = (
        ctypes.wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_longlong),
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.wintypes.BOOL,
    )
    _kernel32.SetWaitableTimer.restype = ctypes.wintypes.BOOL

    _kernel32.CancelWaitableTimer.argtypes = (ctypes.wintypes.HANDLE,)
    _kernel32.CancelWaitableTimer.restype = ctypes.wintypes.BOOL

    _kernel32.WaitForMultipleObjects.argtypes = (
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.HANDLE),
        ctypes.wintypes.BOOL,
        ctypes.wintypes.DWORD,
    )
    _kernel32.WaitForMultipleObjects.restype = ctypes.wintypes.DWORD

    _kernel32.CloseHandle.argtypes = (ctypes.wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

"""
20260622
Linux
epoll
 ├─ socket
 ├─ pipe
 └─ eventfd

Mọi thứ đều là fd-ish.

Windows
select()
 └─ socket only

WaitForMultipleObjects()
 ├─ Event
 ├─ Mutex
 ├─ Process
 └─ Thread

Hai hệ sinh thái hoàn toàn tách biệt.
"""
class WindowsEventLoopWaiter(EventLoopWaiter):
    def __init__(self, cmd_queue: mp.Queue, cmd_event: object | None = None):
        if os.name != "nt":
            raise RuntimeError("WindowsEventLoopWaiter is only available on Windows")

        # ── Force sub-ms system timer resolution ──────────────
        # timeBeginPeriod(1) sets the minimum timer resolution to 1 ms.
        # NtSetTimerResolution(5000, True, ...) requests 0.5 ms (5000 * 100 ns).
        # Both are needed: timeBeginPeriod for general Win32 waits,
        # NtSetTimerResolution for the kernel waitable-timer path.
        _winmm.timeBeginPeriod(1)
        self._timer_period_set = True
        cur = ctypes.c_ulong()
        _ntdll.NtSetTimerResolution(5000, True, ctypes.byref(cur))

        self._timer_handle = _kernel32.CreateWaitableTimerExW(
            None,
            None,
            CREATE_WAITABLE_TIMER_HIGH_RESOLUTION,
            TIMER_ALL_ACCESS,
        )
        if not self._timer_handle:
            raise OSError(ctypes.get_last_error(), "CreateWaitableTimerExW failed")

        if cmd_event is None:
            raise RuntimeError("WindowsEventLoopWaiter requires cmd_event for command wakeups")

        self._cmd_queue = cmd_queue
        self._cmd_event = cmd_event
        # multiprocessing.Event stores a kernel semaphore handle in _flag._semlock.handle.
        self._cmd_event_handle = ctypes.wintypes.HANDLE(int(self._cmd_event._flag._semlock.handle))
        self._handles = (ctypes.wintypes.HANDLE * 2)(self._timer_handle, self._cmd_event_handle)
        self._rx_sockets: list[object] = []
        # Windows cannot wait on socket FDs and kernel handles in one API call,
        # so we poll socket readability at a short interval when RX sockets exist.
        self._rx_poll_interval_s = 0.001

    def rebuild_rx_fds(self, channels, can_device, device_type) -> None:
        self._rx_sockets = []
        if not channels:
            return

        buses = getattr(can_device, "buses", {})
        for channel_idx, channel_info in channels.items():
            handle = getattr(channel_info, "handle", None)
            if handle is None:
                continue
            bus = buses.get(handle)
            if bus is None:
                continue
            sock = getattr(bus, "socket", None)
            if sock is None:
                continue
            self._rx_sockets.append(sock)

    def _has_ready_rx_socket(self) -> bool:
        if not self._rx_sockets:
            return False
        try:
            ready, _, _ = select.select(self._rx_sockets, [], [], 0.0)
            return bool(ready)
        except Exception:
            return False

    def arm_abs(self, deadline_mono_s: float) -> None:
        delay_s = max(0.0, float(deadline_mono_s) - float(time.perf_counter()))
        due_100ns = -max(1, int(delay_s * 10_000_000))
        due_time = ctypes.c_longlong(due_100ns)
        ok = _kernel32.SetWaitableTimer(self._timer_handle, ctypes.byref(due_time), 0, None, None, False)
        if not ok:
            raise OSError(ctypes.get_last_error(), "SetWaitableTimer failed")

    def wait(self, timeout_s: float | None = None) -> WaitEvent:
        deadline = None if timeout_s is None else (time.perf_counter() + max(0.0, float(timeout_s)))

        while True:
            if self._has_ready_rx_socket():
                return WaitEvent.READ

            if deadline is None:
                remaining_s = None
            else:
                remaining_s = deadline - time.perf_counter()
                if remaining_s <= 0.0:
                    return WaitEvent.TIMEOUT

            if self._rx_sockets:
                if remaining_s is None:
                    wait_ms = max(1, int(self._rx_poll_interval_s * 1000.0))
                else:
                    wait_ms = max(0, int(min(self._rx_poll_interval_s, remaining_s) * 1000.0))
            else:
                wait_ms = INFINITE if remaining_s is None else max(0, int(remaining_s * 1000.0))

            ret = _kernel32.WaitForMultipleObjects(2, self._handles, False, wait_ms)
            if ret == WAIT_OBJECT_0:
                return WaitEvent.TIMER
            if ret == WAIT_OBJECT_0 + 1:
                return WaitEvent.COMMAND
            if ret == WAIT_TIMEOUT:
                if deadline is not None and time.perf_counter() >= deadline:
                    return WaitEvent.TIMEOUT
                continue
            raise OSError(ctypes.get_last_error(), "WaitForMultipleObjects failed")

    def clear_command_signal(self) -> None:
        # Manual reset after fully draining command queue.
        self._cmd_event.clear()

    def close(self) -> None:
        if os.name != "nt":
            return
        try:
            _kernel32.CancelWaitableTimer(self._timer_handle)
        except Exception:
            pass
        _kernel32.CloseHandle(self._timer_handle)
        if getattr(self, '_timer_period_set', False):
            _winmm.timeEndPeriod(1)
            _ntdll.NtSetTimerResolution(5000, False, ctypes.byref(ctypes.c_ulong()))
            self._timer_period_set = False

""" 
    Cross-platform
"""
def create_event_loop_waiter() -> EventLoopWaiter:
    if os.name == "nt":
        return WindowsEventLoopWaiter(cmd_queue, cmd_event)
    return EpollEventLoopWaiter()
