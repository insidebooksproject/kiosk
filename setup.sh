#!/bin/sh
# Turn a minimal Debian 13 (trixie) install into an IBP station. The
# installer runs it (from installer/late.sh); it is safe to rerun over SSH
# after changing the files here:
#
#   sudo sh setup.sh [-p PROFILE] [SECRETS_DIR]
#
# PROFILE is a directory under profiles/; without -p it is the one this
# machine was installed with (KIOSK_PROFILE in /etc/ibp-kiosk/profile.conf).
# SECRETS_DIR holds what build.sh writes (authorized_keys, wifi/,
# tailscale-authkey, shippy.ini, ...); every file in it is optional.
#
# After the base system, it sources setup.d/*.sh in order with KIOSK_SRC,
# KIOSK_SECRETS, KIOSK_FEATURES and has_feature (CLAUDE.md), plus
# KIOSK_PROFILE and KIOSK_LIVE (1 when running on the live system rather
# than in the installer), and the functions shutting_down and
# live_systemctl. A step must not call exit, and must be safe to rerun.
set -eu

KIOSK_SRC=$(cd "$(dirname "$0")" && pwd)
KIOSK_PROFILE=""
while getopts p: opt; do
    case "$opt" in
        p) KIOSK_PROFILE=$OPTARG ;;
        *) echo "usage: setup.sh [-p PROFILE] [SECRETS_DIR]" >&2; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
KIOSK_SECRETS=${1:-}
if [ -n "$KIOSK_SECRETS" ]; then
    KIOSK_SECRETS=$(cd "$KIOSK_SECRETS" && pwd)
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "setup.sh: run it as root (sudo sh setup.sh)" >&2
    exit 1
fi
if [ -z "$KIOSK_PROFILE" ] && [ -f /etc/ibp-kiosk/profile.conf ]; then
    # shellcheck source=/dev/null
    KIOSK_PROFILE=$(. /etc/ibp-kiosk/profile.conf && echo "${KIOSK_PROFILE:-}")
fi
if [ -z "$KIOSK_PROFILE" ] || [ ! -f "$KIOSK_SRC/profiles/$KIOSK_PROFILE/profile.conf" ]; then
    echo "setup.sh: no profile '$KIOSK_PROFILE'; pass one with -p ($(cd "$KIOSK_SRC/profiles" && echo */ | tr -d /))" >&2
    exit 1
fi
KIOSK_FEATURES=""
# shellcheck source=/dev/null
. "$KIOSK_SRC/profiles/$KIOSK_PROFILE/profile.conf"

has_feature() {
    case " $KIOSK_FEATURES " in
        *" $1 "*) return 0 ;;
    esac
    return 1
}
# KIOSK_LIVE=1 on a running system (a rerun over SSH), empty in the
# installer's chroot, so steps know whether to restart services now.
KIOSK_LIVE=""
if [ -d /run/systemd/system ] &&
    [ "$(stat -c %d:%i /)" = "$(stat -c %d:%i /proc/1/root/.)" ]; then
    KIOSK_LIVE=1
fi
export KIOSK_SRC KIOSK_SECRETS KIOSK_PROFILE KIOSK_FEATURES KIOSK_LIVE

# shutting_down: true once a shutdown or restart has begun. The boot updater
# runs this script, and a shutdown waits for it (ibp-kiosk-update.service),
# so a step must never wait on systemd then: its job would queue behind the
# shutdown, which is waiting for the step, and neither would finish.
shutting_down() {
    [ "$(systemctl is-system-running 2>/dev/null)" = stopping ]
}

# live_systemctl ARGS...: systemctl for a step's changes to the running
# system. It queues the job and returns (--no-block; daemon-reload, which
# queues no job, still runs to the end), and does nothing once the system
# is shutting down: the next boot starts everything with the new files.
live_systemctl() {
    if shutting_down; then
        echo "ibp-kiosk: shutting down; skipped systemctl $*"
        return 0
    fi
    case " $* " in
        *" daemon-reload "*) ;;
        *) set -- --no-block "$@" ;;
    esac
    systemctl "$@" && return 0
    shutting_down || return 1
    echo "ibp-kiosk: shutting down; systemctl $* did not go through"
}
export DEBIAN_FRONTEND=noninteractive
umask 022
echo "ibp-kiosk: setting up profile $KIOSK_PROFILE (features: ${KIOSK_FEATURES:-none})"

