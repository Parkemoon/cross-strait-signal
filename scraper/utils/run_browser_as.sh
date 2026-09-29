#!/bin/sh
# Playwright's Chromium "executable" when a scraper runs as root (see
# browser_user.py). Gives Playwright's temporary profile directory to
# $BROWSER_USER, then execs the real browser ($BROWSER_BIN) as that user.
# setpriv replaces this process rather than forking, so the browser keeps
# the pipe file descriptors Playwright drives it through.
set -eu
user=$BROWSER_USER
bin=$BROWSER_BIN
unset BROWSER_USER BROWSER_BIN
for arg in "$@"; do
    case $arg in
        --user-data-dir=*) chown -R "$user:" "${arg#--user-data-dir=}" ;;
    esac
done
exec setpriv --reuid="$user" --regid="$user" --init-groups -- "$bin" "$@"
