#!/bin/sh
# partman/early_command: install to the machine's one internal disk (NVMe,
# SATA or eMMC). USB disks, removable media (an SD card left in the slot)
# and virtual devices are skipped, which keeps the installer from wiping the
# stick itself; then it refuses to run unless exactly one disk is left, so it
# never has to guess which one to erase.
set -e

disks=""
count=0
for dev in $(list-devices disk); do
    name=${dev#/dev/}
    case "$name" in
        mmcblk*boot*|mmcblk*rpmb) continue ;;  # eMMC hardware partitions
        loop*|ram*|zram*|sr*|fd*|md*|dm-*|nbd*) continue ;;
    esac
    case "$(readlink -f "/sys/block/$name")" in
        */usb[0-9]*/*) continue ;;
    esac
    [ "$(cat "/sys/block/$name/removable" 2>/dev/null)" = 1 ] && continue
    disks="$disks $dev"
    count=$((count + 1))
done
disks=${disks# }

if [ "$count" -ne 1 ]; then
    logger -t ibp-kiosk "need exactly one internal disk, found $count ($disks); refusing to partition"
    echo "IBP kiosk: need exactly one internal disk, found $count ($disks); not installing." >&2
    exit 1
fi
logger -t ibp-kiosk "installing to $disks"
debconf-set partman-auto/disk "$disks"
