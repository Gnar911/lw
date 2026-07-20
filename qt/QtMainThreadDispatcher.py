from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from lw.MainThreadDispatcher import MainThreadDispatcher


class QtMainThreadDispatcher(QObject, MainThreadDispatcher):
    _invoke = Signal(object)

    def __init__(self):
        super().__init__()

        self._invoke.connect(
            self._dispatch,
        )

    def post(
        self,
        fn: Callable[[], None],
    ) -> None:

        #
        # Can be called from ANY thread.
        #
        self._invoke.emit(fn)

    def _dispatch(
        self,
        fn: Callable[[], None],
    ) -> None:

        fn()