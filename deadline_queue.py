from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar
from abc import ABC, abstractmethod

K = TypeVar("K")
class IDeadlineQueue(Generic[K], ABC):

    """ 20260630: 
        - haikei: the heapq is unable to remove the being inserted item until that item is bubbled up, 
        so if the item is not considered valid -> remove it and proceed to next item
        - tsuka: To control the valid invalid output, the default have no
        valid rule, so let it return True, override this with your rule if needed.
    """
    # @abstractmethod
    def is_valid(self, key: K) -> bool:
        return True
    
    @abstractmethod
    def peek(self) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def push(self, key: K, deadline: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def take_due(self) -> list[K]:
        raise NotImplementedError
    
    @abstractmethod
    def pop(self):
        raise NotImplementedError
    

""" 20260626: Key is necessary to distingish the float value identiry, not just pop it"""
# @dataclass(frozen=True, slots=True)
# class deadlineEntry(Generic[K]):
#     key: K
#     deadline: float
@dataclass(order=True, frozen=True, slots=True)
class DeadlineEntry(Generic[K]):
    deadline: float
    key: K = field(compare=False)

class DeadlineQueue(IDeadlineQueue[K]):
    """
    1. Generic deadline queue with a small tolerance window when collecting ready entries.
    2. Because it is still a queue, so after pop due it will be removed from the queue
    3. Since each due pop will return a batch of entries, then the ordering comparison not necessary, the key is only for the identity 
    Ordering: deadline -> key
    """

    def __init__(self) -> None:
        self.window_s = float(0.00005)  # window 0.05 ms = 50us resolution ?

        """ NOTE: Using a Tuple instead of DeadlineEntry type here because it is Comaparable Type"""
        """ BUG: 20260630 -> Make the dataclass to be comparable -> no need to store the tuplet anymore"""
        #self._heap: list[tuple[float, K]] = []
        self._heap: list[DeadlineEntry] = []

    @property
    def size(self) -> int:
        return len(self._heap)

    def clear(self) -> None:
        self._heap.clear()

    """ 
    heapq is not an object.
    It's a module of functions that mutate a list. 
    self._heap must be a list (or a compatible mutable sequence implementing the required list operations).
    So it could be duplicated.
    """
    def push(
        self,
        key: K,
        deadline: float,
    ) -> None:
        # Store a DeadlineEntry instance so heap ordering is by deadline.
        heapq.heappush(self._heap, DeadlineEntry(float(deadline), key))

    # def peek(self) -> float | None:
    #     if not self._heap:
    #         return None

    #     deadline, _ = self._heap[0]
    #     return deadline
    #     # return deadlineEntry(
    #     #     key=key,
    #     #     deadline=deadline,
    #     # )

    def peek(self) -> float | None:
        while self.size:
            entry = self._heap[0]
            if self.is_valid(entry.key):
                return float(entry.deadline)

            self.pop()

        return None

    """ Remove smallest element from the deadline queue"""
    def pop(self) -> DeadlineEntry[K]:
        # heap stores DeadlineEntry instances
        return heapq.heappop(self._heap)

    """ The queue is containing the float number represent the timepoint and organize them as the [0] is smallest
        next deadline = 2.00
        window        = 0.14

        Normal case:

        wake = 2.00

        pop_due(2.00)
            -> [2.00 .. 2.14]

        Then next wait:

        peek = 2.20

        sleep until 2.20

        But suppose the OS stalls you:

        expected wake = 2.20
        actual wake   = 2.50

        Now you're already late.

        If you do:

        due = pop_due(now=2.50)

        then:

        cutoff = 2.64

        and you'll collect:

        2.20
        2.25
        2.30
        ...
        2.60

        all in one batch.
    """ 
    def take_due(self) -> list[K]:
        due: list[K] = []
        now = time.perf_counter()

        cutoff = now + max(0.0, self.window_s)

        while self._heap:
            entry = self._heap[0]
            deadline = entry.deadline
            key = entry.key

            if deadline > cutoff:
                break

            heapq.heappop(self._heap)

            due.append(key)

        return due