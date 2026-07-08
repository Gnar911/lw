from PySide6.QtCore import QCoreApplication
import threading
import time

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
	
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def wait(fn: Callable[[], T], *, max_ms: float) -> T:
    t0 = time.perf_counter()

    result = fn()

    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms <= max_ms, (
        f"{fn.__name__} took {elapsed_ms:.2f} ms "
        f"(limit {max_ms:.2f} ms)"
    )

    return result