// IBP station with under 3 GiB of RAM (the 2 GB Chromebook).
// setup.d/50-apps.sh copies this to /etc/firefox-esr/ only on such a
// machine, and removes it from the others.

// One content process and no per-site process isolation (fission) keep
// Firefox well under 1 GB.
pref("fission.autostart", false, locked);
pref("dom.ipc.processCount", 1, locked);
pref("browser.sessionhistory.max_total_viewers", 0, locked);
pref("browser.tabs.unloadOnLowMemory", true, locked);
