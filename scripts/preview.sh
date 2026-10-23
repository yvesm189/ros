#!/usr/bin/env bash
# Boot a ROS ISO in QEMU to look at it.
#
#   ./scripts/preview.sh                  # newest ISO in out/
#   ./scripts/preview.sh out/ros-0.1.0-arm64.iso
#
# On Apple silicon an arm64 image boots with hardware acceleration and is
# usable; an amd64 image runs fully emulated and is slow but does boot.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISO="${1:-$(ls -t "${ROOT}"/out/*.iso 2>/dev/null | head -1 || true)}"
MEMORY="${MEMORY:-4096}"
CPUS="${CPUS:-2}"

if [ -z "${ISO}" ] || [ ! -f "${ISO}" ]; then
    echo "error: no ISO found. Run ./scripts/build-iso.sh first." >&2
    exit 1
fi

case "${ISO}" in
    *arm64*) GUEST_ARCH="arm64" ;;
    *)       GUEST_ARCH="amd64" ;;
esac

HOST_ARCH="$(uname -m)"
QEMU="qemu-system-x86_64"
[ "${GUEST_ARCH}" = "arm64" ] && QEMU="qemu-system-aarch64"

if ! command -v "${QEMU}" >/dev/null 2>&1; then
    cat >&2 <<MSG
error: ${QEMU} is not installed.

  macOS:  brew install qemu
  Debian: sudo apt install qemu-system-x86 qemu-system-arm ovmf

Alternatively open ${ISO} with UTM, VirtualBox or VMware - the ISO is an
ordinary Debian live image and boots in any of them.
MSG
    exit 1
fi

ARGS=(-m "${MEMORY}" -smp "${CPUS}" -cdrom "${ISO}" -boot d
      -device virtio-net-pci,netdev=net0 -netdev user,id=net0)

if [ "${GUEST_ARCH}" = "arm64" ]; then
    FIRMWARE="$(ls /opt/homebrew/share/qemu/edk2-aarch64-code.fd \
                   /usr/local/share/qemu/edk2-aarch64-code.fd \
                   /usr/share/AAVMF/AAVMF_CODE.fd 2>/dev/null | head -1 || true)"
    [ -n "${FIRMWARE}" ] || { echo "error: no aarch64 UEFI firmware found" >&2; exit 1; }
    ARGS+=(-machine virt -bios "${FIRMWARE}" -device virtio-gpu-pci -device qemu-xhci
           -device usb-kbd -device usb-tablet)
    case "${HOST_ARCH}" in
        arm64|aarch64) ARGS+=(-accel hvf -cpu host) ;;
        *)             ARGS+=(-cpu max) ;;
    esac
else
    ARGS+=(-vga virtio)
    case "${HOST_ARCH}" in
        x86_64) ARGS+=(-accel hvf -cpu host) ;;
        *)      echo ">> note: emulating x86 on ${HOST_ARCH}; expect a slow boot" ;;
    esac
fi

echo ">> booting $(basename "${ISO}") with ${QEMU}"
exec "${QEMU}" "${ARGS[@]}"
