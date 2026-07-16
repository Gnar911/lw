from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Generic, TypeVar

# from canapp.data_object import CANDBInfo, CANDBInfoType
from lw.logger_setup import LOG
from lw.define import APPLICATION_GENERAL_STORAGE_DIRECTORY
T = TypeVar("T")

""" 20260715: NOTE REMAKE: 
THe sql or mmap can not store the python objects or object containing the pointer because
they are not serialize-able, and can not plattern by memcpy.

struct Message {
    uint32_t id;
    std::string name;
    std::vector<Signal> signals;
};

Stack / mmap region
+---------------------------+
| id = 100                 |
| name.ptr  ------------+  |
| name.size = 8          |  |
| signals.ptr --------+  |  |
| signals.size = 20    |  |  |
+----------------------+--+-+
                       |  |
                       |  |
                       ▼  ▼
						Heap

						+---------------------+
						| "VehicleSpeed"      |
						+---------------------+

						+---------------------+
						| Signal              |
						| Signal              |
						| Signal              |
						| ...                 |
						+---------------------+

					
To serialized an objects serialization libraries do recursively serialize nested objects.
lambdas don't have a stable importable name.
QObject, Thread, Process, Socket, Lock, Future, Executor, Lambda, Generator, Coroutine
messages, signals, dict, list, str, int, float
THose method called serializer (with or without compact algorithm)
Pickle*				Python only   
Java Serialization	Java only
cereal				C++ only

The storage is only for storing bytes.
-> DBCPklHandler = Serializer + Storage

"""
class PickleStorage(Generic[T]):
    """
    Generic pickle-based object storage.

    Example
    -------
        dbc_cache = PickleStorage[CANDBInfo]("cache")

        dbc_cache.save("powertrain.dbc", candb)

        candb = dbc_cache.load("powertrain.dbc")
    """

    def __init__(self):
        self._root_dir = Path(APPLICATION_GENERAL_STORAGE_DIRECTORY)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    # def set_root_dir(self, root_dir: str | Path) -> None:
    #     self._root_dir = Path(root_dir)

    # def ensure_dir(self) -> Path:
    #     self._root_dir.mkdir(parents=True, exist_ok=True)
    #     return self._root_dir

    @staticmethod
    def _stem(path: str | Path) -> str:
        return Path(path).stem

    def get_path(self, source_path: str | Path) -> Path:
        """
        Convert

            xxx.dbc

        into

            xxx.pkl
        """
        return self._root_dir / f"{self._stem(source_path)}.pkl"

    # def exists(self, source_path: str | Path) -> bool:
    #     return self.get_path(source_path).exists()

    def list_files(self) -> list[Path]:
        if not self._root_dir.exists():
            return []

        return sorted(self._root_dir.glob("*.pkl"))

    def load(self, source_path: str | Path) -> T:
        path = self.get_path(source_path)

        # if not path.exists():
        #     LOG.warning("Pickle not found: %s", path)
        #     return None

        with path.open("rb") as f:
            obj: T = pickle.load(f)

        #LOG.info("Loaded pickle: %s", path)
        return obj


    def save(
        self,
        source_path: str | Path,
        obj: T,
    ) -> Path:

        # self.ensure_dir()

        path = self.get_path(source_path)

        with path.open("wb") as f:
            pickle.dump(
                obj,
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

        #LOG.info("Saved pickle: %s", path)

        return path

    def remove(
        self,
        source_path: str | Path,
    ) -> bool:

        return self.remove_path(
            self.get_path(source_path)
        )

    def remove_path(
        self,
        path: str | Path,
    ) -> bool:

        path = Path(path)

        # if not path.exists():
        #     return False

        path.unlink()

        #LOG.info("Removed pickle: %s", path)

        return True

    def clear(self) -> int:

        removed = 0

        for file in self.list_files():
            if self.remove_path(file):
                removed += 1

        return removed