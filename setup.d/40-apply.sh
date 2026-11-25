# Sourced by setup.sh. On a running system (a rerun over SSH, not the
# installer's chroot), apply the base system's changes now. The kiosk
# session itself is left alone: restart it with
#   sudo systemctl restart getty@tty1

if [ -n "$KIOSK_LIVE" ]; then
    systemctl daemon-reload
    systemctl reload ssh
    systemctl reload systemd-logind
    systemctl restart zramswap
    nmcli connection reload
    if [ -f /etc/ibp-kiosk/tailscale-authkey ]; then
        systemctl start --no-block ibp-kiosk-tailscale-up.service
    fi
fi
