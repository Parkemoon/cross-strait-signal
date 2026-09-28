"""api/auth.py — the admin-token checks. A header the token can't match must
be a plain mismatch, never an exception: hmac.compare_digest raises
TypeError on a str with non-ASCII characters, which used to 500 every
route that reads the header."""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.auth import is_admin, require_admin  # noqa: E402


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret-token")


def test_valid_token():
    assert is_admin("s3cret-token") is True
    assert require_admin("s3cret-token") is None


@pytest.mark.parametrize("header", ["", "wrong", "é", "s3cret-tokén", "ÿ" * 40])
def test_mismatch_is_false_not_an_error(header):
    assert is_admin(header) is False
    with pytest.raises(HTTPException) as e:
        require_admin(header)
    assert e.value.status_code == 401


def test_unset_token_trusts_everyone(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    assert is_admin("é") is True
    assert require_admin("é") is None
