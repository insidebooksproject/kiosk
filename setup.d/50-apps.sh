# shellcheck shell=sh
# Sourced by setup.sh (after rootfs/ is copied). The apps' parts every
# station shares: Firefox's low-memory prefs on a machine with little RAM,
# and uv, which runs the IBP Python apps. Defines the ibp_apps_* helpers
# that 60-shipping.sh and 70-package-printer.sh use.
# Never calls exit; safe to rerun.

# uv is not packaged in Debian 13, so it is Astral's static build, pinned by
# version and checksum. To update it: bump the version and both checksums
# (from the release's uv-<target>.tar.gz.sha256 files), then rerun setup.sh.
IBP_APPS_UV_VERSION=0.12.9
IBP_APPS_UV_SHA256_X86_64=ec7a99cd05e0cd7f80243f135ce1361c76835cb0ee60055d14d20eba8eba1460
IBP_APPS_UV_SHA256_AARCH64=c36fe17937ff6bd16dc42fc13854b5465999fcab2efe0af559381e945e3c6001

ibp_apps_warn() {
    echo "ibp-kiosk: WARNING: $*" >&2
}

# Install Debian packages one app needs (kept next to the app's setup
# rather than in packages/apps.txt).
ibp_apps_apt() {
    apt-get install -y --no-install-recommends "$@" ||
        ibp_apps_warn "could not install $*"
}

# Install or update /usr/local/bin/uv and uvx to IBP_APPS_UV_VERSION.
ibp_apps_install_uv() {
    case $(uname -m) in
    x86_64)
        _uv_target=x86_64-unknown-linux-gnu
        _uv_sha=$IBP_APPS_UV_SHA256_X86_64 ;;
    aarch64)
        _uv_target=aarch64-unknown-linux-gnu
        _uv_sha=$IBP_APPS_UV_SHA256_AARCH64 ;;
    *)
        ibp_apps_warn "no uv build for $(uname -m); the shipping apps won't run"
        return 0 ;;
    esac
    if [ -x /usr/local/bin/uv ] &&
        [ "$(/usr/local/bin/uv --version 2>/dev/null | cut -d' ' -f2)" = "$IBP_APPS_UV_VERSION" ]; then
        return 0
    fi
    _uv_tmp=$(mktemp -d)
    _uv_url=https://github.com/astral-sh/uv/releases/download/$IBP_APPS_UV_VERSION/uv-$_uv_target.tar.gz
    if curl -fsSL --retry 3 -o "$_uv_tmp/uv.tar.gz" "$_uv_url" &&
        echo "$_uv_sha  $_uv_tmp/uv.tar.gz" | sha256sum -c --quiet - &&
        tar -xzf "$_uv_tmp/uv.tar.gz" -C "$_uv_tmp"; then
        install -m 755 -o root -g root "$_uv_tmp/uv-$_uv_target/uv" "$_uv_tmp/uv-$_uv_target/uvx" \
            /usr/local/bin/
        echo "ibp-kiosk: installed uv $IBP_APPS_UV_VERSION"
    else
        ibp_apps_warn "could not install uv $IBP_APPS_UV_VERSION from $_uv_url"
    fi
    rm -rf "$_uv_tmp"
}

# Install or upgrade an ibp-kiosk-tool TOOL as USER, so its first launch
# needs no network and doesn't wait. Failure only warns: the app installs
# itself on first launch instead.
ibp_apps_preinstall() {
    _pre_user=$1 _pre_tool=$2
    _pre_home=$(getent passwd "$_pre_user" | cut -d: -f6)
    if [ -z "$_pre_home" ] || [ ! -x /usr/local/bin/uv ]; then
        ibp_apps_warn "can't preinstall $_pre_tool for $_pre_user"
        return 0
    fi
    echo "ibp-kiosk: installing $_pre_tool for $_pre_user (can take minutes)"
    (cd / && runuser -u "$_pre_user" -- env -i HOME="$_pre_home" \
        PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
        /usr/local/bin/ibp-kiosk-tool --install-only "$_pre_tool") ||
        ibp_apps_warn "could not install $_pre_tool for $_pre_user; it will install on first use"
}

# --- Firefox -----------------------------------------------------------------
# Below 3 GiB of RAM (the 2 GB Chromebook), the low-memory prefs.
ibp_apps_mem_kb=$(awk '$1 == "MemTotal:" {print $2}' /proc/meminfo)
if [ "${ibp_apps_mem_kb:-0}" -gt 0 ] && [ "$ibp_apps_mem_kb" -lt 3145728 ]; then
    install -m 644 /usr/local/share/ibp-kiosk/firefox/ibp-kiosk-low-memory.js \
        /etc/firefox-esr/ibp-kiosk-low-memory.js
else
    rm -f /etc/firefox-esr/ibp-kiosk-low-memory.js
fi

# --- uv ----------------------------------------------------------------------
# uv fetches the apps' git sources with the git command.
ibp_apps_apt git
ibp_apps_install_uv
