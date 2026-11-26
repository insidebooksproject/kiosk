#!/usr/bin/env bash
# Build build/ibp-kiosk-<hostname>.iso: the current Debian 13 netinst ISO with
# a boot entry that installs one IBP station unattended. The hostname is
# baked in, so build one ISO per machine.
#
# Settings come from the environment; anything required and unset is asked
# for. The ISO holds the Wi-Fi password, the app API keys and the admin
# password hash, so treat the USB stick as a secret and wipe it after use.
#   KIOSK_HOSTNAME                   the machine's name, e.g. ibp-laptop2
#   KIOSK_WIFI_SSID, KIOSK_WIFI_PSK  Wi-Fi to join (WPA2 personal); the
#                                    installer uses it too. Set the SSID to
#                                    "" for none (then installing needs an
#                                    Ethernet cable)
#   KIOSK_SITE_WIFI_SSID, KIOSK_SITE_WIFI_PSK
#                                    optional second Wi-Fi, saved as
#                                    ibp-site-wifi (IBP's network when
#                                    installing at home). Not asked for
#   KIOSK_ADMIN_PASSWORD             password for the "ibp" admin (sudo, console)
#   KIOSK_SSH_KEYS                   authorized_keys file for "ibp"
#                                    (default ~/.ssh/id_ed25519.pub)
#   KIOSK_TAILSCALE_AUTHKEY          optional one-time key; joins the tailnet on
#                                    first boot as KIOSK_HOSTNAME
#   KIOSK_UPDATE_BRANCH              optional: the branch the station updates
#                                    itself from at boot (default deploy;
#                                    empty turns updates off)
# The apps' settings (each asked for; an empty answer leaves it out):
#   KIOSK_SHIPPY_CONFIG              shippy's config.ini
#   KIOSK_SHIPPY_GUI_CONFIG          shippy-gui's config.ini
#   KIOSK_LOG_SHARE                  Samba share for the logs, //host/share
#   KIOSK_LOG_USER, KIOSK_LOG_PASSWORD
#
# KIOSK_TEST=1 builds a test ISO with no real secrets: admin password
# "testpw", no Wi-Fi, placeholder app configs and log share, hostname
# "test-station" unless set, no updates at boot
# unless KIOSK_UPDATE_BRANCH is set. SSH keys are used if
# found. Never put a test ISO on a real machine. KIOSK_TEST_BROADCOM_STA=1
# makes the install build the Broadcom "wl" Wi-Fi driver without the hardware.
set -euo pipefail

cd "$(dirname "$0")"
umask 077
for tool in curl gpg gpgv sha256sum xorriso cpio gzip openssl; do
    command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done

mirror=https://cdimage.debian.org/debian-cd/current/amd64/iso-cd
mkdir -p build
test_mode=${KIOSK_TEST:-}

# --- Settings -------------------------------------------------------------
ask() {  # ask VAR "prompt" [secret]: asks when VAR is unset or empty
    [ -n "${!1:-}" ] && return
    prompt "$@"
}
ask_optional() {  # ask_optional VAR "prompt" [secret]: asks only when unset
    [ -n "${!1+set}" ] && return
    prompt "$@"
}
prompt() {
    local var=$1 prompt=$2 secret=${3:-} value
    if [ -n "$secret" ]; then
        read -rsp "$prompt: " value; echo
    else
        read -rp "$prompt: " value
    fi
    printf -v "$var" '%s' "$value"
}
die() { echo "$*" >&2; exit 1; }
no_newlines() {  # no_newlines VALUE...: reject values that would break a file
    local v
    for v in "$@"; do
        case "$v" in *$'\n'*|*\\*) die "newlines and backslashes aren't supported in the settings" ;; esac
    done
}

if [ "$test_mode" = 1 ]; then
    : "${KIOSK_HOSTNAME:=test-station}"
    : "${KIOSK_ADMIN_PASSWORD:=testpw}"
    KIOSK_WIFI_SSID=${KIOSK_WIFI_SSID:-}
    KIOSK_TAILSCALE_AUTHKEY=""
fi

