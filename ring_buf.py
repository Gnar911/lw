from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Generic, TypeVar


T = TypeVar("T")
class RingBuffer(Generic[T]):
	def __init__(self, capacity: int):
		self._capacity = max(1, int(capacity))
		self._buffer: list[T | None] = [None] * self._capacity
		self._write_index = 0
		self._count = 0
		self._total_written = 0

	@property
	def capacity(self) -> int:
		return self._capacity

	@property
	def count(self) -> int:
		return self._count

	def append(self, value: T) -> None:
		self._buffer[self._write_index] = value
		self._write_index = (self._write_index + 1) % self._capacity
		self._total_written += 1

		if self._count < self._capacity:
			self._count += 1

	def extend(self, values: Iterable[T]) -> None:
		for value in values:
			self.append(value)

	def values(self) -> list[T]:
		if self._count == 0:
			return []

		if self._count < self._capacity:
			# Cast is safe because only written slots are returned.
			return [v for v in self._buffer[:self._count] if v is not None]

		start = self._write_index
		ordered = self._buffer[start:] + self._buffer[:start]
		return [v for v in ordered if v is not None]

	def indices(self) -> list[int]:
		if self._count == 0:
			return []
		start = self._total_written - self._count
		return list(range(start, self._total_written))

	def clear(self) -> None:
		self._buffer = [None] * self._capacity
		self._write_index = 0
		self._count = 0
		self._total_written = 0

	def __len__(self) -> int:
		return self._count

	def __iter__(self) -> Iterator[T]:
		return iter(self.values())




def _new_ring_buffer(capacity: int) -> list[float]:
	cap = max(1, int(capacity))
	return [0.0] * cap

def _ring_values(buffer: list[float], write_index: int, valid_count: int, capacity: int) -> list[float]:
	cap = max(1, int(capacity))
	if valid_count <= 0:
		return []
	if valid_count < cap:
		return list(buffer[:valid_count])
	start = int(write_index) % cap
	return list(buffer[start:] + buffer[:start])

def _new_text_ring_buffer(capacity: int) -> list[str]:
	cap = max(1, int(capacity))
	return [""] * cap

def _ring_text_values(buffer: list[str], write_index: int, valid_count: int, capacity: int) -> list[str]:
	cap = max(1, int(capacity))
	if valid_count <= 0:
		return []
	if valid_count < cap:
		return list(buffer[:valid_count])
	start = int(write_index) % cap
	return list(buffer[start:] + buffer[:start])

def _ring_int_values(buffer: list[int], write_index: int, valid_count: int, capacity: int) -> list[int]:
	cap = max(1, int(capacity))
	if valid_count <= 0:
		return []
	if valid_count < cap:
		return list(buffer[:valid_count])
	start = int(write_index) % cap
	return list(buffer[start:] + buffer[:start])

def _ring_indices(write_index: int, valid_count: int) -> list[int]:
	if valid_count <= 0:
		return []
	start_abs = max(0, int(write_index) - int(valid_count))
	end_abs = int(write_index)
	return list(range(start_abs, end_abs))
