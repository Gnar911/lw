from typing import Callable


class MainThreadDispatcher:

    def post(
        self,
        fn: Callable[[], None],
    ) -> None:
        raise NotImplementedError("MainThreadDispatcher.post must be implemented")