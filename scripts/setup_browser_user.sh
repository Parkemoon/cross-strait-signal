#!/usr/bin/env bash
# One-time server setup (idempotent) for running the scrapers' headful
# Chromium unprivileged and sandboxed — see scraper/utils/browser_user.py.
#
#   1. system user `cs-browser` (no login shell) that the browser and its
#      Xvfb run as, so a compromised renderer holds neither root nor the
#      pipeline's environment (API keys);
#   2. a shared Playwright Chromium in /opt/ms-playwright, because the
#      default install under /root/.cache is unreadable to that user;
#   3. an AppArmor profile allowing that binary to create user namespaces:
#      Ubuntu 24.04 blocks unprivileged userns (Chromium's sandbox) unless
#      the binary's profile grants `userns` — the same one-liner Ubuntu
#      ships for Google Chrome in /etc/apparmor.d/chrome.
#
# Re-run after upgrading the `playwright` package: step 2 installs the
# browser revision the new version expects (a no-op when it is present).
# Run as root from the repo root:  bash scripts/setup_browser_user.sh
set -euo pipefail

USER_NAME=cs-browser
BROWSERS=/opt/ms-playwright
PROFILE=/etc/apparmor.d/playwright-chromium
cd "$(dirname "$0")/.."

if ! id "$USER_NAME" >/dev/null 2>&1; then
    useradd --system --home-dir "/var/lib/$USER_NAME" --create-home \
            --shell /usr/sbin/nologin "$USER_NAME"
    echo "created user $USER_NAME"
fi

mkdir -p "$BROWSERS"
PLAYWRIGHT_BROWSERS_PATH="$BROWSERS" venv/bin/playwright install --no-shell chromium
chmod -R a+rX "$BROWSERS"

cat > "$PROFILE" <<'EOF'
# Written by scripts/setup_browser_user.sh. Allows everything and only
# grants user namespaces, which Chromium's sandbox needs on Ubuntu 24.04+.
abi <abi/4.0>,
include <tunables/global>

profile playwright-chromium /opt/ms-playwright/chromium-*/chrome-linux*/chrome flags=(unconfined) {
  userns,

  include if exists <local/playwright-chromium>
}
EOF
apparmor_parser -r "$PROFILE"
echo "browser user, $BROWSERS and AppArmor profile ready"
