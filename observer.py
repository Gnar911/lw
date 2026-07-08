from typing import Callable, Type, TypeVar, Generic, List, Optional
from collections import UserDict

class Observable:
    def __init__(self):
        self._listeners = []

    def subscribe(self, callback):
        self._listeners.append(callback)

    def remove_subscribe(self, callback):
        self._listeners.remove(callback)

    def remove_all_subscribe(self):
        self._listeners = []

    def notify(self):
        for cb in self._listeners:
            cb()

    def notify_with_event(self, event):
        for cb in list(self._listeners):
            cb(event)

T = TypeVar("T")
class ObservableEvent(Generic[T]):
    def __init__(self, event_type: Optional[Type[T]] = None):
        self._event_type = event_type
        self._subscribers: List[Callable] = []

    def subscribe(self, cb: Callable):
        self._subscribers.append(cb)

    def notify(self, *args, **kwargs):
        for cb in self._subscribers:
            cb(*args, **kwargs)

    def remove_all_subscribes(self):
        self._subscribers = []

class ObservableDict(UserDict):
    def __init__(self, *args, on_property_changed: ObservableEvent = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_property_changed: ObservableEvent = on_property_changed

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self.on_property_changed:
            self.on_property_changed.notify(value)

    def __delitem__(self, key):
        super().__delitem__(key)
        if self.on_property_changed:
            self.on_property_changed.notify(None)

    def clear(self):
        super().clear()
        if self.on_property_changed:
            self.on_property_changed.notify(None)

class ObservableList(list):
    def __init__(self, *args, on_changed: ObservableEvent = None):
        super().__init__(*args)
        self._on_changed = on_changed

    def _notify(self):
        if self._on_changed:
            self._on_changed.notify(self)

    def append(self, item):
        super().append(item)
        self._notify()

    def insert(self, index, item):
        super().insert(index, item)
        self._notify()

    def remove(self, item):
        super().remove(item)
        self._notify()

    def pop(self, index=-1):
        item = super().pop(index)
        self._notify()
        return item

    def clear(self):
        super().clear()
        self._notify()

    def __setitem__(self, index, value):
        super().__setitem__(index, value)
        self._notify()

    def __delitem__(self, index):
        super().__delitem__(index)
        self._notify()


# from PySide6.QtCore import QObject, Signal
# class ObservableQList(QObject):
#     changed = Signal()

#     def __init__(self, iterable=None):
#         super().__init__()
#         self._data = list(iterable or [])

#     # ---- read ----
#     def __len__(self):
#         return len(self._data)

#     def __iter__(self):
#         return iter(self._data)

#     def __getitem__(self, i):
#         return self._data[i]

#     # ---- write ----
#     def append(self, item):
#         self._data.append(item)
#         self.changed.emit()

#     def extend(self, items):
#         self._data.extend(items)
#         self.changed.emit()

#     def clear(self):
#         self._data.clear()
#         self.changed.emit()