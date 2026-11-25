# Sourced by setup.sh. Boot, services and the console for the base system.

update-grub
systemctl set-default multi-user.target
systemctl enable NetworkManager avahi-daemon ssh tailscaled zramswap \
    unattended-upgrades systemd-timesyncd ibp-kiosk-tailscale-up.service
