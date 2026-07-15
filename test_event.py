from PySide6.QtCore import QCoreApplication
import threading
import time
from lw.logger_setup import LOG
from collections.abc import Callable
from typing import TypeVar

class QtEvent(threading.Event):
	def wait(self, timeout: float) -> bool:
		app = QCoreApplication.instance()
		deadline = time.monotonic() + timeout

		while not self.is_set():
			app.processEvents()
			super().wait(0.01)

			if time.monotonic() >= deadline:
				return self.is_set()

		return True

T = TypeVar("T")

def wait(fn: Callable[[], T], *, max_ms: float, name: str | None = None,) -> T:
    t0 = time.perf_counter()

    result = fn()

    elapsed_ms = (time.perf_counter() - t0) * 1000
	
    display_name = name or fn.__name__

    LOG.info(
        "Function %s took [%.2fms] (limit [%.2fms])",
        display_name,
        elapsed_ms,
        max_ms,
    )
    assert elapsed_ms <= max_ms, (
        f"{display_name} took {elapsed_ms:.2f} ms "
        f"(limit {max_ms:.2f} ms)"
    )

    return result