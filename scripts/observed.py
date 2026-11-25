#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Observe, in the repository's tracked files, where it reaches other systems (#6).

Deterministic: no model, no network, no command but git. Reads tracked files,
hotspots.json and context.json, and writes .thunderstruck/observed.json. A
finding can cite only an observation this step produced.

Spec: docs/superpowers/specs/2026-09-25-observed-dependencies-design.md.
The forms it recognises are data in catalog/observed.yaml.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _common as c  # noqa: E402

KINDS = ("host", "env", "secret")
FORM_KINDS = ("request", "response", "connect", "read", "config", "mesh")

HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)*\Z")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}\Z")
SECRET_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}\Z")
TEMPLATED = re.compile(r"[${}%<]")
MAX_HOST_LEN = 253
MAX_ARGS = 2000

# §2.1: a URL starts at a scheme; the token runs to whitespace or a quote.
_SCHEME = re.compile(r"(?<![a-z0-9+.-])([a-z][a-z0-9+.-]{1,15})://")
_TOKEN_END = re.compile(r"[\s'\"`]")
_HOST_END = re.compile(r"[:?#\[\]/]")
_PORT_ONLY = re.compile(r"\d*")
_QUOTES = "'\"`"


@dataclass
class Extraction:
    observations: list[dict] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=lambda: {k: 0 for k in KINDS})
    excluded_own_host: int = 0
    yaml_failed: bool = False


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------


def load_rules(root: Path | None = None) -> dict:
    """catalog/observed.yaml with its patterns compiled.

    `rules["forms"][lang][kind]` is a list of `(id, pattern | None, requires | None)`;
    a structural form has no pattern."""
    import yaml

    base = Path(root or c.plugin_root()) / "catalog"
    raw = yaml.safe_load((base / "observed.yaml").read_text(encoding="utf-8"))
    forms: dict[str, dict[str, list]] = {}
    for lang, kinds in (raw.get("forms") or {}).items():
        for kind, entries in (kinds or {}).items():
            if kind not in FORM_KINDS:
                raise c.ThunderstruckError(f"observed.yaml: unknown form kind {kind!r}")
            forms.setdefault(lang, {})[kind] = [
                (e["id"],
                 re.compile(e["pattern"], re.M) if e.get("pattern") else None,
                 re.compile(e["requires"]) if e.get("requires") else None)
                for e in entries]
    stability = yaml.safe_load((base / "stability.yaml").read_text(encoding="utf-8"))
    ex = raw.get("exclude_hosts") or {}
    calls = "|".join(re.escape(s) for s in raw.get("secret_calls") or [])
    return {
        "forms": forms,
        "aliases": dict(stability.get("aliases") or {}),
        "api_name": re.compile(raw["api_name"]),
        "config_env_suffixes": tuple(raw.get("config_env_suffixes") or ()),
        "config_host_key_words": tuple(raw.get("config_host_key_words") or ()),
        "generic_first_labels": frozenset(raw.get("generic_first_labels") or ()),
        "secret_call": re.compile(rf"\b\w*(?:{calls})\s*\(") if calls else None,
        "exclude_exact": frozenset(ex.get("exact") or ()),
        "exclude_suffix": tuple(ex.get("suffix") or ()),
        "exclude_prefix": tuple(ex.get("prefix") or ()),
        "exclude_ipv4_loopback": bool(ex.get("ipv4_loopback")),
    }


def _forms(rules: dict, lang: str) -> dict[str, list]:
    return rules["forms"].get(rules["aliases"].get(lang, lang), {})


def _ids(forms: dict, kind: str) -> set[str]:
    return {f[0] for f in forms.get(kind, [])}


def ref(obs: dict) -> str:
    return f"observed {obs['kind']}:{obs['value']} {obs['file']}:{obs['line']}"


def is_own_host(host: str, own_hosts: list[str]) -> bool:
    """Equal to an own host or a subdomain of one; `*.x` covers subdomains of x only."""
    for entry in own_hosts:
        if entry.startswith("*."):
            if host.endswith(entry[1:]):
                return True
        elif host == entry or host.endswith("." + entry):
            return True
    return False


