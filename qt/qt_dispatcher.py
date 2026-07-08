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

        super().close()