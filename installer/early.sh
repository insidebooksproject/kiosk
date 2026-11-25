#!/bin/sh
# partman/early_command: install to the machine's one internal disk (NVMe,
# SATA or eMMC). USB disks, removable media (an SD card left in the slot)
# and virtual devices are skipped, which keeps the installer from wiping the
# stick itself; then it refuses to run unless exactly one disk is left, so it
# never has to guess which one to erase.
#
# Refusing means never returning. debian-installer treats a failed
# early_command as a dialog to click through, and then partitions whatever
# disk it finds without asking (the confirmations are preseeded). So on a
# refusal, or on any error in this script, it logs the reason and waits
# forever: the install stays at "partitioning", Alt+F4 shows the log, and the
# only way on is to power off.
set -e

refuse() {
    set +e
    logger -t ibp-kiosk "NOT INSTALLING: $1. Power off; nothing was erased."
    echo "IBP kiosk: not installing: $1" >&2
    trap - EXIT
    while :; do sleep 3600; done
}
trap 'refuse "early.sh failed unexpectedly"' EXIT

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
    refuse "need exactly one internal disk, found $count ($disks)"
fi
logger -t ibp-kiosk "installing to $disks"
debconf-set partman-auto/disk "$disks"
trap - EXIT
