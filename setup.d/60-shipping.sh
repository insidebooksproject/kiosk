# shellcheck shell=sh
# Sourced by setup.sh after 50-apps.sh. Shipping: the config of shippy and
# shippy-gui, the PM-2411-BT udev rule, the label watcher (kiosk user
# service), the log upload timer, and the apps preinstalled for kiosk. Never
# calls exit; safe to rerun.

# The one config of Ship Individual, Ship Bulk (shippy --config) and Ship
# Manual (shippy-gui, which reads config.ini in its working directory,
# writes it from its Settings dialog and keeps its shippy.log next to it, so
# the directory is kiosk's). ibp-kiosk-app has the same path, as
# $HOME/.config/shippy. The stamp lists the checksums of the secrets the
# file already holds, one per line.
ibp_ship_dir=/home/kiosk/.config/shippy
ibp_ship_conf=$ibp_ship_dir/config.ini
ibp_ship_stamp=/var/lib/ibp-kiosk/shippy.ini.sha256
# Before 2026-11-28 each app had its own: shippy's in /etc and shippy-gui's
# config.ini, with the checksum of the shippy-gui.ini secret it came from.
ibp_ship_old_cli=/etc/ibp-kiosk/shippy.ini
ibp_ship_old_gui=/home/kiosk/.config/shippy-gui/config.ini
ibp_ship_old_gui_stamp=/var/lib/ibp-kiosk/shippy-gui.ini.sha256
ibp_ship_rule=/etc/udev/rules.d/60-ibp-kiosk-label-printer.rules

# The PM-2411-BT needs no CUPS (ibp-printing drives it over USB).
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

install -d -m 700 -o kiosk -g kiosk /home/kiosk/.config "$ibp_ship_dir"
install -d -m 700 /var/lib/ibp-kiosk

# A station set up with the two old configs: start the new one from
# shippy-gui's, which has the volunteer's saved settings and the keys both
# apps need, else from shippy's. The old files stay where they are: nothing
# reads them now, but a rollback of `deploy` would, and either may hold a
# key the other lacks. The stamp gets the checksums of both old secrets, so
# a rerun with the same old secrets keeps the file.
if [ ! -f "$ibp_ship_conf" ]; then
    ibp_ship_from=
    if [ -f "$ibp_ship_old_gui" ]; then
        ibp_ship_from=$ibp_ship_old_gui
    elif [ -f "$ibp_ship_old_cli" ]; then
        ibp_ship_from=$ibp_ship_old_cli
    fi
    if [ -n "$ibp_ship_from" ]; then
        install -m 600 -o kiosk -g kiosk "$ibp_ship_from" "$ibp_ship_conf"
        : >"$ibp_ship_stamp"
        if [ -f "$ibp_ship_old_gui_stamp" ]; then
            cat "$ibp_ship_old_gui_stamp" >>"$ibp_ship_stamp"
        fi
        if [ -f "$ibp_ship_old_cli" ]; then
            sha256sum <"$ibp_ship_old_cli" | cut -d' ' -f1 >>"$ibp_ship_stamp"
        fi
        echo "ibp-kiosk: the shipping apps now share $ibp_ship_conf, copied from $ibp_ship_from; the old configs stay in place, unread"
    fi
fi

# The secret is shippy.ini. An old secrets directory's shippy-gui.ini (from
# when each app had its own) is used only when there is no shippy.ini.
ibp_ship_secret=
if [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/shippy.ini" ]; then
    ibp_ship_secret=$KIOSK_SECRETS/shippy.ini
    if [ -f "$KIOSK_SECRETS/shippy-gui.ini" ]; then
        ibp_apps_warn "ignoring shippy-gui.ini: shippy.ini is the one config of the shipping apps now"
    fi
elif [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/shippy-gui.ini" ]; then
    ibp_ship_secret=$KIOSK_SECRETS/shippy-gui.ini
    ibp_apps_warn "no shippy.ini; using the old shippy-gui.ini for all three shipping tiles (call it shippy.ini)"
fi

# Volunteers change the file from Ship Manual's Settings dialog (font
# size, ...), so a rerun replaces it only with a secret it doesn't already
# hold. The replaced file is kept as config.ini.bak-<date>.
if [ -n "$ibp_ship_secret" ]; then
    ibp_ship_sum=$(sha256sum <"$ibp_ship_secret" | cut -d' ' -f1)
    if [ -f "$ibp_ship_conf" ] && grep -qxF "$ibp_ship_sum" "$ibp_ship_stamp" 2>/dev/null; then
        echo "ibp-kiosk: keeping $ibp_ship_conf (the secret is unchanged)"
    else
        if [ -f "$ibp_ship_conf" ]; then
            cp -p "$ibp_ship_conf" "$ibp_ship_conf.bak-$(date +%Y%m%d-%H%M%S)"
        fi
        install -m 600 -o kiosk -g kiosk "$ibp_ship_secret" "$ibp_ship_conf"
        echo "$ibp_ship_sum" >"$ibp_ship_stamp"
    fi
fi
if [ -f "$ibp_ship_conf" ]; then
    chown kiosk:kiosk "$ibp_ship_conf"
    chmod 600 "$ibp_ship_conf"
else
    ibp_apps_warn "no shippy.ini; Ship Individual, Ship Bulk and Ship Manual won't start"
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
ibp_apps_preinstall kiosk ibp-printing

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
        live_systemctl --user -M kiosk@ restart ibp-kiosk-label-watcher.service || true
    fi
fi