def _excluded(host: str, rules: dict) -> bool:
    if host in rules["exclude_exact"] or host.endswith(rules["exclude_suffix"]) \
            or host.startswith(rules["exclude_prefix"]):
        return True
    return rules["exclude_ipv4_loopback"] and re.fullmatch(r"127(?:\.\d{1,3}){3}", host) is not None


# --------------------------------------------------------------------------
# shared text helpers
# --------------------------------------------------------------------------


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts += [m.end() for m in re.finditer("\n", text)]
    return starts


def _line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _arg_span(text: str, open_at: int) -> tuple[int, int] | None:
    """The argument list from the `(` at `open_at` to its balancing `)`,
    counting only parentheses outside string literals; None past MAX_ARGS."""
    depth, i, limit = 0, open_at, min(len(text), open_at + MAX_ARGS)
    while i < limit:
        ch = text[i]
        if ch in _QUOTES:
            j = i + 1
            while j < limit and text[j] != ch:
                if text[j] == "\\":
                    j += 1
                elif ch != "`" and text[j] == "\n":
                    break
                j += 1
            i = j + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return open_at, i + 1
        i += 1
    return None


# --------------------------------------------------------------------------
# hosts (§2.1)
# --------------------------------------------------------------------------


def _url_host(token: str) -> tuple[str, bool] | None:
    """(host, has_path) for the text after `://`. Userinfo is skipped and never kept.

    A password may itself hold `@` or `/` (`u:p@ss/w@db.internal`): when the
    authority has a `:` followed by anything but a port, userinfo runs to the
    token's last `@`."""
    slash = token.find("/")
    head = token if slash < 0 else token[:slash]
    last_at = token.rfind("@")
    colon = head.find(":")
    if last_at >= 0 and colon >= 0 \
            and not _PORT_ONLY.fullmatch(head[colon + 1:].split("@", 1)[0].split("/", 1)[0]) \
            and "@" in token[colon:]:
        rest = token[last_at + 1:]
    elif "@" in head:
        rest = token[head.rfind("@") + 1:]
    else:
        rest = token
    end = _HOST_END.search(rest)
    host = rest if end is None else rest[:end.start()]
    after = "" if end is None else rest[end.start():]
    after = re.sub(r"^:\d*", "", after)
    has_path = after.startswith("/") and len(re.split(r"[?#]", after, maxsplit=1)[0]) > 1
    return host, has_path


def _normal_host(host: str) -> str:
    return host.lower().rstrip(".")


def _accept_host(raw: str, rules: dict, own_hosts: list[str], ex: Extraction) -> str | None:
    if TEMPLATED.search(raw):
        ex.dropped["host"] += 1
        return None
    host = _normal_host(raw)
    if not host or len(host) > MAX_HOST_LEN or not HOST_RE.match(host):
        ex.dropped["host"] += 1
        return None
    if _excluded(host, rules):
        return None
    if is_own_host(host, own_hosts):
        ex.excluded_own_host += 1
        return None
    return host


def _code_hosts(blanked: str, forms: dict, rules: dict, own_hosts: list[str],
                starts: list[int], ex: Extraction, add) -> None:
    request, response = forms.get("request", []), forms.get("response", [])
    if not request or not response:
        return
    if not any(p.search(blanked) for _, p, _ in request if p) \
            or not any(p.search(blanked) for _, p, _ in response if p):
        return
    for m in _SCHEME.finditer(blanked):
        tail = blanked[m.end():]
        stop = _TOKEN_END.search(tail)
        token = tail if stop is None else tail[:stop.start()]
        host, has_path = _url_host(token)
        if not has_path:
            begin = m.start()
            if begin > 0 and blanked[begin - 1] in _QUOTES:
                begin -= 1
            if not rules["api_name"].search(blanked[max(0, begin - 60):begin]):
                continue
        accepted = _accept_host(host, rules, own_hosts, ex)
        if accepted:
            add("host", accepted, _line_of(starts, m.start()))


