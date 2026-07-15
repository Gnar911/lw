from typing import Callable

from PySide6.QtCore import QSocketNotifier
import os
from lw.waiter.wait_source import WaitSource
if os.name == "nt":
    from PySide6.QtCore import QWinEventNotifier

from typing import Protocol

class EventCallback(Protocol):
    def __call__(self, status: int) -> None:
        ...

class QtEventLoopDispatcher:
    """
    StatusChannel integrated with the Qt event loop.

    Example
    -------
        channel = QtStatusChannel()
        channel.attach(self._on_parser_event)
        ...
    """

    def __init__(self):
        super().__init__()

        self._notifier = None
        self._callback: EventCallback | None = None
        self._wait_src: WaitSource | None = None

    @property
    def attached(self) -> bool:
        return self._notifier is not None

    def attach(
        self,
        wait_src: WaitSource,
        callback: EventCallback,
    ) -> None:
        """
        Register this channel with the Qt event loop.
        """

        if self._notifier is not None:
            raise RuntimeError(
                "QtStatusChannel is already attached."
            )

        self._callback = callback
        self._wait_src = wait_src

        if os.name == "nt":

            notifier = QWinEventNotifier(
                self._wait_src.wait_handle,
            )

            notifier.activated.connect(
                self._on_activated,
            )

        else:

            notifier = QSocketNotifier(
                int(self._wait_src.wait_handle),
                QSocketNotifier.Read,
            )

            notifier.activated.connect(
                self._on_activated,
            )

        self._notifier = notifier

    def detach(self) -> None:
        """
        Remove the notifier from the Qt event loop.
        """

        if self._notifier is None:
            return

        self._notifier.setEnabled(False)
        self._notifier.deleteLater()

        self._notifier = None
        self._callback = None
        self._wait_src = None

    def _on_activated(self, *_args) -> None:
        """
        Invoked by the Qt event loop.
        """

        status = self._wait_src.receive()
        self._callback(status)

    def close(self) -> None:
        if self._notifier is not None:
            self.detach()


import multiprocessing as mp
import os
import sys
import time

from PySide6.QtCore import QCoreApplication, QTimer
from lw.status_channel import StatusChannel

# from your_module import StatusChannel, QtEventLoopDispatcher


def producer(channel: StatusChannel):
    for i in range(5):
        print(f"[Producer] send {i}", flush=True)
        channel.mc_send(i)
        time.sleep(1)

    print("[Producer] done", flush=True)
    channel.mc_send(-1)


def on_status(status: int):
    print(f"[Qt] received {status}")

    if status == -1:
        print("[Qt] quitting")
        QCoreApplication.quit()


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    app = QCoreApplication(sys.argv)

    channel = StatusChannel()

    dispatcher = QtEventLoopDispatcher()
    dispatcher.attach(channel, on_status)

    proc = mp.Process(
        target=producer,
        args=(channel,),
    )

    proc.start()

    app.exec()

    proc.join()

    dispatcher.close()
    channel.close()