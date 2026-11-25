# shellcheck shell=sh
# Sourced by setup.sh after 50-apps.sh. Feature package-printer: CUPS with
# the DYMO driver, and ibp-print-server (ibp-kiosk-print-server.service) on
# localhost:40121, run by the system user ibp-kiosk-print. The DYMO queue
# itself is created on site (docs/apps.md). Without the feature it disables
# the server and removes the udev rule (CUPS is left installed). Never calls
# exit; safe to rerun.

ibp_pp_user=ibp-kiosk-print
ibp_pp_rule=/etc/udev/rules.d/60-ibp-kiosk-package-printer.rules

if has_feature package-printer; then
    # pycups (the ibp-printing `linux` extra, which the print server needs
    # for the queue's label size) has no wheel on PyPI: uv builds it, which
    # needs a compiler and the CUPS and Python headers.
    ibp_apps_apt cups cups-client cups-filters printer-driver-dymo \
        build-essential python3-dev libcups2-dev

    if ! id "$ibp_pp_user" >/dev/null 2>&1; then
        useradd --system --user-group --create-home \
            --home-dir "/var/lib/$ibp_pp_user" --shell /usr/sbin/nologin \
            --comment "IBP label print server" "$ibp_pp_user"
    fi

    install -m 644 /usr/local/share/ibp-kiosk/udev/60-ibp-kiosk-package-printer.rules "$ibp_pp_rule"
    systemctl enable cups.service ibp-kiosk-print-server.service

    ibp_apps_preinstall "$ibp_pp_user" ibp-printing-server
else
    rm -f "$ibp_pp_rule"
    systemctl disable ibp-kiosk-print-server.service
fi

if [ -n "$KIOSK_LIVE" ]; then
    systemctl daemon-reload
    udevadm control --reload || true
    if has_feature package-printer; then
        systemctl restart cups.service
        systemctl restart --no-block ibp-kiosk-print-server.service
    else
        systemctl stop ibp-kiosk-print-server.service
    fi
fi
