#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# CAN Analyzer – one-time Linux RT permission setup
# Run via:  sudo bash setup_rt_linux.sh <username>
# ────────────────────────────────────────────────────────────────
set -euo pipefail

TARGET_USER="${1:?Usage: sudo bash setup_rt_linux.sh <username>}"

echo "=== CAN Analyzer RT Setup for user: ${TARGET_USER} ==="

# ── 1. Passwordless sudo rules for RT knobs ──────────────────
SUDOERS_FILE="/etc/sudoers.d/can-analyzer-rt"
echo "[1/4] Writing ${SUDOERS_FILE} ..."
cat > "${SUDOERS_FILE}" <<EOF
# CAN Analyzer – allow RT tuning without password
${TARGET_USER} ALL=(root) NOPASSWD: /usr/bin/tee /proc/sys/kernel/sched_rt_runtime_us
${TARGET_USER} ALL=(root) NOPASSWD: /usr/bin/chmod a+rw /dev/cpu_dma_latency
EOF
chmod 440 "${SUDOERS_FILE}"
# Validate syntax (reverts if broken)
if ! visudo -cf "${SUDOERS_FILE}" >/dev/null 2>&1; then
    rm -f "${SUDOERS_FILE}"
    echo "ERROR: sudoers syntax check failed – removed ${SUDOERS_FILE}"
    exit 1
fi
echo "    OK: ${SUDOERS_FILE}"

# ── 2. RTPRIO limits ─────────────────────────────────────────
LIMITS_FILE="/etc/security/limits.d/99-can-analyzer-rt.conf"
echo "[2/4] Writing ${LIMITS_FILE} ..."
cat > "${LIMITS_FILE}" <<EOF
# CAN Analyzer – allow SCHED_FIFO up to priority 99
${TARGET_USER}  -  rtprio  99
${TARGET_USER}  -  memlock unlimited
EOF
echo "    OK: ${LIMITS_FILE}"

# ── 3. Apply sched_rt_runtime_us = -1 right now ──────────────
echo "[3/4] Setting sched_rt_runtime_us = -1 ..."
echo -1 > /proc/sys/kernel/sched_rt_runtime_us
echo "    OK: $(cat /proc/sys/kernel/sched_rt_runtime_us)"

# ── 4. Open /dev/cpu_dma_latency for current session ─────────
echo "[4/4] chmod a+rw /dev/cpu_dma_latency ..."
chmod a+rw /dev/cpu_dma_latency 2>/dev/null || true
echo "    OK"

echo ""
echo "=== Setup complete. No reboot needed for sudo rules. ==="
echo "=== Log out and back in (or reboot) for rtprio limits to take effect. ==="
