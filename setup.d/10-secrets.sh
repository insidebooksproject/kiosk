# Sourced by setup.sh. Installs the base system's secrets from
# $KIOSK_SECRETS: the ibp admin's SSH keys, Wi-Fi profiles, the one-time
# Tailscale auth key and update.conf. The app secrets (shippy.ini, ...) are installed by the
# app steps. Every file is optional, and a rerun without a secrets directory
# leaves what is installed alone.

if [ -n "$KIOSK_SECRETS" ]; then
    if [ -f "$KIOSK_SECRETS/authorized_keys" ]; then
        if id ibp >/dev/null 2>&1; then
            install -d -m 700 -o ibp -g ibp /home/ibp/.ssh
            install -m 600 -o ibp -g ibp "$KIOSK_SECRETS/authorized_keys" \
                /home/ibp/.ssh/authorized_keys
        else
            echo "ibp-kiosk: WARNING: no ibp user; SSH keys not installed" >&2
        fi
    fi

    for f in "$KIOSK_SECRETS"/wifi/*.nmconnection; do
        [ -f "$f" ] || continue
        install -d -m 700 /etc/NetworkManager/system-connections
        install -m 600 "$f" "/etc/NetworkManager/system-connections/${f##*/}"
    done

    if [ -f "$KIOSK_SECRETS/tailscale-authkey" ]; then
        install -m 600 "$KIOSK_SECRETS/tailscale-authkey" /etc/ibp-kiosk/tailscale-authkey
    fi

    # Not a secret: which branch ibp-kiosk-update follows (or none).
    if [ -f "$KIOSK_SECRETS/update.conf" ]; then
        install -m 644 "$KIOSK_SECRETS/update.conf" /etc/ibp-kiosk/update.conf
    fi
fi