def _config_hosts(blanked: str, rules: dict, own_hosts: list[str], ex: Extraction, add) -> None:
    """config.host.key: a URL value under a key whose last segment names an address."""
    words = rules["config_host_key_words"]
    for n, line in enumerate(blanked.split("\n"), 1):
        m = re.match(r"^\s*-?\s*([\w.-]+)\s*[:=]\s*['\"]?([a-z][a-z0-9+.-]{1,15})://(\S*)", line)
        if not m:
            continue
        last = re.split(r"[.]", m.group(1))[-1].lower()
        if not any(w in last for w in words):
            continue
        token = _TOKEN_END.split(m.group(3), maxsplit=1)[0]
        accepted = _accept_host(_url_host(token)[0], rules, own_hosts, ex)
        if accepted:
            add("host", accepted, n)


# --------------------------------------------------------------------------
# YAML structure
# --------------------------------------------------------------------------


def _scalar(node) -> str | None:
    import yaml

    return node.value if isinstance(node, yaml.ScalarNode) else None


def _get(node, key: str):
    import yaml

    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if _scalar(k) == key:
                return v
    return None


def _seq(node) -> list:
    import yaml

    return list(node.value) if isinstance(node, yaml.SequenceNode) else []


def _walk(node):
    import yaml

    yield node
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            yield from _walk(k)
            yield from _walk(v)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _walk(item)


def _line(node, offset: int = 0) -> int:
    return node.start_mark.line + 1 + offset


def _yaml_docs(text: str) -> list | None:
    import yaml

    try:
        return [d for d in yaml.compose_all(text, Loader=yaml.SafeLoader) if d is not None]
    except yaml.YAMLError:
        return None


VAULT_ANNOTATION = "vault.hashicorp.com/agent-inject-secret-"


def _yaml_secrets(docs: list, add_secret) -> None:
    import yaml

    for doc in docs:
        kind = _scalar(_get(doc, "kind")) or ""
        spec = _get(doc, "spec")
        if kind == "ExternalSecret":
            for item in _seq(_get(spec, "data")):
                key = _get(_get(item, "remoteRef"), "key")
                if _scalar(key) is not None:
                    add_secret(key.value, _line(key))
            for item in _seq(_get(spec, "dataFrom")):
                key = _get(_get(item, "extract"), "key")
                if _scalar(key) is not None:
                    add_secret(key.value, _line(key))
        if kind == "SecretProviderClass":
            _csi(spec, add_secret)
        for node in _walk(doc):
            if isinstance(node, yaml.MappingNode):
                for k, v in node.value:
                    name = _scalar(k)
                    if name and name.startswith(VAULT_ANNOTATION) and _scalar(v) is not None:
                        add_secret(v.value, _line(v))


def _csi(spec, add_secret, offset: int = 0) -> None:
    import yaml

    for node in _walk(spec) if spec is not None else []:
        if not isinstance(node, yaml.MappingNode):
            continue
        for k, v in node.value:
            name, value = _scalar(k), _scalar(v)
            if value is None:
                continue
            if name in ("objectName", "secretPath"):
                add_secret(value, _line(v, offset))
            elif name == "objects" and v.style == "|":
                inner = _yaml_docs(value)
                for doc in inner or []:
                    _csi(doc, add_secret, offset + _line(v))


# --------------------------------------------------------------------------
# secrets in code (§2.3)
# --------------------------------------------------------------------------

_FIRST_LITERAL = re.compile(r"\(\s*(['\"])([^'\"\n]*)\1")
_NAMED_LITERAL = re.compile(r"\b(?:path\s*=|SecretId\s*:)\s*(['\"])([^'\"\n]*)\1")


