"""Launch scraper browsers unprivileged and sandboxed.

The pipeline runs as root (cron) and Chromium refuses its sandbox as
root, so a browser it launches directly renders third-party pages
unsandboxed, as root, with the pipeline's whole environment (the Gemini
key and admin token are loaded from .env). `launch_chromium()` instead
starts the browser as BROWSER_USER through run_browser_as.sh, with its
sandbox on and an environment of DISPLAY, HOME and PATH only. Playwright
still drives it over its private pipe, so the Python side (database,
keys) stays in the root process.

Server prerequisites (the user, a Chromium under /opt it can read, the
AppArmor profile that lets the sandbox create user namespaces):
scripts/setup_browser_user.sh. Run as a normal user, e.g. on a desktop,
the browser is launched directly, sandboxed as usual.
"""
import os
from pathlib import Path

BROWSER_USER = 'cs-browser'
SHARED_BROWSERS = Path('/opt/ms-playwright')
_WRAPPER = Path(__file__).with_name('run_browser_as.sh')
_SETUP_HINT = 'run scripts/setup_browser_user.sh as root'


def browser_user():
    """BROWSER_USER when this process is root and must hand the browser
    over, else None."""
    if not hasattr(os, 'geteuid') or os.geteuid() != 0:
        return None
    import pwd
    try:
        pwd.getpwnam(BROWSER_USER)
    except KeyError:
        raise RuntimeError(f'no {BROWSER_USER} user: {_SETUP_HINT}') from None
    return BROWSER_USER


def shared_binary(executable_path):
    """The /opt copy of the Chromium Playwright expects: its default
    install path with everything before `chromium-<rev>/` swapped for
    SHARED_BROWSERS."""
    parts = Path(executable_path).parts
    rev = next((i for i, part in enumerate(parts) if part.startswith('chromium-')), None)
    if rev is None:
        raise RuntimeError(f'unexpected Playwright Chromium path {executable_path}')
    binary = SHARED_BROWSERS.joinpath(*parts[rev:])
    if not binary.is_file():
        raise RuntimeError(f'{binary} is missing (playwright upgraded?): {_SETUP_HINT}')
    return str(binary)


def launch_chromium(chromium, display, user, **kwargs):
    """`chromium.launch(**kwargs)` on `display`, sandboxed, and as `user`
    (from browser_user()) when that is set."""
    env = {'DISPLAY': display, 'PATH': '/usr/bin:/bin'}
    if user is None:
        env['HOME'] = os.environ.get('HOME', '/tmp')
        return chromium.launch(chromium_sandbox=True, env=env, **kwargs)
    import pwd
    env.update(HOME=pwd.getpwnam(user).pw_dir, BROWSER_USER=user,
               BROWSER_BIN=shared_binary(chromium.executable_path))
    return chromium.launch(executable_path=str(_WRAPPER), chromium_sandbox=True,
                           env=env, **kwargs)
