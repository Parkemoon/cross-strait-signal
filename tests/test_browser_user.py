"""scraper/utils/browser_user.py — how a scraper browser is launched: as
the unprivileged user under root, always sandboxed, and with an
environment that never carries the pipeline's keys."""
import os
import pwd
from types import SimpleNamespace

import pytest

from scraper.utils import browser_user as bu


class FakeChromium:
    executable_path = '/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome'

    def launch(self, **kwargs):
        self.kwargs = kwargs
        return 'browser'


def test_shared_binary_swaps_the_install_root(tmp_path, monkeypatch):
    binary = tmp_path / 'chromium-1223' / 'chrome-linux64' / 'chrome'
    binary.parent.mkdir(parents=True)
    binary.write_text('')
    monkeypatch.setattr(bu, 'SHARED_BROWSERS', tmp_path)
    assert bu.shared_binary(FakeChromium.executable_path) == str(binary)


def test_shared_binary_missing_revision_points_at_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(bu, 'SHARED_BROWSERS', tmp_path)
    with pytest.raises(RuntimeError, match='setup_browser_user.sh'):
        bu.shared_binary(FakeChromium.executable_path)


def test_shared_binary_rejects_an_unknown_layout():
    with pytest.raises(RuntimeError, match='unexpected'):
        bu.shared_binary('/usr/bin/chromium')


def test_no_drop_when_not_root(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 1000)
    assert bu.browser_user() is None


def test_root_without_the_user_points_at_setup(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: (_ for _ in ()).throw(KeyError(name)))
    with pytest.raises(RuntimeError, match='setup_browser_user.sh'):
        bu.browser_user()


def test_launch_as_user_goes_through_the_wrapper_with_a_bare_env(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'secret')
    monkeypatch.setattr(pwd, 'getpwnam', lambda name: SimpleNamespace(pw_dir='/var/lib/cs-browser'))
    monkeypatch.setattr(bu, 'shared_binary', lambda path: '/opt/ms-playwright/chromium-1223/chrome-linux64/chrome')
    chromium = FakeChromium()
    assert bu.launch_chromium(chromium, ':7', 'cs-browser', headless=False) == 'browser'
    kw = chromium.kwargs
    assert kw['executable_path'].endswith('run_browser_as.sh')
    assert os.access(kw['executable_path'], os.X_OK)
    assert kw['chromium_sandbox'] is True and kw['headless'] is False
    assert kw['env'] == {
        'DISPLAY': ':7', 'PATH': '/usr/bin:/bin', 'HOME': '/var/lib/cs-browser',
        'BROWSER_USER': 'cs-browser',
        'BROWSER_BIN': '/opt/ms-playwright/chromium-1223/chrome-linux64/chrome',
    }


def test_launch_without_user_is_direct_and_still_bare(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'secret')
    monkeypatch.setenv('HOME', '/home/ed')
    chromium = FakeChromium()
    bu.launch_chromium(chromium, ':0', None, headless=False)
    kw = chromium.kwargs
    assert 'executable_path' not in kw
    assert kw['chromium_sandbox'] is True
    assert kw['env'] == {'DISPLAY': ':0', 'PATH': '/usr/bin:/bin', 'HOME': '/home/ed'}
