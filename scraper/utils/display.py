"""Virtual X display for scrapers that must drive a headful browser.

Some sites serve a real browser window and challenge anything headless
(chinatimes.com since 2026-09-08). On this server there is no X session,
so `virtual_display()` starts a private Xvfb for the duration of a scrape
and hands back its DISPLAY value for the browser launch
(scraper/utils/browser_user.py). Under root the Xvfb runs as the same
unprivileged user as the browser, so neither talks X as root.

When a DISPLAY is already set (a desktop session, or the caller wrapped
the run in `xvfb-run`) it is reused and nothing is started. Needs the
`xvfb` apt package on the server.
"""
import os
import shutil
import subprocess
from contextlib import contextmanager


@contextmanager
def virtual_display(user=None, screen='1366x900x24'):
    """Yield a DISPLAY value; a started Xvfb runs as `user` when given."""
    if os.environ.get('DISPLAY'):
        yield os.environ['DISPLAY']
        return
    if not shutil.which('Xvfb'):
        raise RuntimeError('Xvfb is not installed (apt install xvfb)')

    # -displayfd: Xvfb picks a free display number and writes it to the fd
    # once the server is ready, so there is no fixed :99 to collide on and
    # no sleep-and-hope before the browser launches.
    # A bare environment: an Xvfb running as the browser's user must not
    # carry the pipeline's keys, since that user can read its /proc environ.
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        ['Xvfb', '-displayfd', str(write_fd), '-screen', '0', screen, '-nolisten', 'tcp'],
        pass_fds=(write_fd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={'PATH': '/usr/bin:/bin'},
        **({'user': user, 'group': user, 'extra_groups': []} if user else {}))
    os.close(write_fd)
    try:
        with os.fdopen(read_fd) as ready:
            number = ready.readline().strip()
        if not number:
            raise RuntimeError(f'Xvfb exited before reporting a display (code {proc.poll()})')
        yield f':{number}'
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