def _code_secrets(blanked: str, rules: dict, starts: list[int], add_secret) -> None:
    call = rules["secret_call"]
    if call is None:
        return
    for m in call.finditer(blanked):
        span = _arg_span(blanked, m.end() - 1)
        if span is None:
            continue
        args = blanked[span[0]:span[1]]
        lit = _FIRST_LITERAL.match(args) or _NAMED_LITERAL.search(args)
        if lit:
            add_secret(lit.group(2), _line_of(starts, span[0] + lit.start(2)))


def _secret_shaped(value: str) -> bool:
    return len(value) >= 32 and not re.search(r"[/_-]", value)



# --------------------------------------------------------------------------
# env vars (§2.2)
# --------------------------------------------------------------------------

# A read that is the whole right-hand side of an assignment binds that name.
_BIND_BEFORE = {
    "typescript": re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*$"),
    "python": re.compile(r"^\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=\s*$"),
    "java": re.compile(r"\b[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*=\s*$"),
}
_BIND_AFTER = re.compile(r"^(?:[^;\n]*\))?\s*;?\s*$")
_DESTRUCTURED = re.compile(
    r"^\s*([A-Za-z_$][\w$]*)\s*(?::\s*([A-Za-z_$][\w$]*))?\s*(?:=[\s\S]*)?$")


def call_spans(blanked: str, rules: dict, lang: str) -> list[tuple[int, int]]:
    """Start and end offsets of each shipped request or connect call's argument list."""
    forms = _forms(rules, lang)
    spans: set[tuple[int, int]] = set()
    for kind in ("request", "connect"):
        for _, pattern, requires in forms.get(kind, []):
            for m in pattern.finditer(blanked) if pattern else ():
                span = _arg_span(blanked, m.end() - 1)
                if span and (requires is None or requires.search(blanked, span[0], span[1])):
                    spans.add(span)
    return sorted(spans)


def _split_top(text: str) -> list[str]:
    parts, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def _reads(blanked: str, forms: dict, lang: str) -> tuple[list[tuple[str, int]],
                                                          list[tuple[str, str, int]]]:
    """(direct reads as (NAME, offset), bindings as (NAME, bound name, end offset))."""
    direct: list[tuple[str, int]] = []
    bound: list[tuple[str, str, int]] = []
    before = _BIND_BEFORE.get(lang)
    for form_id, pattern, _ in forms.get("read", []):
        for m in pattern.finditer(blanked) if pattern else ():
            if form_id.endswith(".destructure"):
                for item in _split_top(m.group(1)):
                    d = _DESTRUCTURED.match(item)
                    if d and not item.strip().startswith("..."):
                        bound.append((d.group(1), d.group(2) or d.group(1), m.end()))
                continue
            direct.append((m.group(1), m.start()))
            line_start = blanked.rfind("\n", 0, m.start()) + 1
            line_end = blanked.find("\n", m.end())
            line_end = len(blanked) if line_end < 0 else line_end
            b = before.search(blanked[line_start:m.start()]) if before else None
            if b and _BIND_AFTER.match(blanked[m.end():line_end]):
                bound.append((m.group(1), b.group(1), m.end()))
    return direct, bound


def _code_env(blanked: str, rules: dict, lang: str, starts: list[int], add_env) -> None:
    forms = _forms(rules, lang)
    if not forms.get("read"):
        return
    spans = call_spans(blanked, rules, lang)
    if not spans:
        return
    direct, bound = _reads(blanked, forms, lang)
    for name, offset in direct:
        if any(a <= offset < b for a, b in spans):
            add_env(name, _line_of(starts, offset))
    for name, var, after in bound:
        use = re.compile(rf"(?<![\w$.]){re.escape(var)}(?![\w$])")
        for a, b in spans:
            if b <= after:
                continue
            for m in use.finditer(blanked, max(a, after), b):
                add_env(name, _line_of(starts, m.start()))


def _is_address_name(name: str, rules: dict) -> bool:
    return name.endswith(rules["config_env_suffixes"])


