from __future__ import annotations

import ctypes
import os
import platform
import socket
from ctypes import wintypes

from lw.logger_setup import LOG


# Win32 priority classes
HIGH_PRIORITY_CLASS = 0x00000080
REALTIME_PRIORITY_CLASS = 0x00000100

# Win32 thread priority constants
THREAD_PRIORITY_HIGHEST = 2
THREAD_PRIORITY_TIME_CRITICAL = 15


def get_machine_name() -> str:
	"""Return a stable, human-readable machine name for the current host."""
	candidates = [
		os.getenv("CAN_MACHINE_NAME", ""),
		os.getenv("COMPUTERNAME", ""),
		platform.node(),
		socket.gethostname(),
	]
	for value in candidates:
		text = str(value or "").strip()
		if text:
			return text
	return "unknown"


def _set_linux_process_name(name: str):
	"""Compatibility API: sets the current process name on Windows."""
	try:
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
		set_desc = getattr(kernel32, "SetThreadDescription", None)
		if set_desc is None:
			return

		set_desc.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR]
		set_desc.restype = wintypes.HRESULT

		get_current_thread = kernel32.GetCurrentThread
		get_current_thread.argtypes = []
		get_current_thread.restype = wintypes.HANDLE

		thread = get_current_thread()
		_ = set_desc(thread, str(name or "python"))
	except Exception:
		pass


def setup_rt(worker_name: str, priority: int):
	"""Best-effort Windows equivalent of Linux RT setup.

	Windows has no SCHED_FIFO. We map to high process/thread priority and
	verify the active values for diagnostics.
	"""
	try:
		kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

		get_current_process = kernel32.GetCurrentProcess
		get_current_process.argtypes = []
		get_current_process.restype = wintypes.HANDLE

		get_current_thread = kernel32.GetCurrentThread
		get_current_thread.argtypes = []
		get_current_thread.restype = wintypes.HANDLE

		set_priority_class = kernel32.SetPriorityClass
		set_priority_class.argtypes = [wintypes.HANDLE, wintypes.DWORD]
		set_priority_class.restype = wintypes.BOOL

		get_priority_class = kernel32.GetPriorityClass
		get_priority_class.argtypes = [wintypes.HANDLE]
		get_priority_class.restype = wintypes.DWORD

		set_thread_priority = kernel32.SetThreadPriority
		set_thread_priority.argtypes = [wintypes.HANDLE, wintypes.INT]
		set_thread_priority.restype = wintypes.BOOL

		set_thread_affinity_mask = kernel32.SetThreadAffinityMask
		set_thread_affinity_mask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
		set_thread_affinity_mask.restype = ctypes.c_size_t

		get_thread_priority = kernel32.GetThreadPriority
		get_thread_priority.argtypes = [wintypes.HANDLE]
		get_thread_priority.restype = wintypes.INT

		proc = get_current_process()
		thread = get_current_thread()

		requested_proc_class = HIGH_PRIORITY_CLASS
		if int(priority) >= 90:
			requested_proc_class = REALTIME_PRIORITY_CLASS

		requested_thread_pri = THREAD_PRIORITY_HIGHEST
		if int(priority) >= 90:
			requested_thread_pri = THREAD_PRIORITY_TIME_CRITICAL

		proc_ok = bool(set_priority_class(proc, requested_proc_class))
		thread_ok = bool(set_thread_priority(thread, requested_thread_pri))

		affinity_ok = True
		affinity_target_core: int | None = None
		cpu_count = os.cpu_count() or 1
		if cpu_count > 1:
			try:
				# Allow override; default to core 1 so core 0 stays available for OS/interrupts.
				configured_core = int(os.getenv("CAN_SDK_PIN_CORE", "1"))
				target_core = max(0, min(cpu_count - 1, configured_core))
				affinity_mask = ctypes.c_size_t(1 << target_core)
				previous_mask = int(set_thread_affinity_mask(thread, affinity_mask.value))
				affinity_ok = previous_mask != 0
				affinity_target_core = target_core
			except Exception:
				affinity_ok = False

		active_proc_class = int(get_priority_class(proc))
		active_thread_pri = int(get_thread_priority(thread))

		if not proc_ok or not thread_ok or not affinity_ok:
			err = ctypes.get_last_error()
			LOG.warning(
				"[%s] Windows RT setup not fully applied (proc_ok=%s, thread_ok=%s, affinity_ok=%s, last_error=%s)",
				worker_name,
				proc_ok,
				thread_ok,
				affinity_ok,
				err,
			)

		class_name = {
			HIGH_PRIORITY_CLASS: "HIGH_PRIORITY_CLASS",
			REALTIME_PRIORITY_CLASS: "REALTIME_PRIORITY_CLASS",
		}.get(active_proc_class, str(active_proc_class))

		LOG.info(
			"[%s] Windows scheduler active: proc_class=%s thread_priority=%s affinity_core=%s cpu_count=%s",
			worker_name,
			class_name,
			active_thread_pri,
			affinity_target_core,
			cpu_count,
		)
	except Exception as e:
		LOG.warning("[%s] Could not apply Windows RT setup: %s", worker_name, e)

