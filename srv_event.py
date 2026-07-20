from dataclasses import dataclass

"""
Command -> ACK/NACK
Event   -> Notification

An ACK only makes sense if somebody previously requested something.
"""

""" 20270719 NOTE: Event ACK can not existed in the multiple viewmodels
class CommandEvent:
    pass

@dataclass(frozen=True)
class ResponseACK:
    # cmd: CommandEvent
    cmd_type: type[CommandEvent]

@dataclass(frozen=True)
class QueuedACK(ResponseACK):
    pass

@dataclass(frozen=True)
class BusyNACK(ResponseACK):
    pass

@dataclass(frozen=True)
class DuplicateNACK(ResponseACK):
    pass

@dataclass(frozen=True)
class ResponseNACK(ResponseACK):
    detail: str

@dataclass(frozen=True)
class NoOpACK(ResponseACK):
    pass

class NotiEvent:
    pass

class InvalidPeriodError(ValueError):
    pass

class DuplicateKeyError(KeyError):
    pass
"""

class SrvEvent:
    pass
