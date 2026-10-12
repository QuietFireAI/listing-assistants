"""client_drawer - Client Isolation, Anti-Commingling, and Drawer Management System.

What this module enforces (and what it does not):

  ENFORCED HERE
  1. One Client, One Drawer: each client_id maps to exactly one directory
     under the drawer root.
  2. Path safety: client ids, categories and filenames are single, plain
     path segments (letters, digits, '.', '_', '-'; no separators, no '..',
     no absolute paths). Every resolved path is re-checked to lie inside its
     drawer (realpath containment), so neither '../' nor a symlink can carry
     a read or write into another client's drawer or outside the root.
     Fixed 2026-10-11 (audit D-1): before this, a filename such as
     '../../bob/documents/x' filed under alice landed in bob's drawer, and a
     client_id of '../../escaped' created a drawer outside the root.
  3. Context binding: record_agent_artifact() requires the caller's acting
     client_context_id and refuses (ComminglingBreachError) when it differs
     from the target drawer. Fixed 2026-10-11 (audit D-2): the old check only
     asked whether the target drawer existed.
  4. No silent identity overwrite: re-provisioning an existing drawer with a
     different client name or property address is refused unless the caller
     passes update_identity=True.

  NOT ENFORCED HERE
  - Encryption at rest. Files are written as plain files; protect the volume
    (OS permissions / full-disk encryption) if that is required.
  - Tamper detection on stored files. Each file's SHA-256 is recorded in the
    manifest at write time; verify_hashes() recomputes and reports
    mismatches on demand. Nothing watches the files continuously.
  - Wiring (2026-10-12): agents 04, 05, 07, 08, 14 and 15 file records
    through dispatcher/drawer_filing.py, and the HITL protocol records holds;
    see that module for what is filed where.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Optional

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class ComminglingBreachError(Exception):
    """Raised when an access would cross client boundaries or escape a drawer."""
    pass


def _safe_segment(value: str, what: str) -> str:
    """A single plain path segment, or ComminglingBreachError. Fail closed:
    anything that is not obviously one segment is refused, not repaired."""
    if not isinstance(value, str) or not _SEGMENT.match(value) or value in (".", ".."):
        raise ComminglingBreachError(
            f"{what} {value!r} is not a single safe path segment "
            f"(allowed: letters, digits, '.', '_', '-'; no separators, no '..') "
            f"- refused fail-closed")
    return value


def _contained(path: str, root: str) -> str:
    """realpath(path) must be root itself or inside it."""
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise ComminglingBreachError(
            f"resolved path {real!r} is outside {real_root!r} - refused fail-closed")
    return real


class ClientDrawer:
    """Represents an isolated physical and logical drawer for a single real estate client."""

    CATEGORIES = ("artifacts", "documents", "interactions", "financials", "timeline", "audit")

    def __init__(self, client_id: str, drawer_root: str):
        self.client_id = _safe_segment(client_id, "client_id")
        self.drawer_root = os.path.abspath(drawer_root)
        self.drawer_path = _contained(os.path.join(self.drawer_root, client_id), self.drawer_root)
        self.categories = list(self.CATEGORIES)
        self._ensure_structure()

    def _ensure_structure(self):
        """Creates the isolated drawer directory structure."""
        os.makedirs(self.drawer_path, exist_ok=True)
        for cat in self.categories:
            os.makedirs(os.path.join(self.drawer_path, cat), exist_ok=True)

    def _file_path(self, category: str, filename: str) -> str:
        if category not in self.categories:
            raise ValueError(f"unknown drawer category {category!r}; "
                             f"categories are {self.categories}")
        _safe_segment(filename, "filename")
        return _contained(os.path.join(self.drawer_path, category, filename),
                          self.drawer_path)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.drawer_path, "drawer_manifest.json")

    def initialize_manifest(
        self,
        client_name: str,
        property_address: str,
        role: str = "seller",
        assigned_agent: str = "00",
        extra_metadata: Optional[dict] = None,
        update_identity: bool = False
    ):
        """Initializes the human-supplied client manifest. An existing manifest
        with a different name/address is never silently overwritten."""
        existing = None
        if os.path.exists(self.manifest_path):
            # A corrupt manifest is an error to surface, not something to
            # paper over with a fresh one (that would erase the file index).
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            same = (existing.get("client_name") == client_name and
                    existing.get("property_address") == property_address)
            if not same and not update_identity:
                raise ComminglingBreachError(
                    f"drawer {self.client_id!r} already belongs to "
                    f"{existing.get('client_name')!r} at "
                    f"{existing.get('property_address')!r}; refusing to "
                    f"overwrite identity (pass update_identity=True to change it)")
        manifest = {
            "client_id": self.client_id,
            "client_name": client_name,
            "property_address": property_address,
            "role": role,
            "assigned_human_agent": assigned_agent,
            "created_at": (existing or {}).get("created_at", "runtime"),
            "metadata": extra_metadata or {},
            "file_index": (existing or {}).get("file_index", {})
        }
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def get_manifest(self) -> dict:
        if os.path.exists(self.manifest_path):
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"client_id": self.client_id, "file_index": {}}

    def store_file(
        self,
        agent_id: str,
        category: str,
        filename: str,
        content: str | bytes,
        metadata: Optional[dict] = None
    ) -> str:
        """Stores a file inside this client's drawer and records its SHA-256."""
        target_file = self._file_path(category, filename)
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        with open(target_file, "wb") as f:
            f.write(content_bytes)
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        manifest = self.get_manifest()
        manifest.setdefault("file_index", {})[f"{category}/{filename}"] = {
            "agent_id": agent_id,
            "category": category,
            "filename": filename,
            "sha256": file_hash,
            "size_bytes": len(content_bytes),
            "metadata": metadata or {}
        }
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return target_file

    def get_file(self, category: str, filename: str) -> Optional[bytes]:
        """Retrieves a file strictly from within this client's drawer."""
        target_file = self._file_path(category, filename)
        if os.path.exists(target_file):
            with open(target_file, "rb") as f:
                return f.read()
        return None

    def list_files(self, category: Optional[str] = None) -> list[dict]:
        """Lists all files indexed in this client's drawer."""
        index = self.get_manifest().get("file_index", {})
        if category:
            return [v for v in index.values() if v.get("category") == category]
        return list(index.values())

    def verify_hashes(self) -> dict:
        """Recomputes every indexed file's SHA-256 against the manifest.
        Returns {ok, checked, mismatched: [...], missing: [...]}."""
        mismatched, missing, checked = [], [], 0
        for key, entry in self.get_manifest().get("file_index", {}).items():
            data = self.get_file(entry["category"], entry["filename"])
            if data is None:
                missing.append(key)
                continue
            checked += 1
            if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                mismatched.append(key)
        return {"ok": not mismatched and not missing, "checked": checked,
                "mismatched": mismatched, "missing": missing}


