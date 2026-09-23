#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Fetch service-catalog context for this repository, deterministically.

Runs the command configured under [context] in .thunderstruck.toml, narrows
its JSON to 1-hop edges with context_extract.py, and writes
.thunderstruck/context.json. No model is involved, so every edge a finding
cites traces back to a command the user approved on this machine.

Never interactive and never fatal to a scan: every problem becomes a status
and a warning in context.json.

    uv run scripts/context.py                  # fetch, or reuse the cache
    uv run scripts/context.py --refresh        # fetch even if the cache is fresh
    uv run scripts/context.py --approve        # trust the configured command here
    uv run scripts/context.py --detect-entity  # print the ref from catalog-info.yaml
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402
from context_extract import (DIRECTIONS, ENTITY_REF, RELATION_TYPE,  # noqa: E402
                             extract_attributes, extract_edges)

DEFAULT_TIMEOUT_S = 20
MAX_TIMEOUT_S = 60
DEFAULT_MAX_AGE_DAYS = 30
TRUST_ENV = "THUNDERSTRUCK_TRUST_CONTEXT"
KINDS = ("command",)
EXTRACTORS = ("backstage-relations",)
LABEL = re.compile(r"^[a-z][a-z0-9_]{0,31}\Z")


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def _is_argv(value: Any) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(part, str) and part for part in value))


def _check_source(src: Any, where: str) -> list[str]:
    if not isinstance(src, dict):
        return [f"{where} must be a table"]
    errors: list[str] = []
    if not isinstance(src.get("name"), str) or not src["name"].strip():
        errors.append(f"{where}.name is missing")
    if src.get("kind") not in KINDS:
        errors.append(f"{where}.kind must be one of {list(KINDS)}")
    if not _is_argv(src.get("argv")):
        errors.append(f"{where}.argv must be a non-empty list of strings")
    if "preflight" in src and not _is_argv(src["preflight"]):
        errors.append(f"{where}.preflight must be a non-empty list of strings")
    timeout = src.get("timeout_s", DEFAULT_TIMEOUT_S)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not 1 <= timeout <= MAX_TIMEOUT_S:
        errors.append(f"{where}.timeout_s must be between 1 and {MAX_TIMEOUT_S} seconds")
    if src.get("extractor") not in EXTRACTORS:
        errors.append(f"{where}.extractor must be one of {list(EXTRACTORS)}")
    types = src.get("edge_types")
    if not isinstance(types, dict) or not types or not all(
            isinstance(k, str) and RELATION_TYPE.match(k) and v in DIRECTIONS
            for k, v in types.items()):
        errors.append(f'{where}.edge_types must map relation types to "inbound" or "outbound"')
    attrs = src.get("neighbour_attributes", {})
    if not isinstance(attrs, dict) or not all(
            isinstance(k, str) and LABEL.match(k) and isinstance(v, str) and v
            for k, v in attrs.items()):
        errors.append(f"{where}.neighbour_attributes must map short lowercase labels "
                      f"to annotation keys")
    return errors


def _normalise_source(src: dict) -> dict:
    return {"name": src.get("name"), "kind": src.get("kind"), "argv": src.get("argv"),
            "preflight": src.get("preflight") or [],
            "timeout_s": src.get("timeout_s", DEFAULT_TIMEOUT_S),
            "extractor": src.get("extractor"), "edge_types": src.get("edge_types"),
            "neighbour_attributes": src.get("neighbour_attributes") or {}}


def load_config(profile: dict) -> tuple[dict | None, list[str]]:
    """The [context] table, normalised, plus every problem found in it."""
    raw = profile.get("context")
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        return None, ["[context] must be a table"]
    errors: list[str] = []
    cfg: dict[str, Any] = {"enabled": raw.get("enabled", True),
                           "entity_ref": raw.get("entity_ref"),
                           "max_age_days": raw.get("max_age_days", DEFAULT_MAX_AGE_DAYS),
                           "sources": []}
    if not isinstance(cfg["enabled"], bool):
        errors.append("context.enabled must be true or false")
    if cfg["enabled"] is False:
        return cfg, errors
    if not isinstance(cfg["entity_ref"], str) or not ENTITY_REF.match(cfg["entity_ref"]):
        errors.append("context.entity_ref must look like kind:namespace/name")
    age = cfg["max_age_days"]
    if isinstance(age, bool) or not isinstance(age, int) or age < 1:
        errors.append("context.max_age_days must be a whole number of days, at least 1")
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("context.sources must list at least one [[context.sources]] table")
        sources = []
    elif len(sources) > 1:
        errors.append("context.sources: this version supports one source")
    for i, src in enumerate(sources):
        errors += _check_source(src, f"context.sources[{i}]")
        if isinstance(src, dict):
            cfg["sources"].append(_normalise_source(src))
    return cfg, errors


def config_hash(cfg: dict) -> str:
    """Identity of what will run. The cache lifetime is not part of it."""
    return c.sha256_text(json.dumps(
        {"entity_ref": cfg["entity_ref"], "sources": cfg["sources"]}, sort_keys=True))


# --------------------------------------------------------------------------
# trust on first use
# --------------------------------------------------------------------------


def trust_store_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "thunderstruck" / "trusted-sources.json"


def _trust_key(repo: Path, chash: str) -> str:
    return f"{Path(repo).resolve()}::{chash}"


