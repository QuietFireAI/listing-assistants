"""Secrets on disk are readable by their owner only - on Linux, macOS and
Windows (dispatcher/private_file.py, added 2026-10-12 after the first
Windows CI run showed chmod(0o600) does nothing there)."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dispatcher.private_file import is_private, write_private  # noqa: E402


def test_write_private_is_private_from_the_start(tmp_path):
    p = str(tmp_path / "a" / "secret.bin")
    write_private(p, b"\x00\x01secret")
    ok, how = is_private(p)
    assert ok, how
    assert open(p, "rb").read() == b"\x00\x01secret"


def test_overwrite_keeps_it_private_even_if_it_was_not(tmp_path):
    p = str(tmp_path / "loose.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{}")
    if os.name != "nt":
        os.chmod(p, 0o644)
        assert not is_private(p)[0]          # the check can say no
    write_private(p, b'{"k": 1}')
    assert is_private(p)[0], is_private(p)[1]


def test_exclusive_never_replaces_an_existing_secret(tmp_path):
    p = str(tmp_path / "authority.key")
    write_private(p, b"first", exclusive=True)
    with pytest.raises(FileExistsError):
        write_private(p, b"second", exclusive=True)
    assert open(p, "rb").read() == b"first"   # untouched, not deleted


def test_console_init_operator_key_is_private(tmp_path):
    env = {**os.environ, "LISTINGASSISTANTS_STATE_DIR": str(tmp_path / "state")}
    out = subprocess.run([sys.executable, "tools/console.py", "init"], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    line = json.loads(out.stdout.strip().splitlines()[-1])
    assert line["operator_key"].startswith("generated, private: ")
    key = os.path.join(str(tmp_path / "state"), "operator-key.bin")
    assert os.path.exists(key), os.listdir(str(tmp_path / "state"))
    assert is_private(key)[0], is_private(key)[1]


@pytest.mark.skipif(os.name != "nt", reason="the Windows permission-list check")
def test_windows_check_sees_another_account(tmp_path):
    """The Windows branch is not vacuous: give Everyone read access and the
    check must say the file is no longer private."""
    p = str(tmp_path / "secret.bin")
    write_private(p, b"s")
    assert is_private(p)[0], is_private(p)[1]
    subprocess.run(["icacls", p, "/grant", "*S-1-1-0:R"], check=True,
                   capture_output=True)                      # S-1-1-0 = Everyone
    ok, why = is_private(p)
    assert not ok and "readable by" in why, why
