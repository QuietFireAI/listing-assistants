"""private_file.py - secrets on disk that only their owner can read.

Added 2026-10-12. The first full Windows CI run showed the operator's
signing key, the update-signing key and the pager config left readable to
other accounts on Windows: they were made private with chmod(0o600), and
Windows has no POSIX mode bits - chmod there only toggles read-only.

write_private() creates the file private from the first byte:
  - Linux / macOS: os.open(..., 0o600), so the file is never briefly
    readable by others (a later chmod leaves a window).
  - Windows: the file's inherited permissions are removed, Everyone /
    Users / Authenticated Users are stripped, the current user is granted
    access by security id, and the permission list is read back (as SDDL)
    and checked: only you, SYSTEM, Administrators and OWNER RIGHTS may
    remain - the same reach root has over a 0600 file on Linux.
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


# Who may be on a private file's permission list on Windows, by security
# id: you, the operating system (SYSTEM) and the machine's administrators -
# the same reach root has over a 0600 file on Linux - and OWNER RIGHTS.
# Anyone else - Everyone, Users, Authenticated Users, another person - makes
# the file not private. Ids, not names: names are translated on non-English
# Windows ("Administratoren").
_SDDL_ALIASES = {"SY": "S-1-5-18", "BA": "S-1-5-32-544", "OW": "S-1-3-4",
                 "WD": "S-1-1-0", "BU": "S-1-5-32-545", "AU": "S-1-5-11",
                 "CO": "S-1-3-0", "IU": "S-1-5-4", "NU": "S-1-5-2"}
_ALLOWED_OTHERS = {"S-1-5-18", "S-1-5-32-544", "S-1-3-4"}
_STRIP = ("*S-1-1-0", "*S-1-5-32-545", "*S-1-5-11")     # Everyone, Users, Authenticated Users


def _my_sid() -> str:
    out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out.rsplit(",", 1)[-1].strip().strip('"')


def _sddl(path: str) -> str:
    """The file's security descriptor as SDDL text, from `icacls /save`."""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".acl")
    os.close(fd)
    try:
        subprocess.run(["icacls", path, "/save", tmp, "/q"],
                       capture_output=True, text=True, check=True)
        raw = open(tmp, "rb").read()
    finally:
        os.remove(tmp)
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-16-le")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else ""


def _allow_trustees(sddl: str) -> list[str]:
    """The security ids granted access (allow entries) in the DACL."""
    import re
    dacl = sddl.split("D:", 1)[1] if "D:" in sddl else ""
    dacl = re.split(r"S:(?=[A-Z(])", dacl)[0]          # stop at the audit list, if any
    out = []
    for kind, trustee in re.findall(r"\(([A-Z]+);[^;]*;[^;]*;[^;]*;[^;]*;([^)]+)\)", dacl):
        if kind in ("A", "OA"):
            out.append(_SDDL_ALIASES.get(trustee, trustee))
    return out


def _lock_down_windows(path: str) -> None:
    me = _my_sid()
    subprocess.run(["icacls", path, "/inheritance:r", "/remove:g", *_STRIP],
                   capture_output=True, text=True, check=True)
    subprocess.run(["icacls", path, "/grant:r", f"*{me}:F"],
                   capture_output=True, text=True, check=True)
    ok, why = is_private(path)
    if not ok:
        raise NotPrivateError(why)


def is_private(path: str) -> tuple[bool, str]:
    """(True, how) when no ordinary account but yours can open the file;
    (False, why) otherwise."""
    if WINDOWS:
        me = _my_sid()
        sddl = _sddl(path)
        trustees = _allow_trustees(sddl)
        if me.endswith("-500"):
            trustees = [me if t == "LA" else t for t in trustees]   # the built-in Administrator
        if me not in trustees:
            return False, f"{path}: your account is not on its permission list ({sddl})"
        others = sorted({t for t in trustees if t != me and t not in _ALLOWED_OTHERS})
        if others:
            return False, f"{path} is readable by {others} as well as you ({sddl})"
        return True, "only your account (plus SYSTEM and Administrators) on the Windows permission list"
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
