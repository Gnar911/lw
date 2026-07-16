from typing import Any, Callable, Protocol


class MainThreadDispatcher(Protocol):

    def post(
        self,
        fn: Callable[[], None],
    ) -> None:
        ...