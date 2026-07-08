from __future__ import annotations

# Shared memory ring name used across service boundaries.
CAN_SHARED_RING_SHM_NAME = "can_analyzer_ring_v1"

GATEWAY_FORWARD_RING_SHM_NAME = f"{CAN_SHARED_RING_SHM_NAME}_gateway_forward"