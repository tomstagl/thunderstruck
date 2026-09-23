#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Turn a Backstage catalog entity into thunderstruck's edge records.

Pure functions, no I/O. This is the only code that reads catalog JSON, so it
is where untrusted text is narrowed to entity refs, relation types and short
attribute values. Free text never leaves this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ENTITY_REF = re.compile(
    r"^[A-Za-z][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
RELATION_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
ATTRIBUTE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}\Z")
LABEL = re.compile(r"^[a-z][a-z0-9_]{0,31}\Z")
DIRECTIONS = ("inbound", "outbound")


def _target_ref(relation: dict) -> str | None:
    ref = relation.get("targetRef")
    if isinstance(ref, str):
        return ref
    target = relation.get("target")
    if isinstance(target, dict) and isinstance(target.get("kind"), str) \
            and isinstance(target.get("name"), str):
        return f"{target['kind'].lower()}:{target.get('namespace') or 'default'}/{target['name']}"
    return None


def extract_edges(entity: dict[str, Any], edge_types: dict[str, str],
                  source: str) -> list[dict]:
    edges: dict[tuple[str, str], dict] = {}
    relations = entity.get("relations")
    for rel in relations if isinstance(relations, list) else []:
        if not isinstance(rel, dict) or not isinstance(rel.get("type"), str):
            continue
        rtype = rel["type"]
        direction = edge_types.get(rtype)
        neighbour = _target_ref(rel)
        if direction not in DIRECTIONS or neighbour is None or not ENTITY_REF.match(neighbour):
            continue
        edges.setdefault((rtype, neighbour), {
            "ref": f"{rtype} {neighbour}", "type": rtype, "direction": direction,
            "neighbour": neighbour, "source": source, "attributes": {}})
    return [edges[key] for key in sorted(edges)]


def extract_attributes(entity: dict[str, Any],
                       mapping: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    metadata = entity.get("metadata")
    annotations = metadata.get("annotations") if isinstance(metadata, dict) else None
    if not isinstance(annotations, dict):
        annotations = {}
    attributes: dict[str, str] = {}
    rejected: list[str] = []
    for label in sorted(mapping):
        value = annotations.get(mapping[label])
        if value is None:
            continue
        text = str(value).strip()
        if ATTRIBUTE_VALUE.match(text):
            attributes[label] = text
        else:
            rejected.append(label)
    return attributes, rejected


def context_hash(entity_ref: str, edges: list[dict], truncated: dict[str, int]) -> str:
    canonical = json.dumps({"entity_ref": entity_ref, "edges": edges, "truncated": truncated},
                           sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_entity_ref(text: str) -> str | None:
    """The single Backstage Component declared in a catalog-info.yaml."""
    import yaml

    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return None
    refs: list[str] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if not str(doc.get("apiVersion", "")).startswith("backstage.io/"):
            continue
        if str(doc.get("kind", "")).lower() != "component":
            continue
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        name = meta.get("name")
        if not isinstance(name, str):
            continue
        ref = f"component:{meta.get('namespace') or 'default'}/{name}"
        if ENTITY_REF.match(ref):
            refs.append(ref)
    return refs[0] if len(refs) == 1 else None
