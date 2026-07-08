
import ctypes
import getpass
import os
import platform
import resource
import socket
import subprocess
import time
from pathlib import Path
from setproctitle import setproctitle as _setproctitle
from lw.logger_setup import LOG, setup_logger

_SETUP_SCRIPT = Path(__file__).resolve().parent / "setup_rt_linux.sh"


def get_machine_name() -> str:
    """Return a stable, human-readable machine name for the current host."""
    candidates = [
        os.getenv("CAN_MACHINE_NAME", ""),
        os.getenv("HOSTNAME", ""),
        platform.node(),
        socket.gethostname(),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return "unknown"


def _configure_sched_rt_runtime_us(worker_name: str) -> None:
    """Validate Linux RT throttling setting for SEND worker.

    One-time setup script is responsible for privileged writes.
    Runtime worker code does not escalate permissions.

    Override behavior with env var:
      - CAN_SEND_SCHED_RT_RUNTIME_US=-1      (default for SEND)
      - CAN_SEND_SCHED_RT_RUNTIME_US=950000  (or any integer)
      - CAN_SEND_SCHED_RT_RUNTIME_US=keep    (skip write)
    """
    if worker_name != "SEND":
        return

    runtime_cfg = str(os.getenv("CAN_SEND_SCHED_RT_RUNTIME_US", "-1")).strip().lower()
    if runtime_cfg in ("", "keep", "default"):
        LOG.info("[%s] Keep existing sched_rt_runtime_us (CAN_SEND_SCHED_RT_RUNTIME_US=%r)", worker_name, runtime_cfg)
        return

    try:
        desired_runtime = int(runtime_cfg)
    except ValueError:
        LOG.warning("[%s] Invalid CAN_SEND_SCHED_RT_RUNTIME_US=%r; expected integer or 'keep'", worker_name, runtime_cfg)
        return

    runtime_path = "/proc/sys/kernel/sched_rt_runtime_us"
    try:
        with open(runtime_path, "r", encoding="utf-8") as f:
            current_runtime = int(f.read().strip())
    except Exception:
        current_runtime = None

    if current_runtime == desired_runtime:
        LOG.info("[%s] sched_rt_runtime_us already %s", worker_name, desired_runtime)
        return

    LOG.warning(
        "[%s] sched_rt_runtime_us is %s (expected %s). "
        "Run preflight setup once to apply privileged RT settings.",
        worker_name,
        current_runtime,
        desired_runtime,
    )

def _set_linux_process_name(name: str):
    """
    Set process display name from inside worker process.
    - Prefer setproctitle (updates process title shown by many tools).
    - Fallback to prctl(PR_SET_NAME) for Linux comm (15-char visible limit).
    """
    target_name = str(name or "python3")

    if _setproctitle is not None:
        try:
            _setproctitle(target_name)
            return
        except Exception:
            pass

    try:
        short_name = target_name[:15]
        libc = ctypes.CDLL(None)
        PR_SET_NAME = 15
        buf = ctypes.create_string_buffer(short_name.encode("utf-8"))
        libc.prctl(PR_SET_NAME, ctypes.byref(buf), 0, 0, 0)
    except Exception:
        pass   


def _read_linux_cpu_times() -> dict[int, tuple[int, int]]:
    snapshots: dict[int, tuple[int, int]] = {}
    try:
        with open("/proc/stat", "r", encoding="utf-8") as fp:
            for line in fp:
                if not line.startswith("cpu"):
                    continue
                parts = line.split()
                cpu_label = parts[0]
                if cpu_label == "cpu" or not cpu_label[3:].isdigit():
                    continue

                core_id = int(cpu_label[3:])
                counters = [int(x) for x in parts[1:]]
                if len(counters) < 4:
                    continue

                idle = counters[3] + (counters[4] if len(counters) > 4 else 0)
                total = sum(counters)
                snapshots[core_id] = (idle, total)
    except Exception:
        return {}

    return snapshots


def _get_irq_heavy_cores(threshold: int = 100000) -> set[int]:
    """Return set of CPU cores that are the exclusive/dominant target of
    high-frequency device IRQs (e.g. i915 GPU).  These cores are unsafe
    for busy-spin RT work because hardware IRQs preempt even SCHED_FIFO."""
    heavy: set[int] = set()
    try:
        with open("/proc/interrupts", "r") as f:
            header = f.readline().split()
            num_cpus = len(header)
            for line in f:
                parts = line.split()
                if len(parts) < num_cpus + 2:
                    continue
                counts = []
                for i in range(1, num_cpus + 1):
                    try:
                        counts.append(int(parts[i]))
                    except (ValueError, IndexError):
                        counts.append(0)
                total = sum(counts)
                if total < threshold:
                    continue
                # Find if one core handles >80% of this IRQ
                for cpu_idx, cnt in enumerate(counts):
                    if cnt > total * 0.8:
                        heavy.add(cpu_idx)
    except Exception:
        pass
    return heavy


def _move_irqs_off_core(target_core: int, worker_name: str) -> None:
    """Best-effort: move high-frequency device IRQs off *target_core*
    so they cannot preempt the RT busy-spin loop."""
    num_cpus = len(os.sched_getaffinity(0)) or 6
    all_mask = (1 << num_cpus) - 1
    exclude_mask = all_mask & ~(1 << target_core)
    if exclude_mask == 0:
        return
    hex_mask = format(exclude_mask, "x")
    try:
        with open("/proc/interrupts", "r") as f:
            header = f.readline().split()
            ncols = len(header)
            for line in f:
                parts = line.split()
                if len(parts) < ncols + 2:
                    continue
                irq_num = parts[0].rstrip(":")
                if not irq_num.isdigit():
                    continue
                counts = []
                for i in range(1, ncols + 1):
                    try:
                        counts.append(int(parts[i]))
                    except (ValueError, IndexError):
                        counts.append(0)
                if counts[target_core] < 1000:
                    continue
                affinity_path = f"/proc/irq/{irq_num}/smp_affinity"
                try:
                    with open(affinity_path, "w") as af:
                        af.write(hex_mask)
                    LOG.info("[%s] Moved IRQ %s off CPU %s (mask=0x%s)",
                             worker_name, irq_num, target_core, hex_mask)
                except (PermissionError, OSError):
                    pass
    except Exception:
        pass


def _pick_least_busy_core(available_cores: list[int]) -> int:
    if not available_cores:
        return 0

    irq_heavy = _get_irq_heavy_cores()
    eligible = [core for core in available_cores if core != 0 and core not in irq_heavy]
    if not eligible:
        eligible = [core for core in available_cores if core != 0]
    if not eligible:
        eligible = list(available_cores)

    fallback_core = eligible[0]

    snap_a = _read_linux_cpu_times()
    if not snap_a:
        return fallback_core

    time.sleep(0.2)
    snap_b = _read_linux_cpu_times()
    if not snap_b:
        return fallback_core

    busy_by_core: list[tuple[float, int]] = []
    for core in eligible:
        if core not in snap_a or core not in snap_b:
            continue

        idle_a, total_a = snap_a[core]
        idle_b, total_b = snap_b[core]
        delta_total = total_b - total_a
        if delta_total <= 0:
            continue

        delta_idle = idle_b - idle_a
        busy_ratio = 1.0 - (delta_idle / delta_total)
        busy_by_core.append((busy_ratio, core))

    if not busy_by_core:
        return fallback_core

    busy_by_core.sort(key=lambda item: (item[0], item[1]))
    best_busy = busy_by_core[0][0]
    close_candidates = [
        core for busy, core in busy_by_core if busy <= (best_busy + 0.02)
    ]
    if not close_candidates:
        return busy_by_core[0][1]

    return close_candidates[0]


def setup_rt(worker_name: str, priority: int):
    _configure_sched_rt_runtime_us(worker_name)

    # Try to raise soft RT limit to hard limit so SCHED_FIFO can be set
    # automatically every run when system policy already allows it.
    try:
        soft_rtprio, hard_rtprio = resource.getrlimit(resource.RLIMIT_RTPRIO)
        desired_soft = soft_rtprio
        if hard_rtprio == resource.RLIM_INFINITY:
            desired_soft = max(soft_rtprio, int(priority))
        else:
            desired_soft = min(max(soft_rtprio, int(priority)), int(hard_rtprio))

        if desired_soft > soft_rtprio:
            resource.setrlimit(resource.RLIMIT_RTPRIO, (desired_soft, hard_rtprio))

        soft_rtprio, hard_rtprio = resource.getrlimit(resource.RLIMIT_RTPRIO)
        LOG.info(
            "[%s] RLIMIT_RTPRIO soft=%s hard=%s",
            worker_name,
            soft_rtprio,
            hard_rtprio,
        )
    except Exception as e:
        LOG.warning("[%s] Could not adjust RLIMIT_RTPRIO: %s", worker_name, e)

    # ---- Real-time scheduling ----
    try:
        param = os.sched_param(priority)
        os.sched_setscheduler(0, os.SCHED_FIFO, param)
        current_policy = os.sched_getscheduler(0)
        current_name = "SCHED_FIFO" if current_policy == os.SCHED_FIFO else str(current_policy)
        current_priority = os.sched_getparam(0).sched_priority
        LOG.info(
            "[%s] Scheduler active: %s (priority %s)",
            worker_name,
            current_name,
            current_priority,
        )
    except (PermissionError, OSError) as e:
        LOG.warning("[%s] Could not set SCHED_FIFO: %s", worker_name, e)
        try:
            soft_rtprio, hard_rtprio = resource.getrlimit(resource.RLIMIT_RTPRIO)
            LOG.warning(
                "[%s] RT limit insufficient (soft=%s hard=%s). "
                "One-time setup: add 'username - rtprio 99' in /etc/security/limits.d/, then re-login.",
                worker_name,
                soft_rtprio,
                hard_rtprio,
            )
        except Exception:
            pass
        try:
            os.nice(-20)
        except OSError:
            pass

    # ---- PM QoS: prevent deep C-states (keeps CPU awake) ----
    pm_qos_fd = None
    try:
        pm_qos_fd = os.open("/dev/cpu_dma_latency", os.O_WRONLY)
        os.write(pm_qos_fd, (0).to_bytes(4, byteorder="little"))  # 0 µs = no C-state
        LOG.info("[%s] PM QoS cpu_dma_latency=0 set", worker_name)
    except (OSError, PermissionError) as e:
        if pm_qos_fd is not None:
            try:
                os.close(pm_qos_fd)
            except OSError:
                pass
            pm_qos_fd = None
        LOG.warning(
            "[%s] Could not set PM QoS: %s. "
            "Run preflight setup once to grant access to /dev/cpu_dma_latency.",
            worker_name,
            e,
        )
    # NOTE: fd must stay open for the lifetime of the process

    # ---- CPU affinity ----
    try:
        available = sorted(os.sched_getaffinity(0))
        if not available:
            return

        target_core = _pick_least_busy_core(available)
        os.sched_setaffinity(0, {target_core})
        LOG.info(
            "[%s] pinned to CPU %s (cpus=%s, policy=least_busy, irq_heavy=%s)",
            worker_name,
            target_core,
            available,
            sorted(_get_irq_heavy_cores()),
        )
        _move_irqs_off_core(target_core, worker_name)
    except OSError:
        pass


# ────────────────────────────────────────────────────────────────
# Preflight – call from MAIN process before spawning workers
# ────────────────────────────────────────────────────────────────

def _can_write_rt_runtime() -> bool:
    """Return True if sched_rt_runtime_us already matches desired setting."""
    runtime_cfg = str(os.getenv("CAN_SEND_SCHED_RT_RUNTIME_US", "-1")).strip().lower()
    if runtime_cfg in ("", "keep", "default"):
        return True
    try:
        desired_runtime = int(runtime_cfg)
    except ValueError:
        return False

    path = "/proc/sys/kernel/sched_rt_runtime_us"
    try:
        with open(path, "r") as f:
            val = int(f.read().strip())
        return val == desired_runtime
    except (PermissionError, OSError, ValueError):
        return False


def _can_open_pm_qos() -> bool:
    """Return True if /dev/cpu_dma_latency is openable."""
    try:
        fd = os.open("/dev/cpu_dma_latency", os.O_WRONLY)
        os.close(fd)
        return True
    except (PermissionError, OSError):
        return False


def _can_set_sched_fifo() -> bool:
    """Return True if RLIMIT_RTPRIO allows SCHED_FIFO prio 90."""
    try:
        soft, _ = resource.getrlimit(resource.RLIMIT_RTPRIO)
        return soft >= 90
    except Exception:
        return False


def preflight_rt_check() -> None:
    """Test RT knobs and offer one-time setup if any are missing.

    Call this from the **main process** before spawning worker subprocesses.
        It checks three things:
            1. sched_rt_runtime_us already matches desired value
            2. /dev/cpu_dma_latency openable
            3. RLIMIT_RTPRIO >= 90

    If any fail, the user is prompted once to run the setup script.
    """
    rt_runtime_ok = _can_write_rt_runtime()
    pm_qos_ok = _can_open_pm_qos()
    rtprio_ok = _can_set_sched_fifo()

    if rt_runtime_ok and pm_qos_ok and rtprio_ok:
        print("[RT] All RT permissions OK")
        return

    # Report what's missing
    print("\n" + "=" * 60)
    print("[RT] Some real-time permissions are not configured:")
    if not rt_runtime_ok:
        print("  ✗  sched_rt_runtime_us   (causes ~50 ms stalls in poll mode)")
    if not pm_qos_ok:
        print("  ✗  cpu_dma_latency       (CPU may enter deep sleep, adding jitter)")
    if not rtprio_ok:
        print("  ✗  RLIMIT_RTPRIO < 90    (cannot use SCHED_FIFO real-time scheduling)")
    print("")
    print("  This is a ONE-TIME setup. After this, every run works automatically.")
    print("=" * 60)

    try:
        answer = input("[RT] Allow setup now? Your password will be asked once. [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n[RT] Skipped. Warnings may appear during run.")
        return

    if answer not in ("y", "yes"):
        print("[RT] Skipped. Warnings may appear during run.")
        return

    # Run the setup script with sudo
    username = getpass.getuser()
    script = str(_SETUP_SCRIPT)
    print(f"[RT] Running: sudo bash {script} {username}")
    try:
        result = subprocess.run(
            ["sudo", "bash", script, username],
            timeout=30,
        )
        if result.returncode == 0:
            print("[RT] Setup complete. RT permissions are now active.\n")
        else:
            print(f"[RT] Setup script exited with code {result.returncode}.\n")
    except subprocess.TimeoutExpired:
        print("[RT] Setup timed out.\n")
    except Exception as e:
        print(f"[RT] Setup failed: {e}\n")