# --- Packages ---------------------------------------------------------------
# The installer only comments out the install media's apt source after
# late_command has run, and apt-get update fails on it.
if [ -f /etc/apt/sources.list ]; then
    sed -i 's|^deb cdrom:|# deb cdrom:|' /etc/apt/sources.list
fi

# Tailscale's apt repo, for remote admin over the tailnet
if [ ! -f /etc/apt/sources.list.d/tailscale.list ]; then
    apt-get install -y --no-install-recommends ca-certificates curl
    curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
        -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list \
        -o /etc/apt/sources.list.d/tailscale.list
fi

# The union of packages/*.txt: one name per line, # comments
packages=$(cat "$KIOSK_SRC"/packages/*.txt | sed 's/#.*//' | tr -s ' \t' '\n' |
    grep -v '^$' | LC_ALL=C sort -u | tr '\n' ' ')
apt-get update
# shellcheck disable=SC2086
apt-get install -y --no-install-recommends $packages tailscale

# --- Files ------------------------------------------------------------------
# Laid out by absolute path. Modes are set here rather than copied, since
# build.sh stages everything owner-only: directories 0755, files 0644,
# usr/local/bin and usr/sbin/policy-rc.d 0755. A file that needs another mode
# or owner gets it in the setup.d step that owns it.
# --remove-destination: a script that is running (ibp-kiosk-update runs this
# on a live station) keeps its old file rather than have it change under it.
cp -r --remove-destination --no-preserve=mode,ownership "$KIOSK_SRC/rootfs/." /
(cd "$KIOSK_SRC/rootfs" && find . -mindepth 1 -type d) | while read -r d; do
    chmod 755 "/${d#./}"
done
(cd "$KIOSK_SRC/rootfs" && find . -type f) | while read -r f; do
    case "$f" in
        ./usr/local/bin/* | ./usr/sbin/policy-rc.d) chmod 755 "/${f#./}" ;;
        *) chmod 644 "/${f#./}" ;;
    esac
done

# The launcher (launcher/ibp_kiosk), run with the system python3
lib=/usr/local/lib/ibp-kiosk
rm -rf "$lib/ibp_kiosk"
if [ -d "$KIOSK_SRC/launcher/ibp_kiosk" ]; then
    install -d -m 755 "$lib"
    cp -r --no-preserve=mode,ownership "$KIOSK_SRC/launcher/ibp_kiosk" "$lib/"
    find "$lib/ibp_kiosk" \( -name __pycache__ -o -name '*.pyc' \) -prune -exec rm -rf {} +
    find "$lib/ibp_kiosk" -type d -exec chmod 755 {} +
    find "$lib/ibp_kiosk" -type f -exec chmod 644 {} +
else
    echo "ibp-kiosk: WARNING: no launcher/ibp_kiosk; the session will have no launcher" >&2
fi

# The station's profile
install -d -m 755 /etc/ibp-kiosk
install -m 644 "$KIOSK_SRC/profiles/$KIOSK_PROFILE/profile.conf" /etc/ibp-kiosk/profile.conf
install -m 644 "$KIOSK_SRC/profiles/$KIOSK_PROFILE/station.toml" /etc/ibp-kiosk/station.toml

# --- The kiosk user: no password, logged in automatically on tty1 ------------
# The getty@tty1 drop-in in rootfs logs it in; its login shell starts the
# session. When the session ends, the login ends and getty starts a new one:
# that restart is the watchdog.
if ! id kiosk >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash --comment "IBP kiosk" kiosk
fi
cat >/home/kiosk/.bash_profile <<'EOF'
# Written by ibp-kiosk setup.sh
if [ "$(tty)" = /dev/tty1 ]; then
    exec /usr/local/bin/ibp-kiosk-session
fi
EOF
chown root:root /home/kiosk/.bash_profile
chmod 644 /home/kiosk/.bash_profile

# --- Steps ------------------------------------------------------------------
for step in "$KIOSK_SRC"/setup.d/*.sh; do
    [ -f "$step" ] || continue
    echo "ibp-kiosk: ${step##*/}"
    # shellcheck source=/dev/null
    . "$step"
done

if [ -n "${KIOSK_LIVE:-}" ]; then
    echo "Done. To restart the session with the new settings: sudo systemctl restart getty@tty1"
fi
