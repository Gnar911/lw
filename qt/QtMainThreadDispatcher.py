from collections.abc import Callable

from PySide6.QtCore import QObject, Signal


class QtMainThreadDispatcher(QObject):
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