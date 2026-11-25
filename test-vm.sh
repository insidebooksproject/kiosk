#!/usr/bin/env bash
# shellcheck disable=SC2054  # QEMU options are comma-separated on purpose
# Try a station in a QEMU VM: UEFI, the ISO as a USB stick, the target disk
# on NVMe (/dev/nvme0n1, like the Acer laptops), wired network.
#
#   ./test-vm.sh install [--mem 2G|4G] [--iso FILE]
#                 wipe the VM disk and boot the ISO (press Enter at the menu);
#                 QEMU exits when the installer reboots
#   ./test-vm.sh [--mem 2G|4G]
#                 boot the installed VM
#   ./test-vm.sh monitor 'COMMAND'
#                 send one command to the running VM's QEMU monitor, e.g.
#                 'sendkey ret', 'sendkey meta_l', 'screendump build/vm/s.ppm'
#
# --mem: 2G is the Chromebook, 4G (the default) a laptop. --iso defaults to
# the newest build/ibp-kiosk-*.iso. Set VM_DISK=virtio to use a virtio disk
# instead of NVMe (the installed system mounts root by UUID, so either works
# after the install). The display is a plain framebuffer (VM_VIDEO=VGA):
# with VM_VIDEO=virtio-vga, terminal windows show stale frames in the VM.
# Screen: VNC on localhost:5901. SSH: /usr/bin/ssh -p 2222 ibp@localhost
# Monitor by hand, without socat:
#   echo 'info status' | nc -U -q 1 build/vm/monitor.sock
set -euo pipefail

cd "$(dirname "$0")"
vm=build/vm
ovmf=/usr/share/OVMF
mkdir -p "$vm"

mode=boot mem=4G iso=""
while [ $# -gt 0 ]; do
    case "$1" in
        install) mode=install ;;
        monitor)
            [ $# -eq 2 ] || { echo "usage: $0 monitor 'COMMAND'" >&2; exit 2; }
            [ -S "$vm/monitor.sock" ] || { echo "no VM running" >&2; exit 1; }
            printf '%s\n' "$2" | nc -U -q 1 "$vm/monitor.sock" | tr -d '\r' |
                grep -v '^QEMU .* monitor\|^(qemu)' || true
            exit 0 ;;
        --mem) mem=${2:-}; shift ;;
        --iso) iso=${2:-}; shift ;;
        *) echo "unknown argument: $1 (see the top of $0)" >&2; exit 2 ;;
    esac
    shift
done
case "$mem" in
    2G|2g|2048) mem=2048 ;;
    4G|4g|4096) mem=4096 ;;
    *) echo "--mem is 2G or 4G" >&2; exit 2 ;;
esac

case "${VM_DISK:-nvme}" in
    nvme) disk=(-device nvme,drive=disk,serial=ibpkiosk,bootindex=1) ;;
    virtio) disk=(-device virtio-blk-pci,drive=disk,bootindex=1) ;;
    *) echo "VM_DISK is nvme or virtio" >&2; exit 2 ;;
esac
args=(-drive "if=none,id=disk,format=raw,file=$vm/disk.img" "${disk[@]}")
if [ "$mode" = install ]; then
    if [ -z "$iso" ]; then
        iso=$(find build -maxdepth 1 -name 'ibp-kiosk-*.iso' -printf '%T@ %p\n' |
            sort -rn | head -n1 | cut -d' ' -f2-)
    fi
    [ -f "$iso" ] || { echo "no ISO; run ./build.sh first (KIOSK_TEST=1 for a test ISO)" >&2; exit 1; }
    echo "installing $iso"
    rm -f "$vm/disk.img" "$vm/vars.fd"
    args+=(-drive "if=none,id=usb,format=raw,readonly=on,file=$iso"
           -device usb-storage,drive=usb,bootindex=0
           -no-reboot)
fi
[ -f "$vm/disk.img" ] || truncate -s 16G "$vm/disk.img"
[ -f "$vm/vars.fd" ] || cp "$ovmf/OVMF_VARS_4M.fd" "$vm/vars.fd"

exec qemu-system-x86_64 \
    -machine q35,accel=kvm -cpu host -smp 2 -m "$mem" \
    -drive "if=pflash,format=raw,readonly=on,file=$ovmf/OVMF_CODE_4M.fd" \
    -drive "if=pflash,format=raw,file=$vm/vars.fd" \
    -device qemu-xhci -device usb-kbd -device usb-tablet \
    -device "${VM_VIDEO:-VGA}" \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22 \
    -display none -vnc 127.0.0.1:1 \
    -monitor "unix:$vm/monitor.sock,server,nowait" \
    "${args[@]}"