class ClientDrawerManager:
    """Master controller for all client drawers."""

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)
        os.makedirs(self.storage_root, exist_ok=True)
        self._active_drawers: dict[str, ClientDrawer] = {}
        self._load_existing_drawers()

    def _load_existing_drawers(self):
        """Mounts existing drawers. Directory names that are not safe client
        ids, and symlinks, are skipped (never mounted)."""
        for entry in os.listdir(self.storage_root):
            full_path = os.path.join(self.storage_root, entry)
            if os.path.isdir(full_path) and _SEGMENT.match(entry) and not os.path.islink(full_path):
                self._active_drawers[entry] = ClientDrawer(entry, self.storage_root)

    def provision_drawer(
        self,
        client_id: str,
        client_name: str,
        property_address: str,
        role: str = "seller",
        assigned_agent: str = "00",
        metadata: Optional[dict] = None,
        update_identity: bool = False
    ) -> ClientDrawer:
        """Provisions an isolated client drawer identified by human input."""
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")
        drawer = ClientDrawer(client_id, self.storage_root)
        drawer.initialize_manifest(
            client_name=client_name,
            property_address=property_address,
            role=role,
            assigned_agent=assigned_agent,
            extra_metadata=metadata,
            update_identity=update_identity
        )
        self._active_drawers[client_id] = drawer
        return drawer

    def has_drawer(self, client_id: str) -> bool:
        try:
            _safe_segment(client_id, "client_id")
        except ComminglingBreachError:
            return False
        path = os.path.join(self.storage_root, client_id)
        return client_id in self._active_drawers or (
            os.path.isdir(path) and not os.path.islink(path))

    def get_drawer(self, client_id: str) -> ClientDrawer:
        """Retrieves an existing drawer. Fails closed if it does not exist or
        the id is not a safe segment."""
        _safe_segment(client_id, "client_id")
        if client_id in self._active_drawers:
            return self._active_drawers[client_id]
        if self.has_drawer(client_id):
            drawer = ClientDrawer(client_id, self.storage_root)
            self._active_drawers[client_id] = drawer
            return drawer
        raise ComminglingBreachError(
            f"Client drawer {client_id!r} does not exist. Action rejected to prevent commingling.")

    def record_agent_artifact(
        self,
        client_id: str,
        agent_id: str,
        category: str,
        filename: str,
        content: str | bytes,
        metadata: Optional[dict] = None,
        *,
        acting_client_context_id: str
    ) -> str:
        """Files an agent artifact. The caller must state the client context it
        is acting for; a mismatch with the target drawer is a breach."""
        if acting_client_context_id != client_id:
            raise ComminglingBreachError(
                f"Agent {agent_id} acting for {acting_client_context_id!r} attempted "
                f"to file {filename!r} into drawer {client_id!r} - cross-client "
                f"filing blocked fail-closed.")
        if not self.has_drawer(client_id):
            raise ComminglingBreachError(
                f"Agent {agent_id} attempted to file {filename!r} for unprovisioned client {client_id!r}. "
                f"Filing blocked fail-closed to prevent commingling.")
        return self.get_drawer(client_id).store_file(
            agent_id=agent_id, category=category, filename=filename,
            content=content, metadata=metadata)

    def list_all_clients(self) -> list[dict]:
        """Returns summary dossiers of all provisioned clients."""
        summaries = []
        for cid, drawer in self._active_drawers.items():
            manifest = drawer.get_manifest()
            summaries.append({
                "client_id": cid,
                "client_name": manifest.get("client_name", "Unknown"),
                "property_address": manifest.get("property_address", "Unknown"),
                "role": manifest.get("role", "seller"),
                "file_count": len(manifest.get("file_index", {}))
            })
        return summaries
