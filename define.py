from __future__ import annotations
from pathlib import Path


from platformdirs import PlatformDirs
dirs = PlatformDirs(
    appname="CBCM",
    appauthor="FPT.FJP.G3D1",   # Optional
)

APPLICATION_GENERAL_STORAGE_DIRECTORY = Path(dirs.user_data_dir)
APPLICATION_GENERAL_STORAGE_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)

import tempfile
MMAP_TEMP_STORAGE_DIR = Path(tempfile.gettempdir())

# Shared memory ring name used across service boundaries.
CAN_SHARED_RING_SHM_NAME = "can_analyzer_ring_v1"

GATEWAY_FORWARD_RING_SHM_NAME = f"{CAN_SHARED_RING_SHM_NAME}_gateway_forward"