# shellcheck shell=sh
# Sourced by setup.sh after 50-apps.sh. Feature shipping: shippy and
# shippy-gui configs, the PM-2411-BT udev rule, the label watcher (kiosk user
# service), the log upload timer, and the apps preinstalled for kiosk.
# Without the feature it removes the rule and disables the services (configs
# and installed apps are left alone). Never calls exit; safe to rerun.

ibp_ship_gui_dir=/home/kiosk/.config/shippy-gui
ibp_ship_gui_stamp=/var/lib/ibp-kiosk/shippy-gui.ini.sha256
ibp_ship_rule=/etc/udev/rules.d/60-ibp-kiosk-label-printer.rules

if has_feature shipping && ! id kiosk >/dev/null 2>&1; then
    ibp_apps_warn "no kiosk user; skipping the shipping setup"
elif has_feature shipping; then
    # The direct-USB printer path needs no CUPS (ibp-printing dropped it).
    # cifs-utils mounts the log share. The rest are the system libraries
    # the PyPI PySide6 wheels in shippy-gui load.
    ibp_apps_apt cifs-utils \
        libegl1 libgl1 libfontconfig1 libfreetype6 libdbus-1-3 libglib2.0-0t64 \
        libxkbcommon0 libxkbcommon-x11-0 \
        libwayland-client0 libwayland-cursor0 libwayland-egl1 \
        libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 libxcb-glx0 libxcb-icccm4 \
        libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render0 \
        libxcb-render-util0 libxcb-shape0 libxcb-shm0 libxcb-sync1 libxcb-util1 \
        libxcb-xfixes0 libxcb-xkb1

    # shippy.ini: /etc/ibp-kiosk/shippy.ini, readable by kiosk only.
    if [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/shippy.ini" ]; then
        install -m 640 -o root -g kiosk "$KIOSK_SECRETS/shippy.ini" /etc/ibp-kiosk/shippy.ini
    elif [ -f /etc/ibp-kiosk/shippy.ini ]; then
        chown root:kiosk /etc/ibp-kiosk/shippy.ini
        chmod 640 /etc/ibp-kiosk/shippy.ini
    else
        ibp_apps_warn "no shippy.ini; Ship Individual and Ship Bulk won't start"
    fi

    # shippy-gui's config.ini: volunteers change it from its Settings dialog
    # (font size, ...), so a rerun replaces it only when a different secret
    # is supplied than the one installed last (its checksum is kept in
    # /var/lib/ibp-kiosk). The replaced file is kept as config.ini.bak-<date>.
    install -d -m 700 -o kiosk -g kiosk /home/kiosk/.config "$ibp_ship_gui_dir"
    if [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/shippy-gui.ini" ]; then
        ibp_ship_sum=$(sha256sum <"$KIOSK_SECRETS/shippy-gui.ini" | cut -d' ' -f1)
        if [ ! -f "$ibp_ship_gui_dir/config.ini" ] ||
            [ "$(cat "$ibp_ship_gui_stamp" 2>/dev/null)" != "$ibp_ship_sum" ]; then
            if [ -f "$ibp_ship_gui_dir/config.ini" ]; then
                cp -p "$ibp_ship_gui_dir/config.ini" \
                    "$ibp_ship_gui_dir/config.ini.bak-$(date +%Y%m%d-%H%M%S)"
            fi
            install -m 600 -o kiosk -g kiosk "$KIOSK_SECRETS/shippy-gui.ini" \
                "$ibp_ship_gui_dir/config.ini"
            install -d -m 700 /var/lib/ibp-kiosk
            echo "$ibp_ship_sum" >"$ibp_ship_gui_stamp"
        else
            echo "ibp-kiosk: keeping shippy-gui's config.ini (the secret is unchanged)"
        fi
    elif [ -f "$ibp_ship_gui_dir/config.ini" ]; then
        chown kiosk:kiosk "$ibp_ship_gui_dir/config.ini"
        chmod 600 "$ibp_ship_gui_dir/config.ini"
    else
        ibp_apps_warn "no shippy-gui.ini; Ship Manual won't start"
    fi

    # The PM-2411-BT: group kiosk on its usblp node, no USB autosuspend.
    install -m 644 /usr/local/share/ibp-kiosk/udev/60-ibp-kiosk-label-printer.rules "$ibp_ship_rule"

    # The label watcher, for the kiosk user only (ConditionUser=kiosk).
    systemctl --global enable ibp-kiosk-label-watcher.service

    # Log upload, only with a share to upload to.
    if [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/log-upload.conf" ]; then
        install -m 600 -o root -g root "$KIOSK_SECRETS/log-upload.conf" /etc/ibp-kiosk/log-upload.conf
    fi
    if [ -f /etc/ibp-kiosk/log-upload.conf ]; then
        chown root:root /etc/ibp-kiosk/log-upload.conf
        chmod 600 /etc/ibp-kiosk/log-upload.conf
        systemctl enable ibp-kiosk-log-upload.timer
    else
        ibp_apps_warn "no log-upload.conf; the label-printer logs stay on this machine"
        systemctl disable ibp-kiosk-log-upload.timer
    fi

    # The apps themselves, so the first launch needn't download them.
    ibp_apps_preinstall kiosk shippy
    ibp_apps_preinstall kiosk shippy-gui
    ibp_apps_preinstall kiosk ibp-printing
else
    rm -f "$ibp_ship_rule"
    systemctl --global disable ibp-kiosk-label-watcher.service
    systemctl disable ibp-kiosk-log-upload.timer
fi

if [ -n "$KIOSK_LIVE" ]; then
    live_systemctl daemon-reload
    udevadm control --reload || true
    udevadm trigger --subsystem-match=usbmisc --subsystem-match=usb || true
    if systemctl is-enabled --quiet ibp-kiosk-log-upload.timer; then
        live_systemctl restart ibp-kiosk-log-upload.timer
    else
        live_systemctl stop ibp-kiosk-log-upload.timer
    fi
    # The watcher runs in kiosk's user manager, if kiosk is logged in.
    if ! shutting_down && systemctl --user -M kiosk@ daemon-reload 2>/dev/null; then
        if has_feature shipping; then
            live_systemctl --user -M kiosk@ restart ibp-kiosk-label-watcher.service || true
        else
            live_systemctl --user -M kiosk@ stop ibp-kiosk-label-watcher.service || true
        fi
    fi
fi
