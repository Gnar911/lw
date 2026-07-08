from __future__ import annotations

from typing import Callable

from lw.message_queue_channel import MessageChannel
from lw.waiter.event_loop_waiter import create_event_loop_waiter
from lw.logger_setup import LOG

#TODO: Should create a basic event loop with internal event interruipt exit and expose a method for shutdown
# When call -> trigger the interrupt event to close the queue. #BUG: The problem is the interrupt exit event can not be share-able
# via multi process

class ExitLoop:
    pass

class MessageQueueEventLoop:
    """Dispatcher loop driven by MessageChannel signaling."""

    def __init__(self, channel: MessageChannel):
        self._waiter = create_event_loop_waiter()
        self._channel = channel
        self._waiter.set_event(channel)

    def run_dispatcher_loop(self, do_it: Callable[[object], None]) -> None:
        """Run forever: wait channel signal, then dispatch all queued payloads."""
        while True:
            ev = self._waiter.wait_event()
            if ev is not self._channel:
                continue

            while True:
                pending_cmd = self._channel.receive()
                if pending_cmd is None:
                    break

                if isinstance(pending_cmd, ExitLoop):
                    self._waiter.close()
                    return
                
                do_it(pending_cmd)

    def run_dispatcher_loop_wait_on_queue(self, do_it: Callable[[object], None]) -> None:
        """Run forever: wait channel signal, then dispatch all queued payloads."""
        while True:
                try:
                    pending_cmd = self._channel.receive_block()
                except EOFError:
                    LOG.info("Channel closed.")
                    return

                if isinstance(pending_cmd, ExitLoop):
                    self._waiter.close()
                    return
                do_it(pending_cmd)
