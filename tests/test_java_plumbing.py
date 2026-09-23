"""Java is a new leaf under the existing pipeline: a language mapping, a
_lang_key branch, and nothing else changes shape. This pins that the
pipeline doesn't crash on Java before any detector exists for it, and that
the calibration sweep sees every tracked file."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import _common


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    return root


def test_java_extension_maps_to_java_language(catalog):
    langmap = _common.language_map(catalog)
    assert _common.detect_language("src/Main.java", langmap) == "java"


def test_java_file_scans_without_crashing(tmp_path, plugin_root):
    # No package statement and CRLF line endings: Review Focus #1.
    repo = _git_repo(tmp_path / "repo", {"src/Main.java": (
        "public class Main {\r\n"
        "    public static void main(String[] args) {\r\n"
        "        System.out.println(\"hi\");\r\n"
        "    }\r\n"
        "}\r\n")})
    result = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "signals.py"),
         "--repo", str(repo), "--top", "5"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((repo / ".thunderstruck" / "hotspots.json").read_text())
    assert data["schema"] == "thunderstruck.hotspots/v1"
    ranked = {h["file"]: h["language"] for h in data["hotspots"]}
    assert ranked.get("src/Main.java") == "java"


def test_calibrate_sweeps_every_tracked_file(tmp_path, plugin_root):
    # calibrate.py must see hits outside any hotspot ranking, and must skip
    # test directories by default exactly as signals.py does.
    body = "class A {\n    Object q = new java.util.concurrent.LinkedBlockingQueue<>();\n}\n"
    repo = _git_repo(tmp_path / "cal", {
        "src/main/java/A.java": body,
        "src/test/java/ATest.java": body,
    })
    result = subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "calibrate.py"),
         "--repo", str(repo), "--lang", "java", "--patterns", "S14"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # No Java S14 detector exists yet in Task 1; the sweep must still run
    # cleanly and print nothing rather than fail.
    assert "ATest.java" not in result.stdout
