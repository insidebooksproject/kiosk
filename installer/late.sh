#!/bin/sh
# preseed/late_command: copy the station files into the new system and run
# setup.sh there with the profile build.sh chose. Output lands in
# /var/log/installer/syslog on the installed machine.
set -e

dest=/target/root/ibp-kiosk-install
rm -rf "$dest"
# The copy holds the secrets: remove it even when setup.sh fails.
trap 'rm -rf "$dest"' EXIT
cp -r /kiosk "$dest"
profile=$(cat /kiosk/profile)
in-target sh /root/ibp-kiosk-install/setup.sh -p "$profile" \
    /root/ibp-kiosk-install/secrets
rm -rf "$dest"
