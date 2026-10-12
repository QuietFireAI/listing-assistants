"""private_file.py - secrets on disk that only their owner can read.

Added 2026-10-12. The first full Windows CI run showed the operator's
signing key, the update-signing key and the pager config left readable to
other accounts on Windows: they were made private with chmod(0o600), and
Windows has no POSIX mode bits - chmod there only toggles read-only.

write_private() creates the file private from the first byte:
  - Linux / macOS: os.open(..., 0o600), so the file is never briefly
    readable by others (a later chmod leaves a window).
  - Windows: the file's inherited permissions are removed and only the
    current user is granted access (icacls /inheritance:r /grant:r), then
    the permission list is read back and checked.
Fail-closed: if the file cannot be made private, it is deleted and an
error is raised - a readable secret is never left behind.

is_private() answers the same question for an existing file on either
system; the tests use it.
"""
from __future__ import annotations

import os
import subprocess

WINDOWS = os.name == "nt"


class NotPrivateError(OSError):
    pass


def _whoami() -> str:
    out = subprocess.run(["whoami"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _acl_entries(path: str) -> list[str]:
    """The principals on the file's permission list, from `icacls <path>`.
    icacls prints `<path> PRINCIPAL:(perms)` on the first line, one
    principal per following line, then a blank line and a summary."""
    out = subprocess.run(["icacls", path], capture_output=True, text=True, check=True).stdout
    principals = []
    for i, line in enumerate(out.splitlines()):
        line = line.strip()
        if not line:
            break
        if i == 0:
            line = line[len(path):].strip() if line.lower().startswith(path.lower()) else line
        if ":" in line:
            principals.append(line.rsplit(":(", 1)[0].strip())
    return principals


def _lock_down_windows(path: str) -> None:
    me = _whoami()
    subprocess.run(["icacls", path, "/inheritance:r", "/grant:r", f"{me}:F"],
                   capture_output=True, text=True, check=True)
    ok, why = is_private(path)
    if not ok:
        raise NotPrivateError(why)


def is_private(path: str) -> tuple[bool, str]:
    """(True, how) when only the owner can read the file; (False, why) when
    anyone else can."""
    if WINDOWS:
        me = _whoami().lower()
        principals = [p.lower() for p in _acl_entries(path)]
        others = [p for p in principals if p != me]
        if not principals:
            return False, f"no permission entries read for {path}"
        if others:
            return False, f"{path} is readable by {others} as well as {me}"
        return True, f"only {me} has access (Windows permission list)"
    mode = os.stat(path).st_mode & 0o777
    if mode & 0o077:
        return False, f"{path} has mode {oct(mode)}; others can read it"
    return True, f"mode {oct(mode)}"


def write_private(path: str, data: bytes, exclusive: bool = False) -> None:
    """Writes `data` to `path`, readable only by the current user.
    exclusive=True refuses to replace an existing file (FileExistsError)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    flags |= getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if WINDOWS:
            # lock it down before the secret is written into it
            _lock_down_windows(path)
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if not WINDOWS:
            os.chmod(path, 0o600)   # O_TRUNC on an existing file keeps its old mode
        ok, why = is_private(path)
        if not ok:
            raise NotPrivateError(why)
    except BaseException:
        if fd is not None:
            os.close(fd)
        try:
            os.remove(path)
        except OSError:
            pass
        raise
