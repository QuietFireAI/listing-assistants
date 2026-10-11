"""Kills the logic mutants that survived in dispatcher/client_drawer.py
(post-fix mutmut run, 2026-10-11)."""
import json
import os

import pytest
from dispatcher.client_drawer import ClientDrawerManager, ComminglingBreachError


def test_drawer_created_by_another_manager_is_found_and_loaded(tmp_path):
    root = str(tmp_path / "drawers")
    ClientDrawerManager(root).provision_drawer("ctx-a", "Alice", "1 Oak")
    late = ClientDrawerManager(root)
    late._active_drawers.clear()                       # simulate a drawer made after this manager loaded
    d = late.get_drawer("ctx-a")
    assert d.client_id == "ctx-a" and d.drawer_root == os.path.abspath(root)
    assert late._active_drawers["ctx-a"] is d and late.get_drawer("ctx-a") is d
    assert d.get_manifest()["client_name"] == "Alice"


def test_missing_drawer_and_unsafe_ids_name_the_problem(tmp_path):
    m = ClientDrawerManager(str(tmp_path / "drawers"))
    with pytest.raises(ComminglingBreachError, match="'ghost' does not exist"):
        m.get_drawer("ghost")
    with pytest.raises(ComminglingBreachError, match=r"client_id '\.\./x' is not a single safe path segment"):
        m.get_drawer("../x")
    assert m.has_drawer("a/b") is False                # unsafe id: not a drawer (no raise, by design)
    d = m.provision_drawer("ctx-a", "Alice", "1 Oak")
    with pytest.raises(ComminglingBreachError, match="filename"):
        d.store_file("04", "artifacts", "../x.md", "x")
    with pytest.raises(ValueError, match="unknown drawer category 'secrets'"):
        d.store_file("04", "secrets", "x.md", "x")


def test_has_drawer_requires_a_real_directory_under_the_root(tmp_path, monkeypatch):
    root = tmp_path / "drawers"
    m = ClientDrawerManager(str(root))
    assert m.has_drawer("ctx-a") is False
    elsewhere = tmp_path / "elsewhere" / "ctx-b"
    elsewhere.mkdir(parents=True)
    os.symlink(elsewhere, root / "ctx-b")              # symlinked drawer dir is not a drawer
    assert m.has_drawer("ctx-b") is False
    (tmp_path / "ctx-c").mkdir()                       # same name outside the root is not a drawer
    monkeypatch.chdir(tmp_path)
    assert m.has_drawer("ctx-c") is False
    m.provision_drawer("ctx-d", "Dee", "4 Elm")
    m._active_drawers.clear()
    assert m.has_drawer("ctx-d") is True


def test_artifact_keeps_agent_and_metadata(tmp_path):
    m = ClientDrawerManager(str(tmp_path / "drawers"))
    m.provision_drawer("ctx-a", "Alice", "1 Oak")
    m.record_agent_artifact("ctx-a", "04", "artifacts", "r.md", "x", metadata={"v": 2},
                            acting_client_context_id="ctx-a")
    entry = m.get_drawer("ctx-a").get_manifest()["file_index"]["artifacts/r.md"]
    assert entry["agent_id"] == "04" and entry["metadata"] == {"v": 2}
    with pytest.raises(ComminglingBreachError, match="Agent 04 acting for 'ctx-b'"):
        m.record_agent_artifact("ctx-a", "04", "artifacts", "s.md", "x", acting_client_context_id="ctx-b")


def test_verify_hashes_counts_every_file_and_names_missing_ones(tmp_path):
    m = ClientDrawerManager(str(tmp_path / "drawers"))
    d = m.provision_drawer("ctx-a", "Alice", "1 Oak")
    for name in ("a.md", "b.md", "c.md"):
        d.store_file("04", "artifacts", name, name)
    assert d.verify_hashes() == {"ok": True, "checked": 3, "mismatched": [], "missing": []}
    os.remove(os.path.join(d.drawer_path, "artifacts", "a.md"))
    (open(os.path.join(d.drawer_path, "artifacts", "c.md"), "w")).write("tampered")
    v = d.verify_hashes()
    assert v == {"ok": False, "checked": 2, "mismatched": ["artifacts/c.md"], "missing": ["artifacts/a.md"]}


def test_empty_drawer_verifies_clean(tmp_path):
    d = ClientDrawerManager(str(tmp_path / "drawers")).provision_drawer("ctx-a", "Alice", "1 Oak")
    assert d.verify_hashes() == {"ok": True, "checked": 0, "mismatched": [], "missing": []}
