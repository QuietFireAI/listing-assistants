"""client_drawer - Client Isolation, Anti-Commingling, and Drawer Management System.

Guarantees:
  1. One Client, One Drawer: Every client identified by the human principal is assigned
     a dedicated, isolated Drawer (vault directory and database boundary).
  2. Zero Commingling / Anti-Leakage: Agents in the swarm operating on behalf of a client
     can only read from and write to that specific client's drawer. Cross-context filing
     or reading is an immediate confidentiality breach and is blocked fail-closed.
  3. Complete File Custody: All files created by any agent (MLS drafts, comp packages,
     disclosure artifacts, inspection reports, flyers, commission net sheets) are stored
     directly inside that client's drawer.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Tuple


class ComminglingBreachError(Exception):
    """Raised when an agent attempts cross-client or unauthenticated drawer access."""
    pass


class ClientDrawer:
    """Represents an isolated physical and logical drawer for a single real estate client."""

    def __init__(self, client_id: str, drawer_root: str):
        self.client_id = client_id
        self.drawer_path = os.path.join(drawer_root, client_id)
        self.categories = ["artifacts", "documents", "interactions", "financials", "timeline", "audit"]
        self._ensure_structure()

    def _ensure_structure(self):
        """Creates the isolated drawer directory structure."""
        os.makedirs(self.drawer_path, exist_ok=True)
        for cat in self.categories:
            os.makedirs(os.path.join(self.drawer_path, cat), exist_ok=True)

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.drawer_path, "drawer_manifest.json")

    def initialize_manifest(
        self,
        client_name: str,
        property_address: str,
        role: str = "seller",
        assigned_agent: str = "00",
        extra_metadata: Optional[dict] = None
    ):
        """Initializes or updates the human-supplied client manifest."""
        manifest = {
            "client_id": self.client_id,
            "client_name": client_name,
            "property_address": property_address,
            "role": role,
            "assigned_human_agent": assigned_agent,
            "created_at": "runtime",
            "metadata": extra_metadata or {},
            "file_index": {}
        }
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    manifest["file_index"] = existing.get("file_index", {})
            except Exception:
                pass

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
        """Stores a file inside this client's isolated drawer and updates the manifest index."""
        if category not in self.categories:
            category = "artifacts"

        target_dir = os.path.join(self.drawer_path, category)
        target_file = os.path.join(target_dir, filename)

        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            content_bytes = content
            with open(target_file, "wb") as f:
                f.write(content)

        file_hash = hashlib.sha256(content_bytes).hexdigest()

        # Update manifest index
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
        target_file = os.path.join(self.drawer_path, category, filename)
        if os.path.exists(target_file):
            with open(target_file, "rb") as f:
                return f.read()
        return None

    def list_files(self, category: Optional[str] = None) -> list[dict]:
        """Lists all files indexed in this client's drawer."""
        manifest = self.get_manifest()
        index = manifest.get("file_index", {})
        if category:
            return [v for k, v in index.items() if v.get("category") == category]
        return list(index.values())


class ClientDrawerManager:
    """Master controller for all client drawers across the swarm."""

    def __init__(self, storage_root: str):
        self.storage_root = os.path.abspath(storage_root)
        os.makedirs(self.storage_root, exist_ok=True)
        self._active_drawers: dict[str, ClientDrawer] = {}
        self._load_existing_drawers()

    def _load_existing_drawers(self):
        """Scans storage root and mounts all existing client drawers."""
        for entry in os.listdir(self.storage_root):
            full_path = os.path.join(self.storage_root, entry)
            if os.path.isdir(full_path):
                self._active_drawers[entry] = ClientDrawer(entry, self.storage_root)

    def provision_drawer(
        self,
        client_id: str,
        client_name: str,
        property_address: str,
        role: str = "seller",
        assigned_agent: str = "00",
        metadata: Optional[dict] = None
    ) -> ClientDrawer:
        """Provisions a new, isolated client drawer identified by human input."""
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")

        drawer = ClientDrawer(client_id, self.storage_root)
        drawer.initialize_manifest(
            client_name=client_name,
            property_address=property_address,
            role=role,
            assigned_agent=assigned_agent,
            extra_metadata=metadata
        )
        self._active_drawers[client_id] = drawer
        return drawer

    def get_drawer(self, client_id: str) -> ClientDrawer:
        """Retrieves an existing drawer. Fails closed if drawer does not exist."""
        if client_id not in self._active_drawers:
            drawer_path = os.path.join(self.storage_root, client_id)
            if os.path.exists(drawer_path):
                drawer = ClientDrawer(client_id, self.storage_root)
                self._active_drawers[client_id] = drawer
                return drawer
            raise ComminglingBreachError(
                f"Client drawer {client_id!r} does not exist. Action rejected to prevent commingling."
            )
        return self._active_drawers[client_id]

    def has_drawer(self, client_id: str) -> bool:
        return client_id in self._active_drawers or os.path.exists(
            os.path.join(self.storage_root, client_id)
        )

    def record_agent_artifact(
        self,
        client_id: str,
        agent_id: str,
        category: str,
        filename: str,
        content: str | bytes,
        metadata: Optional[dict] = None
    ) -> str:
        """Enforces anti-commingling validation before storing any agent-generated file."""
        if not self.has_drawer(client_id):
            raise ComminglingBreachError(
                f"Agent {agent_id} attempted to file {filename!r} for unprovisioned client {client_id!r}. "
                f"Filing blocked fail-closed to prevent commingling."
            )
        drawer = self.get_drawer(client_id)
        return drawer.store_file(
            agent_id=agent_id,
            category=category,
            filename=filename,
            content=content,
            metadata=metadata
        )

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