def _config_env(text: str, blanked: str, docs: list | None, rules: dict, lang: str,
                starts: list[int], add_env) -> None:
    import yaml

    for form_id, pattern, _ in _forms(rules, lang).get("config", []):
        if form_id == "config.env.k8s-name":
            for doc in docs or []:
                for node in _walk(doc):
                    if not isinstance(node, yaml.MappingNode):
                        continue
                    for key in ("containers", "initContainers"):
                        for container in _seq(_get(node, key)):
                            for item in _seq(_get(container, "env")):
                                name = _get(item, "name")
                                if _scalar(name) is not None and _is_address_name(name.value, rules):
                                    add_env(name.value, _line(name))
        elif form_id == "config.env.spring-value" and pattern:
            for m in pattern.finditer(blanked):
                name = re.sub(r"[.-]", "_", m.group(1)).upper()
                if _is_address_name(name, rules):
                    add_env(name, _line_of(starts, m.start()))
        elif form_id.startswith("config.env.") and pattern:
            for m in pattern.finditer(blanked):
                if _is_address_name(m.group(1), rules):
                    add_env(m.group(1), _line_of(starts, m.start()))

# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------


def observe_text(text: str, lang: str, rel: str, rules: dict,
                 own_hosts: list[str]) -> Extraction:
    """Every observation in one file's text, in file order. Values that fail
    their kind's pattern are counted in `dropped` and never returned."""
    ex = Extraction()
    forms = _forms(rules, lang)
    blanked = c.strip_comments(text, lang)
    starts = _line_starts(blanked)
    seen: set[tuple[str, str, int]] = set()

    def add(kind: str, value: str, line: int) -> None:
        if (kind, value, line) not in seen:
            seen.add((kind, value, line))
            ex.observations.append({"kind": kind, "value": value, "file": rel, "line": line})

    def add_secret(value: str, line: int) -> None:
        value = str(value).strip()
        if not SECRET_RE.match(value) or _secret_shaped(value) or TEMPLATED.search(value):
            ex.dropped["secret"] += 1
            return
        add("secret", value, line)

    def add_env(value: str, line: int) -> None:
        if not ENV_RE.match(value):
            ex.dropped["env"] += 1
            return
        add("env", value, line)

    if lang in ("yaml", "properties"):
        if "config.host.key" in _ids(forms, "config"):
            _config_hosts(blanked, rules, own_hosts, ex, add)
        docs = _yaml_docs(text) if lang == "yaml" else None
        _config_env(text, blanked, docs, rules, lang, starts, add_env)
        if lang == "yaml":
            if docs is None:
                ex.yaml_failed = True
            else:
                _yaml_secrets(docs, add_secret)
                if "mesh.service-entry" in _ids(forms, "mesh"):
                    for doc in docs:
                        if _scalar(_get(doc, "kind")) == "ServiceEntry":
                            for h in _seq(_get(_get(doc, "spec"), "hosts")):
                                accepted = _scalar(h) is not None and \
                                    _accept_host(h.value, rules, own_hosts, ex)
                                if accepted:
                                    add("host", accepted, _line(h))
    else:
        _code_hosts(blanked, forms, rules, own_hosts, starts, ex, add)
        _code_secrets(blanked, rules, starts, add_secret)
        _code_env(blanked, rules, lang, starts, add_env)
        _config_env(text, blanked, None, rules, lang, starts, add_env)
    ex.observations.sort(key=lambda o: (o["line"], o["kind"], o["value"]))
    return ex


# --------------------------------------------------------------------------
# the [observed] profile table (§4)
# --------------------------------------------------------------------------

DEFAULT_OWN_HOSTS_ANNOTATION = "thunderstruck.io/own-hosts"
_MAP_KEYS = {"hosts": "host", "env": "env", "secrets": "secret"}
_ANNOTATION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./_-]{0,252}\Z")


