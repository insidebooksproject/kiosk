#!/bin/sh
# ibp-kiosk: Debian's hook for package scripts (invoke-rc.d and
# deb-systemd-invoke ask it before they start, stop or restart a service).
# Allowed as usual, except once a shutdown has begun: the boot updater may
# be running apt then, the shutdown waits for it, and a package script
# waiting on a service job would wait on the shutdown itself. Exit 101 is
# "action forbidden"; the next boot starts everything anyway.
if [ "$(systemctl is-system-running 2>/dev/null)" = stopping ]; then
    exit 101
fi
exit 0