ask KIOSK_HOSTNAME "Hostname"
[[ $KIOSK_HOSTNAME =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] ||
    die "bad hostname: $KIOSK_HOSTNAME (lowercase letters, digits and dashes)"

ask_optional KIOSK_WIFI_SSID "Wi-Fi network name (empty for none)"
if [ -n "$KIOSK_WIFI_SSID" ]; then
    ask KIOSK_WIFI_PSK "Wi-Fi password" secret
    if [ ${#KIOSK_WIFI_PSK} -lt 8 ] || [ ${#KIOSK_WIFI_PSK} -gt 63 ]; then
        die "a WPA2 password is 8 to 63 characters"
    fi
    no_newlines "$KIOSK_WIFI_SSID" "$KIOSK_WIFI_PSK"
fi
KIOSK_SITE_WIFI_SSID=${KIOSK_SITE_WIFI_SSID:-}
KIOSK_SITE_WIFI_PSK=${KIOSK_SITE_WIFI_PSK:-}
if [ -n "$KIOSK_SITE_WIFI_SSID" ]; then
    if [ ${#KIOSK_SITE_WIFI_PSK} -lt 8 ] || [ ${#KIOSK_SITE_WIFI_PSK} -gt 63 ]; then
        die "a WPA2 password is 8 to 63 characters (KIOSK_SITE_WIFI_PSK)"
    fi
    no_newlines "$KIOSK_SITE_WIFI_SSID" "$KIOSK_SITE_WIFI_PSK"
fi

if [ -z "${KIOSK_ADMIN_PASSWORD:-}" ]; then
    prompt KIOSK_ADMIN_PASSWORD "Password for the ibp admin user" secret
    confirm=""
    prompt confirm "Again" secret
    [ "$KIOSK_ADMIN_PASSWORD" = "$confirm" ] || die "passwords differ"
    [ -n "$KIOSK_ADMIN_PASSWORD" ] || die "the admin password can't be empty"
fi

KIOSK_SSH_KEYS=${KIOSK_SSH_KEYS:-$HOME/.ssh/id_ed25519.pub}
if [ ! -s "$KIOSK_SSH_KEYS" ]; then
    [ "$test_mode" = 1 ] || die "no SSH keys at $KIOSK_SSH_KEYS"
    echo "warning: no SSH keys at $KIOSK_SSH_KEYS; SSH to the test VM won't work" >&2
    KIOSK_SSH_KEYS=""
fi
KIOSK_TAILSCALE_AUTHKEY=${KIOSK_TAILSCALE_AUTHKEY:-}
no_newlines "$KIOSK_TAILSCALE_AUTHKEY"

if [ "$test_mode" != 1 ]; then
    for var in KIOSK_SHIPPY_CONFIG KIOSK_SHIPPY_GUI_CONFIG; do
        ask_optional "$var" "$var: path to the config.ini (empty to leave it out)"
        [ -z "${!var}" ] || [ -s "${!var}" ] || die "no file at ${!var}"
    done
    ask_optional KIOSK_LOG_SHARE "Samba share for the logs, //host/share (empty for none)"
    if [ -n "$KIOSK_LOG_SHARE" ]; then
        [[ $KIOSK_LOG_SHARE == //?*/?* ]] || die "the log share looks like //host/share"
        ask KIOSK_LOG_USER "Samba user for $KIOSK_LOG_SHARE"
        ask KIOSK_LOG_PASSWORD "Samba password for $KIOSK_LOG_USER" secret
        no_newlines "$KIOSK_LOG_SHARE" "$KIOSK_LOG_USER" "$KIOSK_LOG_PASSWORD"
    fi
fi

# --- Debian netinst ISO, checked against Debian's signed SHA256SUMS --------
curl -fsSL -o build/SHA256SUMS "$mirror/SHA256SUMS"
curl -fsSL -o build/SHA256SUMS.sign "$mirror/SHA256SUMS.sign"
gpg --dearmor <keys/debian-cd-signing-key.asc >build/debian-cd.gpg
gpgv --keyring "$PWD/build/debian-cd.gpg" build/SHA256SUMS.sign build/SHA256SUMS
iso=$(awk '$2 ~ /^debian-[0-9.]+-amd64-netinst\.iso$/ {print $2}' build/SHA256SUMS)
[ -n "$iso" ] || die "no netinst ISO in SHA256SUMS"
if ! (cd build && [ -f "$iso" ] && grep " $iso\$" SHA256SUMS | sha256sum --quiet -c 2>/dev/null); then
    echo "downloading $iso"
    curl -fL -o "build/$iso" "$mirror/$iso"
    (cd build && grep " $iso\$" SHA256SUMS | sha256sum --quiet -c)
fi

# --- Installer payload: preseed.cfg plus /kiosk, as an extra initrd --------
payload=build/payload
out=build/ibp-kiosk-$KIOSK_HOSTNAME.iso
rm -rf "$payload"
mkdir -p "$payload/kiosk/secrets"
trap 'rm -rf "$payload" build/payload.cpio.gz build/grub.cfg' EXIT

if [ -n "$KIOSK_WIFI_SSID" ]; then
    wifi="d-i netcfg/wireless_show_essids select manual
d-i netcfg/wireless_essid string $KIOSK_WIFI_SSID
d-i netcfg/wireless_essid_again string $KIOSK_WIFI_SSID
d-i netcfg/wireless_security_type select wpa
d-i netcfg/wireless_wpa string $KIOSK_WIFI_PSK"
else
    wifi="# No Wi-Fi in this build: installing needs an Ethernet cable."
fi
hash=$(printf '%s' "$KIOSK_ADMIN_PASSWORD" | openssl passwd -6 -stdin)
preseed=$(<installer/preseed.cfg)
preseed=${preseed//@HOSTNAME@/"$KIOSK_HOSTNAME"}
preseed=${preseed//@WIFI@/"$wifi"}
preseed=${preseed//@ADMIN_PASSWORD_HASH@/"$hash"}
printf '%s\n' "$preseed" >"$payload/preseed.cfg"

menu=$(<installer/grub.cfg)
menu=${menu//@HOSTNAME@/"$KIOSK_HOSTNAME"}
printf '%s\n' "$menu" >build/grub.cfg

# The repo's files, as setup.sh expects them (KIOSK_SRC on the target)
for f in setup.sh installer packages setup.d rootfs launcher; do
    if [ -e "$f" ]; then cp -r "$f" "$payload/kiosk/"; fi
done
find "$payload/kiosk" \( -name __pycache__ -o -name '*.pyc' \) -prune -exec rm -rf {} +

# Secrets, every one optional (names per CLAUDE.md)
secrets=$payload/kiosk/secrets
[ -z "$KIOSK_SSH_KEYS" ] || cp "$KIOSK_SSH_KEYS" "$secrets/authorized_keys"
nmconnection() {  # nmconnection ID SSID PSK
    mkdir -p "$secrets/wifi"
    cat >"$secrets/wifi/$1.nmconnection" <<EOF
[connection]
id=$1
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=$2

[wifi-security]
key-mgmt=wpa-psk
psk=$3

[ipv4]
method=auto

[ipv6]
method=auto
EOF
}
[ -z "$KIOSK_WIFI_SSID" ] || nmconnection ibp-wifi "$KIOSK_WIFI_SSID" "$KIOSK_WIFI_PSK"
[ -z "$KIOSK_SITE_WIFI_SSID" ] ||
    nmconnection ibp-site-wifi "$KIOSK_SITE_WIFI_SSID" "$KIOSK_SITE_WIFI_PSK"
# VM tests: build the Broadcom wl driver without the hardware (setup.d/30)
[ "${KIOSK_TEST_BROADCOM_STA:-}" != 1 ] || : >"$secrets/force-broadcom-sta"
[ -z "$KIOSK_TAILSCALE_AUTHKEY" ] ||
    printf '%s\n' "$KIOSK_TAILSCALE_AUTHKEY" >"$secrets/tailscale-authkey"
# Which branch the station updates itself from at boot (ibp-kiosk-update).
# Without update.conf it follows `deploy`; a test ISO follows nothing unless
# told to, so a VM keeps the code it was built from.
if [ -n "${KIOSK_UPDATE_BRANCH+set}" ]; then
    printf 'UPDATE_BRANCH=%s\n' "$KIOSK_UPDATE_BRANCH" >"$secrets/update.conf"
elif [ "$test_mode" = 1 ]; then
    printf 'UPDATE_BRANCH=\n' >"$secrets/update.conf"
fi

if [ "$test_mode" = 1 ]; then
    for name in shippy shippy-gui; do
        cat >"$secrets/$name.ini" <<'EOF'
# Placeholder written by build.sh KIOSK_TEST=1: no real keys.
[ibp]
url = http://ibp-server.invalid
apikey = test

[easypost]
apikey = test

[googlemaps]
apikey = AIzaTESTTESTTESTTESTTESTTESTTESTTESTTES
EOF
    done
    printf 'SHARE=//ibp-server.invalid/ibp-logs-test\nUSERNAME=test\nPASSWORD=test\n' \
        >"$secrets/log-upload.conf"
else
    [ -z "${KIOSK_SHIPPY_CONFIG:-}" ] || cp "$KIOSK_SHIPPY_CONFIG" "$secrets/shippy.ini"
    [ -z "${KIOSK_SHIPPY_GUI_CONFIG:-}" ] || cp "$KIOSK_SHIPPY_GUI_CONFIG" "$secrets/shippy-gui.ini"
    if [ -n "${KIOSK_LOG_SHARE:-}" ]; then
        printf 'SHARE=%s\nUSERNAME=%s\nPASSWORD=%s\n' \
            "$KIOSK_LOG_SHARE" "$KIOSK_LOG_USER" "$KIOSK_LOG_PASSWORD" \
            >"$secrets/log-upload.conf"
    fi
fi

(cd "$payload" && find . -mindepth 1 | LC_ALL=C sort |
    cpio --quiet -o -H newc -R 0:0) | gzip -9 >build/payload.cpio.gz

# --- Remaster: add the payload and our boot menu, keep Debian's boot setup --
rm -f "$out"
xorriso -indev "build/$iso" -outdev "$out" \
    -map build/payload.cpio.gz /kiosk/payload.cpio.gz \
    -map build/grub.cfg /boot/grub/grub.cfg \
    -boot_image any replay 2>build/xorriso.log ||
    { cat build/xorriso.log >&2; exit 1; }

echo
echo "Built $out from $iso"
echo "  hostname $KIOSK_HOSTNAME, Wi-Fi ${KIOSK_WIFI_SSID:-none}${test_mode:+ (TEST build)}"
echo "  secrets: $(cd "$secrets" && find . -type f | sed 's|^\./||' | LC_ALL=C sort | paste -sd' ')"
echo "Write it to the USB stick (replace sdX; this erases the stick):"
echo "  sudo dd if=$out of=/dev/sdX bs=4M conv=fsync status=progress"