def _valid_value(kind: str, value: Any, wildcard: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    if kind == "host":
        host = value.strip().lower().rstrip(".")
        bare = host[2:] if wildcard and host.startswith("*.") else host
        return host if len(bare) <= MAX_HOST_LEN and HOST_RE.match(bare) else None
    if kind == "env":
        return value if ENV_RE.match(value) else None
    return value if SECRET_RE.match(value) else None


def load_config(profile: dict) -> tuple[dict, list[str]]:
    """The `[observed]` table, validated like `[[suppress]]`: an invalid entry is
    dropped with one warning naming it, and the rest still runs."""
    from context_extract import ENTITY_REF

    section = profile.get("observed") if isinstance(profile, dict) else None
    section = section if isinstance(section, dict) else {}
    warnings: list[str] = []
    cfg: dict[str, Any] = {"own_hosts_annotation": DEFAULT_OWN_HOSTS_ANNOTATION,
                           "map": [], "ignore": []}
    if "own_hosts_annotation" in section:
        value = section["own_hosts_annotation"]
        if isinstance(value, str) and _ANNOTATION_KEY.match(value):
            cfg["own_hosts_annotation"] = value
        else:
            warnings.append("[observed] own_hosts_annotation must be an annotation key; "
                            f"using {DEFAULT_OWN_HOSTS_ANNOTATION}")
    seen: set[tuple[str, str]] = set()
    raw_map = section.get("map", [])
    for i, entry in enumerate(raw_map if isinstance(raw_map, list) else [], 1):
        where = f"[[observed.map]] entry {i}"
        problem = None
        values: dict[str, list[str]] = {"host": [], "env": [], "secret": []}
        if not isinstance(entry, dict):
            problem = "must be a table"
        elif not isinstance(entry.get("entity"), str) or not ENTITY_REF.match(entry["entity"]):
            problem = "entity must look like kind:namespace/name"
        elif set(entry) - {"entity", *_MAP_KEYS}:
            problem = f"accepts only entity, {', '.join(_MAP_KEYS)}"
        else:
            for key, kind in _MAP_KEYS.items():
                raw = entry.get(key, [])
                if not isinstance(raw, list):
                    problem = f"{key} must be a list"
                    break
                for value in raw:
                    good = _valid_value(kind, value)
                    if good is None:
                        problem = f"{key} holds a value that is not a valid {kind}"
                        break
                    if (kind, good) in seen:
                        problem = f"{key} repeats a value another map entry names"
                        break
                    values[kind].append(good)
                if problem:
                    break
            if not problem and not any(values.values()):
                problem = "names no hosts, env or secrets"
        if problem:
            warnings.append(f"{where} ignored: {problem}")
            continue
        seen |= {(k, v) for k, vs in values.items() for v in vs}
        cfg["map"].append({"entity": entry["entity"],
                           **{k: sorted(set(v)) for k, v in values.items()}})
    raw_ignore = section.get("ignore", [])
    for i, entry in enumerate(raw_ignore if isinstance(raw_ignore, list) else [], 1):
        where = f"[[observed.ignore]] entry {i}"
        kinds = [k for k in KINDS if isinstance(entry, dict) and k in entry]
        problem = None
        if not isinstance(entry, dict):
            problem = "must be a table"
        elif len(kinds) != 1:
            problem = "must name exactly one of host, env, secret"
        elif set(entry) - {kinds[0], "reason"}:
            problem = f"accepts only {kinds[0]} and reason"
        elif not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            problem = "needs a non-empty reason"
        if problem is None:
            value = _valid_value(kinds[0], entry[kinds[0]], wildcard=kinds[0] == "host")
            if value is None:
                problem = f"{kinds[0]} is not a valid {kinds[0]}"
        if problem:
            warnings.append(f"{where} ignored: {problem}")
            continue
        cfg["ignore"].append({"kind": kinds[0], "value": value,
                              "reason": " ".join(entry["reason"].split())})
    return cfg, warnings


def map_hash(cfg: dict) -> str:
    return c.sha256_text(_canonical({"map": cfg["map"], "ignore": cfg["ignore"]}))


def _canonical(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------
# matching (§3)
# --------------------------------------------------------------------------


def match_name(kind: str, value: str, rules: dict) -> str | None:
    """The name §3 rule 3 compares with a neighbour's, or None (a generic first label)."""
    if kind == "host":
        label = value.split(".", 1)[0]
        return None if label in rules["generic_first_labels"] else label
    if kind == "env":
        for suffix in sorted(rules["config_env_suffixes"], key=len, reverse=True):
            if value.endswith(suffix) and len(value) > len(suffix):
                value = value[:-len(suffix)]
                break
        return value.lower().replace("_", "-")
    return value.rsplit("/", 1)[-1].lower()


def _ignore_rule(kind: str, value: str, cfg: dict) -> dict | None:
    for rule in cfg["ignore"]:
        if rule["kind"] != kind:
            continue
        pattern = rule["value"]
        if pattern == value or (kind == "host" and pattern.startswith("*.")
                                and value.endswith(pattern[1:])):
            return rule
    return None


def _rule_name(rule: dict) -> str:
    return f"{rule['kind']} {rule['value']}"


def resolve(observations: list[dict], edges: list[dict], cfg: dict, rules: dict) -> dict:
    """Resolve each distinct (kind, value) once, then classify the documented
    outbound edges no observation reached (§3). Sorted per §5."""
    counts: dict[tuple[str, str], int] = {}
    for o in observations:
        key = (o["kind"], o["value"])
        counts[key] = counts.get(key, 0) + 1
    mapped = {(kind, v): entry["entity"] for entry in cfg["map"]
              for kind in KINDS for v in entry[kind]}
    map_entities = {entry["entity"] for entry in cfg["map"]}
    outbound: dict[str, list[str]] = {}
    inbound: dict[str, list[str]] = {}
    for e in edges:
        (outbound if e["direction"] == "outbound" else inbound) \
            .setdefault(e["neighbour"], []).append(e["ref"])
    by_name: dict[str, set[str]] = {}
    for entity in set(outbound) | set(inbound):
        by_name.setdefault(entity.rsplit("/", 1)[-1].lower(), set()).add(entity)

    hits = {_rule_name(r): 0 for r in cfg["ignore"]}
    resolutions: list[dict] = []
    reached: set[str] = set()
    candidates: set[str] = set()
    for (kind, value), n in sorted(counts.items()):
        res: dict[str, Any] = {"kind": kind, "value": value, "resolution": "unmatched",
                               "entity": None, "edge": None, "via": None, "occurrences": n}
        rule = _ignore_rule(kind, value, cfg)
        entity = via = None
        if rule is not None:
            hits[_rule_name(rule)] += n
            res.update(resolution="ignored", rule=_rule_name(rule), reason=rule["reason"])
        elif (kind, value) in mapped:
            entity, via = mapped[(kind, value)], "map"
        else:
            name = match_name(kind, value, rules)
            found = sorted(by_name.get(name, ())) if name else []
            if len(found) == 1:
                entity, via = found[0], "name"
            elif len(found) > 1:
                refs = sorted(r for ent in found
                              for r in outbound.get(ent, []) + inbound.get(ent, []))
                candidates |= set(refs)
                res.update(resolution="ambiguous", candidates=refs)
        if entity is not None:
            res.update(entity=entity, via=via)
            if entity in outbound:
                res.update(resolution="documented", edge=sorted(outbound[entity])[0])
                reached |= set(outbound[entity])
            elif entity in inbound:
                res.update(resolution="dependent_only", edge=sorted(inbound[entity])[0])
            else:
                res["resolution"] = "mapped_undocumented"
        resolutions.append(res)

    not_observed: list[str] = []
    no_mapping: list[str] = []
    for entity, refs in outbound.items():
        for r in refs:
            if r in reached or r in candidates:
                continue
            (not_observed if entity in map_entities else no_mapping).append(r)
    ignored = sorted(({"rule": _rule_name(r), "reason": r["reason"], "hits": hits[_rule_name(r)]}
                      for r in cfg["ignore"]), key=lambda x: x["rule"])
    return {"resolutions": resolutions, "not_observed": sorted(not_observed),
            "no_mapping": sorted(no_mapping), "ignored": ignored}
