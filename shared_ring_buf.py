from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Generic, Protocol, TypeVar
import struct

T = TypeVar("T")


# =============================================================================
# Generic Ring Buffer
# =============================================================================
DEFAULT_MAX_ENTRIES = 10_000
# Backward-compatible alias; instances can override via max_entries.
CAPACITY = DEFAULT_MAX_ENTRIES
HEADER_STRUCT = struct.Struct("<Q")
HEADER_SIZE = HEADER_STRUCT.size


@dataclass(slots=True)
class RingHeader:
    write_idx: int = 0

class Codec(Protocol[T]):
    @classmethod
    def obj_size(cls) -> int: ...

    @classmethod
    def serialize(cls, obj: T) -> bytes: ...

    @classmethod
    def deserialize(cls, raw: bytes) -> T: ...

class SharedRingBuffer(Generic[T]):
    """ NOTE: This do not create attribute, just annotation, if you call its method, remember to pass it type"""
    CODEC: type[Codec[T]]

    def __init__(
        self,
        mmap_name: str,
        max_entries: int = CAPACITY,
        create: bool = False,
    ):
        self._create = create
        self._owner = False
        self._shm: shared_memory.SharedMemory | None = None
        self.mmap_name = mmap_name
        self.max_entries = int(max_entries)
        if self.max_entries <= 0:
            raise ValueError(f"max_entries must be > 0, got {self.max_entries}")

    @property
    def entry_size(self) -> int:
        size = int(self.CODEC.obj_size())
        if size <= 0:
            raise ValueError(f"Invalid codec object size: {size}")
        return size

    @property
    def payload_size(self) -> int:
        return self.max_entries * self.entry_size

    @property
    def shm_size(self) -> int:
        return HEADER_SIZE + self.payload_size

    @property
    def shm(self) -> shared_memory.SharedMemory:
        if self._shm is None:
            raise RuntimeError("Shared memory not opened.")
        return self._shm

    @property
    def buf(self):
        return self.shm.buf

    def open(self):
        if self._shm is not None:
            return

        if self._create:
            self._shm = shared_memory.SharedMemory(
                name=self.mmap_name,
                create=True,
                size=self.shm_size,
            )
            self._owner = True
            self.write_header(RingHeader())
        else:
            self._shm = shared_memory.SharedMemory(
                name=self.mmap_name,
                create=False,
            )

    def close(self, unlink=False):
        if self._shm is None:
            return

        self._shm.close()

        if unlink and self._owner:
            self._shm.unlink()

        self._shm = None

    def read_header(self) -> RingHeader:
        (idx,) = HEADER_STRUCT.unpack_from(self.buf, 0)
        return RingHeader(idx)

    def write_header(self, header: RingHeader):
        HEADER_STRUCT.pack_into(self.buf, 0, header.write_idx)

    def slot_offset(self, slot: int):
        return HEADER_SIZE + int(slot) * self.entry_size

    def write(self, obj: T) -> int:
        header = self.read_header()

        idx = header.write_idx
        slot = idx % self.max_entries

        offset = self.slot_offset(slot)

        raw = self.CODEC.serialize(obj)
        if len(raw) != self.entry_size:
            raise ValueError(
                f"Codec returned {len(raw)} bytes "
                f"(expected {self.entry_size})"
            )

        self.buf[offset:offset + self.entry_size] = raw

        self.write_header(RingHeader(idx + 1))
        return idx

    def read_by_index(self, idx: int) -> T:
        slot = idx % self.max_entries
        offset = self.slot_offset(slot)
        raw = bytes(self.buf[offset:offset + self.entry_size])
        return self.CODEC.deserialize(raw)

    def write_raw(self, raw: bytes) -> int:
        if len(raw) != self.entry_size:
            raise ValueError(
                f"Expected {self.entry_size} bytes, got {len(raw)}."
            )

        header = self.read_header()

        idx = header.write_idx
        slot = idx % self.max_entries

        offset = self.slot_offset(slot)

        self.buf[offset:offset + self.entry_size] = raw

        self.write_header(RingHeader(idx + 1))
        return idx

    def read_raw(self, idx: int) -> bytes:
        slot = idx % self.max_entries
        offset = self.slot_offset(slot)
        return bytes(self.buf[offset:offset + self.entry_size])

    def read_view(self, idx: int) -> memoryview:
        slot = idx % self.max_entries
        offset = self.slot_offset(slot)
        return self.buf[offset:offset + self.entry_size]