def is_trusted(repo: Path, chash: str) -> bool:
    if os.environ.get(TRUST_ENV) == "1":
        return True
    store = c.load_json(trust_store_path(), {}) or {}
    return _trust_key(repo, chash) in (store.get("trusted") or [])


def approve(repo: Path, chash: str) -> Path:
    path = trust_store_path()
    store = c.load_json(path, {}) or {}
    trusted = [k for k in (store.get("trusted") or []) if isinstance(k, str)]
    key = _trust_key(repo, chash)
    if key not in trusted:
        trusted.append(key)
    c.write_json(path, {"schema": "thunderstruck.trust/v1", "trusted": sorted(trusted)})
    return path


# --------------------------------------------------------------------------
# running a command
# --------------------------------------------------------------------------

BUDGET_EXHAUSTED = "not started: the context time budget was used up"


@dataclass
class Fetched:
    doc: dict | None = None
    raw: str = ""
    error: str | None = None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError):
        proc.kill()
    # Wait on the direct child only, then stop reading: a helper that left the
    # process group (e.g. via its own setsid) can still hold stdout open, and
    # draining the pipe with communicate() would hang until it exits.
    proc.wait()
    proc.stdout.close()


def run_command(argv: list[str], entity_ref: str, timeout: float, cwd: Path,
                want_json: bool = True) -> Fetched:
    if timeout <= 0:
        return Fetched(error=BUDGET_EXHAUSTED)
    cmd = [part.replace("{entity_ref}", entity_ref) for part in argv]
    name = Path(cmd[0]).name
    try:
        # Own session, so a timeout can kill the whole process group: a login
        # helper that inherits stdout would otherwise keep communicate() waiting.
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                encoding="utf-8", errors="replace", start_new_session=True)
    except OSError as exc:
        return Fetched(error=f"could not start {name!r} ({exc.strerror or exc})")
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        return Fetched(error=f"{name} timed out after {timeout:.1f}s")
    if proc.returncode != 0:
        return Fetched(error=f"{name} exited {proc.returncode}")
    if not want_json:
        return Fetched()
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        return Fetched(error=f"{name} did not print JSON")
    if not isinstance(doc, dict):
        return Fetched(error=f"{name} printed JSON that is not an object")
    return Fetched(doc=doc, raw=out)


# --------------------------------------------------------------------------
# fetching one source
# --------------------------------------------------------------------------

MAX_PARALLEL = 4
TOTAL_BUDGET_S = 60.0


@dataclass
class SourceResult:
    edges: list[dict] = field(default_factory=list)
    truncated: dict[str, int] = field(default_factory=lambda: {"inbound": 0, "outbound": 0})
    warnings: list[str] = field(default_factory=list)
    raws: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def _listing(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def cap_edges(edges: list[dict]) -> tuple[list[dict], dict[str, int]]:
    kept: list[dict] = []
    counts = {"inbound": 0, "outbound": 0}
    truncated = {"inbound": 0, "outbound": 0}
    for edge in edges:
        direction = edge["direction"]
        if counts[direction] < c.MAX_NEIGHBOURS_PER_DIRECTION:
            kept.append(edge)
            counts[direction] += 1
        else:
            truncated[direction] += 1
    return kept, truncated


def fetch_source(entity_ref: str, source: dict, cwd: Path, budget_s: float) -> SourceResult:
    deadline = time.monotonic() + budget_s

    def allowance() -> float:
        return min(float(source["timeout_s"]), deadline - time.monotonic())

    if source["preflight"]:
        pre = run_command(source["preflight"], entity_ref, allowance(), cwd, want_json=False)
        if pre.error:
            return SourceResult(error=f"preflight failed: {pre.error}")
    main = run_command(source["argv"], entity_ref, allowance(), cwd)
    if main.error:
        return SourceResult(error=main.error)

    edges, truncated = cap_edges(extract_edges(main.doc, source["edge_types"], source["name"]))
    result = SourceResult(edges=edges, truncated=truncated, raws={entity_ref: main.raw})
    if any(truncated.values()):
        result.warnings.append(
            f"service context shows the first {c.MAX_NEIGHBOURS_PER_DIRECTION} neighbours "
            f"per direction; {truncated['inbound']} inbound and {truncated['outbound']} "
            f"outbound are not listed")
    mapping = source["neighbour_attributes"]
    if not mapping or not edges:
        return result

    def fetch(edge: dict) -> Fetched:
        return run_command(source["argv"], edge["neighbour"], allowance(), cwd)

    skipped: list[str] = []
    failed: list[str] = []
    rejected: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        for edge, got in zip(edges, pool.map(fetch, edges)):
            if got.error == BUDGET_EXHAUSTED:
                skipped.append(edge["neighbour"])
            elif got.error:
                failed.append(f"{edge['neighbour']} ({got.error})")
            else:
                edge["attributes"], bad = extract_attributes(got.doc, mapping)
                rejected += [f"{edge['neighbour']} {label}" for label in bad]
                result.raws[edge["neighbour"]] = got.raw
    if skipped:
        result.warnings.append(
            f"{len(skipped)} neighbour(s) not fetched within the {budget_s:g}s context "
            f"budget, so they have no attributes: {_listing(skipped)}")
    if failed:
        result.warnings.append(f"attributes unavailable for {_listing(failed)}")
    if rejected:
        result.warnings.append(
            f"attribute value rejected (not a short label): {_listing(rejected)}")
    return result
