from dataclasses import dataclass
from lw.ring_buf import RingBuffer
from network_service.metrics.service import ContentPayload, send_metrics_toS3
from dataclasses import dataclass, field
from typing import Any
"""
20260630
#NOTE: Similar to how tracing/profiling tools work (Chrome Trace, Perfetto, Tracy). 
They record the start and end of each dispatched callback.
"""
""" This is domain model used by the debug caller, zero UI information"""
@dataclass(slots=True, frozen=True)
class DebugSchedulerMetric:
    RING_CAP = 50_000
    sleep_wait_s: RingBuffer[float] = RingBuffer[float](RING_CAP)
    cycle_send_latency_s: RingBuffer[float] = RingBuffer[float](RING_CAP)
    cycle_cmd_latency_s: RingBuffer[float] = RingBuffer[float](RING_CAP)

    def reset_ring_buffers(self) -> None:
        self.cycle_cmd_latency_s.clear()
        self.sleep_wait_s.clear()
        self.cycle_send_latency_s.clear()


@dataclass(slots=True)
class Region:
    label: str
    fillColor: str
    values: list[float]
    fillOpacity: float


@dataclass(slots=True)
class GraphData(ContentPayload):
    title: str
    series: list[Region] = field(default_factory=list)
    type: str = "XY_GRAPH"

class SchedulerGraphBuilder:
    suffix: str = ""

    @staticmethod
    def build(metric: DebugSchedulerMetric, user_name: str = "") -> GraphData:
        # if user_name == "":
        #     user_name="Scheduler Debug"

        user_name = user_name + " " + SchedulerGraphBuilder.suffix

        return GraphData(
            title=user_name,
            series=[
                Region(
                    label="Wait time",
                    fillColor="#85e49b",
                    fillOpacity = 0.2,
                    values=list(metric.sleep_wait_s.values()),
                ),
                Region(
                    label="Command time",
                    fillColor="#6fa3db",
                    fillOpacity = 0.2,
                    values=list(metric.cycle_cmd_latency_s.values()),
                ),
                Region(
                    label="Work time",
                    fillColor="#3384db",
                    fillOpacity = 0.2,
                    values=list(metric.cycle_send_latency_s.values()),
                ),
            ],
        )
    
"""
{
    "title": "Scheduler Debug",
    "type": "XY_GRAPH"
    "series": [
        {
            "label": "Sleep Wait",
            "color": "green",
            "values": [...]
        },
        {
            "label": "Command",
            "color": "blue",
            "values": [...]
        },
        {
            "label": "Send",
            "color": "orange",
            "values": [...]
        }
        ...
    ]
}
"""

def send_debug_metrics(user_name: str, metric: DebugSchedulerMetric):
    metadata = SchedulerGraphBuilder.build(user_name=user_name, metric=metric)
    send_metrics_toS3(metadata)
    metric.reset_ring_buffers()