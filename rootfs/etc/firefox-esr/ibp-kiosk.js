// IBP station. Debian's firefox-esr reads every .js file in /etc/firefox-esr;
// these apply to both browser tiles (portal and requests). Policies (the
// extension, lockdown) are in /usr/share/firefox-esr/distribution/policies.json.
// Each tile's start page is in its own profile's user.js, written by
// ibp-kiosk-app. The 2 GB Chromebook also gets ibp-kiosk-low-memory.js
// (feature low-memory).

// The launcher's Home key ends Firefox with SIGTERM (SIGKILL if it is slow),
// and a power cut ends it with nothing. Either way, the next start just
// opens the tile's page: no "restore session" page, no safe-mode or refresh
// offer after several unclean exits, no crash reporter.
pref("browser.startup.page", 1, locked);
pref("browser.sessionstore.resume_from_crash", false, locked);
pref("browser.sessionstore.max_resumed_crashes", 0, locked);
pref("toolkit.startup.max_resumed_crashes", -1, locked);
pref("browser.crashReports.unsubmittedCheck.enabled", false, locked);
pref("browser.crashReports.unsubmittedCheck.autoSubmit2", false, locked);

// Nothing to ask on the way out or on the way in.
pref("browser.warnOnQuit", false, locked);
pref("browser.warnOnQuitShortcut", false, locked);
pref("browser.tabs.warnOnClose", false, locked);
pref("browser.aboutwelcome.enabled", false, locked);
pref("datareporting.policy.firstRunURL", "", locked);
pref("browser.shell.checkDefaultBrowser", false, locked);
