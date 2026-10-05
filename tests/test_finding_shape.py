"""finding_shape.py: the one implementation of turning an investigator's
answer into a finding file, shared by save_finding.py and the SubagentStop
hook, so a finding saved either way is byte-identical (#5)."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from test_investigator_contract import _malformed
from test_pipeline import _hotspots, _valid_finding

ROOT = Path(__file__).resolve().parent.parent
SHAPE = ROOT / "scripts" / "finding_shape.py"


def test_parse_result_accepts_fenced_and_unfenced_objects():
    import finding_shape as fs
    assert fs.parse_result('{"a": 1}') == {"a": 1}
    assert fs.parse_result('  ```json\n{"a": 1}\n```\n') == {"a": 1}


@pytest.mark.parametrize("raw", ["Here is the result:\n{}", "[]", "{not json"])
def test_parse_result_rejects_anything_but_one_object(raw):
    import finding_shape as fs
    with pytest.raises(ValueError):
        fs.parse_result(raw)


@pytest.mark.parametrize("malformed", [False, True])
def test_shape_matches_save_finding_byte_for_byte(scanned_copy, tmp_path, malformed):
    import finding_shape as fs
    data = _hotspots(scanned_copy)
    hid, doc = _valid_finding(scanned_copy, data)
    doc["validated_with"] = "forged"
    doc["findings"][0]["key"] = "forged"
    if malformed:
        doc = _malformed(doc)
    src = tmp_path / "result.json"
    src.write_text(json.dumps(doc))
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "save_finding.py"),
                           "--repo", str(scanned_copy), "--id", hid, "--from", str(src)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    saved = (scanned_copy / ".thunderstruck" / "findings" / f"{hid}.json").read_bytes()

    index = json.loads((scanned_copy / ".thunderstruck" / "bundles" / "index.json").read_text())
    entry = fs.find_entry(index, hid)
    dest = tmp_path / "out" / f"{hid}.json"
    fs.write_json_atomic(dest, fs.shape(fs.parse_result(src.read_text()), entry))
    assert dest.read_bytes() == saved


def test_failed_doc_is_stamped(scanned_copy):
    import finding_shape as fs
    index = json.loads((scanned_copy / ".thunderstruck" / "bundles" / "index.json").read_text())
    entry = index["bundles"][0]
    doc = fs.failed_doc(entry)
    assert doc["analysis_failed"] is True and doc["findings"] == []
    assert doc["hotspot_id"] == entry["id"] and doc["file"] == entry["file"]
    assert doc["bundle_hash"] == entry["bundle_hash"]
    assert doc["schema"] == fs.FINDING_SCHEMA_VERSION


def test_write_json_atomic_refuses_a_symlinked_directory(tmp_path):
    import finding_shape as fs
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "findings"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        fs.write_json_atomic(link / "H01.json", {"a": 1})
    assert list(real.iterdir()) == []


def test_write_json_atomic_leaves_no_temp_file(tmp_path):
    import finding_shape as fs
    fs.write_json_atomic(tmp_path / "d" / "H01.json", {"a": 1})
    assert [p.name for p in (tmp_path / "d").iterdir()] == ["H01.json"]
    assert (tmp_path / "d" / "H01.json").read_text() == '{\n  "a": 1\n}\n'


@pytest.mark.parametrize("hid", ["../H01", "H01 ", 1, None, "H99"])
def test_find_entry_matches_exact_ids_only(hid):
    import finding_shape as fs
    index = {"bundles": [{"id": "H01", "file": "a.py", "bundle_hash": "x"}]}
    assert fs.find_entry(index, hid) is None
    assert fs.find_entry(index, "H01")["file"] == "a.py"


def test_record_agent_appends_for_the_same_bundle_and_resets_for_another(tmp_path):
    import finding_shape as fs
    entry = {"id": "H01", "file": "a.py", "bundle_hash": "h1"}
    fs.record_agent(tmp_path, entry, {"agent_id": "a1", "kind": "first"})
    fs.record_agent(tmp_path, entry, {"agent_id": "a2", "kind": "respawn"})
    rec = json.loads((tmp_path / "agents" / "H01.json").read_text())
    assert rec["hotspot_id"] == "H01" and rec["bundle_hash"] == "h1"
    assert [a["agent_id"] for a in rec["agents"]] == ["a1", "a2"]

    fs.record_agent(tmp_path, {**entry, "bundle_hash": "h2"}, {"agent_id": "a3", "kind": "first"})
    rec = json.loads((tmp_path / "agents" / "H01.json").read_text())
    assert rec["bundle_hash"] == "h2"
    assert [a["agent_id"] for a in rec["agents"]] == ["a3"]


def test_finding_shape_imports_the_stdlib_only():
    tree = ast.parse(SHAPE.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module.split(".")[0])
    outside = {n for n in names if n not in sys.stdlib_module_names and n != "__future__"}
    assert not outside, f"finding_shape.py imports {outside}"
