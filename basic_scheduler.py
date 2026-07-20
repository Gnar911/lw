from __future__ import annotations

"""
    1. TimerFd
    Trigger:
        kernel timer expires

    OS state:
        timer readable

    Wakeup:
        read(timerfd)

	IPC no payload
    2. EventObject (EventFd, mp.Event, Win32 Event)
    Trigger:
        user calls set()

    OS state:
        counter > 0

    Wakeup:
        eventfd_read()

	IPC payload
    3. Queue
    Trigger:
        queue.put()

    OS state:
        queue fd readable

    Wakeup:
        queue.get()

	Network wire
	4. CAN Socket
	Trigger:
		CAN frame arrives

	OS state:
		socket readable

	Wakeup:
		recv()

	Network wireless
	5. TCP Socket
	Trigger:
		network packet arrives

	OS state:
		socket readable

	Wakeup:
		recv()

"""

import os
import time
from typing import Callable, Protocol

from native_sdk.api import busy_spin_until as _native_busy_spin_until
# from can_service.config.cfg_types import EventDriven, WakeupMode
# from can_service.config.load_config import load_runtime_config
""" Cross platform Waiter"""
from lw.waiter.event_loop_waiter import SelectEventLoopWaiter, create_event_loop_waiter 
from lw.waiter.event_object import EventObject
from lw.waiter.wait_source import WaitSource, InterruptEvent
import multiprocessing as mp
from lw.waiter.wait_source import TimerFd
from queue import Empty
from typing import Type, TypeVar, Any

class WaitEvent:
	pass

class ExceptEvent:
	pass

TExceptEvent = TypeVar("TExceptEvent", bound=ExceptEvent)
TWaitEvent = TypeVar("TWaitEvent", bound=WaitEvent)

class TimerScheduler(Protocol):
	def __init__(self):
		...

	def wait_until(self, target_deadline: float) -> float:
		...
	
class EventTimerScheduler:
	""" High accuracy, no use message_queue here, no interrupt
	"""
	def __init__(self):
		self._waiter = create_event_loop_waiter()
		self._spin_margin_s = 0.0007 if os.name == "nt" else 0.0002
		self.timer_fd = TimerFd()
		self._waiter.set_event(self.timer_fd)

	def wait_until(self, target_deadline: float) -> float:
		spin_start = target_deadline - self._spin_margin_s
		self.timer_fd.arm_abs(spin_start)
		self._waiter.set_event(self.timer_fd)

		while True:
			event = self._waiter.wait()
			if event is self.timer_fd:
				""" need to spin to make sure the fine coarse the deadline"""
				break
					
		""" Can not interrupt fine coarse"""
		spin_entry_time = time.perf_counter()
		if spin_entry_time < target_deadline:
			wake_time = float(_native_busy_spin_until(target_deadline))
		else:
			wake_time = spin_entry_time

		return wake_time

class EventTimerInterruptableScheduler(EventTimerScheduler):
	""" High accuracy, no use message_queue here, for interrupt -> using the shared Value flag
	"""
	def __init__(self, itr_event: EventObject, itr_value: InterruptEvent):
		super().__init__()
		self.itr_event = itr_event
		self.itr_value = itr_value
		self._waiter.set_event(self.itr_event)

	def wait_until_or_interrupt(self, target_deadline: float) -> InterruptEvent | float:
		spin_start = target_deadline - self._spin_margin_s
		self.timer_fd.arm_abs(spin_start)

		while True:
			event = self._waiter.wait()
			if event is self.timer_fd:
				""" need to spin to make sure the fine coarse the deadline"""
				break
			elif event is self.itr_event:
				self.itr_event.unset()
				return self.itr_value
					
		""" Can not interrupt fine coarse"""
		spin_entry_time = time.perf_counter()
		if spin_entry_time < target_deadline:
			wake_time = float(_native_busy_spin_until(target_deadline))
		else:
			wake_time = spin_entry_time

		return wake_time
	

class MessageQueueScheduler:
	""" Latency and unstable, use for payload handling only, avoid use in RT loop"""
	def __init__(self, cmd_queue: mp.Queue):
		self._waiter = create_event_loop_waiter()
		self.cmd_queue = cmd_queue
		self.cmd_reader_fd = cmd_queue._reader.fileno()
		self._waiter.set_event(self.cmd_reader_event)

	""" One wake up could be many payload inside the queue, so we need to check all
	"""
	def handle_queue_until_empty(self, do_it: Callable = None):
		drained_count = 0
		#self._waiter.set_event(self.cmd_reader_fd)
		
		while True:
			""" Waiter is being shared between the class, then we should use while True if it is return other event"""
			ev = self._waiter.wait()

			if ev == self.cmd_reader_fd:
				while True:
					try:
						pending_cmd = self.cmd_queue.get_nowait()
					except Empty:
						break
					drained_count += 1
					do_it(pending_cmd)
				return

	""" Handle the process queue command until queue empty or except some event type, 
		then will return at that event and drop the queue
	"""
	def handle_queue_until_except_or_empty(self, expt_evt_type: Type[TExceptEvent], do_it: Callable = None) -> TExceptEvent | int:
		drained_count = 0
		#self._waiter.set_event(self.cmd_reader_fd)
		
		while True:
			ev = self._waiter.wait()

			if ev == self.cmd_reader_fd:
				while True:
					try:
						pending_cmd = self.cmd_queue.get_nowait()
					except Empty:
						break
					do_it(pending_cmd)	
					if not isinstance(pending_cmd, expt_evt_type):
						drained_count += 1
						continue
					return pending_cmd
				return drained_count
	
	""" Wait queue until the tartget event come then return target cmd with event type 
	"""
	def wait_for_event(self, evt_type: type[TWaitEvent]) -> TWaitEvent:
		while True:
			ev = self._waiter.wait()

			if ev is not self.cmd_reader_event:
				raise RuntimeError()

			while True:
				try:
					pending_cmd = self.cmd_queue.get_nowait()
				except Empty:
					break

				if isinstance(pending_cmd, evt_type):
					return pending_cmd

class BusySpin:
	def wait_until(self, target_deadline: float) -> float:
		return float(_native_busy_spin_until(target_deadline))

class SchedulerFactory:
	@staticmethod
	def create_mq_scheduler(cmd_queue: mp.Queue) -> MessageQueueScheduler:
		return MessageQueueScheduler(cmd_queue)

	@staticmethod
	def create_timer_scheduler(itr_event: EventObject, itr_value: Any) -> TimerScheduler:
		runtime_cfg = load_runtime_config()
		if runtime_cfg.schedule_mode is EventDriven:
			return EventTimerScheduler(itr_event, itr_value)
		return BusySpin()