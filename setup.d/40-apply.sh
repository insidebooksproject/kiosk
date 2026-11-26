# Sourced by setup.sh. On a running system (a rerun over SSH, not the
# installer's chroot), apply the base system's changes now. The kiosk
# session itself is left alone: restart it with
#   sudo systemctl restart getty@tty1

if [ -n "$KIOSK_LIVE" ]; then
    live_systemctl daemon-reload
    live_systemctl reload ssh
    live_systemctl reload systemd-logind
    live_systemctl restart zramswap
    nmcli connection reload || shutting_down
    if [ -f /etc/ibp-kiosk/tailscale-authkey ]; then
        live_systemctl start ibp-kiosk-tailscale-up.service
    fi
fi
