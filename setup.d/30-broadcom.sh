# Sourced by setup.sh. Broadcom Wi-Fi, as in most Intel MacBooks. The newer
# chips use the kernel's brcmfmac with firmware-brcm80211 (packages/base.txt).
# The older ones need Broadcom's own "wl" driver, which is in non-free and is
# built here by DKMS, and again by each kernel upgrade (hence the headers
# metapackage). b43 is passed over: its firmware is fetched from a third-party
# site at install time. The Debian installer has no driver for these chips,
# so such a machine installs over Ethernet. If this step fails the install
# still finishes, without Wi-Fi.

ibp_broadcom_sta_needed() {
    [ -n "$KIOSK_SECRETS" ] && [ -f "$KIOSK_SECRETS/force-broadcom-sta" ] && return 0
    for ibp_dev in /sys/bus/pci/devices/*; do
        [ "$(cat "$ibp_dev/vendor" 2>/dev/null)" = 0x14e4 ] || continue
        case "$(cat "$ibp_dev/class")" in 0x0280*) ;; *) continue ;; esac
        case "$(cat "$ibp_dev/device")" in
            # brcmfmac: BCM4350, 4354, 4356, 43602, 4355, 4364 and later
            0x43a3|0x43df|0x43ec|0x43ba|0x43bb|0x43bc|0x43dc|0x4464|0x44*) ;;
            *) return 0 ;;
        esac
    done
    return 1
}

ibp_install_broadcom_sta() {
    cat >/etc/apt/sources.list.d/ibp-kiosk-non-free.sources <<'EOF'
# Written by ibp-kiosk setup.d/30-broadcom.sh, for broadcom-sta-dkms
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie trixie-updates
Components: non-free
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
    apt-get update &&
        apt-get install -y --no-install-recommends linux-headers-amd64 broadcom-sta-dkms ||
        return 1
    # In the installer the running kernel isn't the installed one, so build
    # for every installed kernel by name.
    for ibp_k in /lib/modules/*; do
        [ -e "$ibp_k/build" ] || continue
        dkms autoinstall -k "${ibp_k##*/}" || return 1
    done
}

if ibp_broadcom_sta_needed; then
    ibp_install_broadcom_sta ||
        echo "ibp-kiosk: WARNING: the Broadcom wl driver did not install; Wi-Fi won't work" >&2
fi
