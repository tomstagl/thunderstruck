"""Web permalinks for evidence refs the validator has already resolved.

A URL is built from three things only: git (the remote, the scanned tree,
commit ids), the repo profile's [links] table, and a ref that validate.py
resolved. Never from model output, never from repository text. Userinfo in a
remote (tokens, usernames) is dropped at parse time and cannot reach output.

Every link is pinned to the scanned commit, and a file that differs from that
commit in any way is left unlinked: a link that opens the wrong lines is worse
than no link.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

import _common as c

KNOWN_HOSTS = {"github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket"}

# provider -> (code range, code single line, whole file, commit)
TEMPLATES = {
    "github": ("{base}/blob/{sha}/{path}#L{start}-L{end}",
               "{base}/blob/{sha}/{path}#L{start}",
               "{base}/blob/{sha}/{path}",
               "{base}/commit/{sha}"),
    "gitlab": ("{base}/-/blob/{sha}/{path}#L{start}-{end}",
               "{base}/-/blob/{sha}/{path}#L{start}",
               "{base}/-/blob/{sha}/{path}",
               "{base}/-/commit/{sha}"),
    "bitbucket": ("{base}/src/{sha}/{path}#lines-{start}:{end}",
                  "{base}/src/{sha}/{path}#lines-{start}",
                  "{base}/src/{sha}/{path}",
                  "{base}/commits/{sha}"),
}
# GitHub and GitLab render these and ignore line anchors unless ?plain=1.
PLAIN_PROVIDERS = frozenset({"github", "gitlab"})
PLAIN_EXTS = frozenset({".md", ".markdown", ".mdown", ".mkd", ".rst", ".adoc",
                        ".asciidoc", ".org", ".textile", ".rdoc", ".ipynb"})

PLACEHOLDERS = frozenset({"base", "sha", "path", "start", "end"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_SCP = re.compile(r"^(?:[^@/\s]+@)?(?P<host>[A-Za-z0-9.-]{2,}):(?P<path>[^/\\].*)$")
_URL_SCHEMES = frozenset({"http", "https", "ssh", "git", "git+ssh", "ssh+git"})
_UNSAFE_IN_BASE = re.compile(r"[{}#?\s]")
_LINES = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*$")


@dataclass(frozen=True)
class Remote:
    host: str
    base: str  # scheme://host[:port]/path — no userinfo, no .git, no trailing /


def parse_remote(url: str) -> Remote | None:
    """The web base of a git remote URL, or None when it has none."""
    url = (url or "").strip()
    if "://" in url:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            return None
        scheme = parts.scheme.lower()
        if scheme not in _URL_SCHEMES or not parts.hostname:
            return None
        host = parts.hostname.lower()
        web = "http" if scheme == "http" else "https"
        # an ssh port is not the web port; an http(s) port is
        netloc = f"{host}:{port}" if port and scheme in {"http", "https"} else host
        path = parts.path
    else:
        m = _SCP.match(url)
        if not m:
            return None
        host = m["host"].lower()
        web, netloc, path = "https", host, m["path"]
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4].rstrip("/")
    if not path or _UNSAFE_IN_BASE.search(path) or _UNSAFE_IN_BASE.search(netloc):
        return None
    return Remote(host=host, base=f"{web}://{netloc}/{path}")


def detect_provider(host: str) -> str | None:
    """Exact hosts only — a guessed provider yields links that silently 404."""
    return KNOWN_HOSTS.get((host or "").lower())


def valid_base_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return (parts.scheme in {"http", "https"} and bool(parts.hostname)
            and not _UNSAFE_IN_BASE.search(value))


def encode_path(path: str) -> str:
    """Normalise like the validator, then percent-encode each segment."""
    return "/".join(quote(seg, safe="") for seg in c.ref_path(path).split("/"))


def parse_lines(value, total: int | None) -> tuple[int, int] | None:
    """A finding's `location.lines` as (start, end), or None if unusable.

    validate.py does not check this field, so it is parsed strictly here: an
    int or "a" / "a-b", inside the file. Anything else links the whole file.
    """
    if total is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        start = end = value
    elif isinstance(value, str) and (m := _LINES.match(value)):
        start = int(m[1])
        end = int(m[2]) if m[2] else start
    else:
        return None
    if 1 <= start <= end <= total:
        return start, end
    return None


def template_error(template: str) -> str | None:
    """None when every placeholder is allowed, else the first offending one."""
    for name in _PLACEHOLDER.findall(template):
        if name not in PLACEHOLDERS:
            return "{" + name + "}"
    if "{" in _PLACEHOLDER.sub("", template) or "}" in _PLACEHOLDER.sub("", template):
        return "unbalanced brace"
    return None


def _fill(template: str, values: dict[str, str]) -> str:
    # one pass: a substituted value is never expanded again
    return _PLACEHOLDER.sub(lambda m: values.get(m[1], m[0]), template)


def _file_template(code_template: str) -> str | None:
    """A user template cut at its fragment, for whole-file links."""
    head = code_template.split("#", 1)[0]
    return None if ("{start}" in head or "{end}" in head) else head


@dataclass(frozen=True)
class LinkContext:
    base: str
    sha: str
    code_range: str
    code_line: str
    code_file: str | None
    commit_tpl: str
    provider: str | None = None
    remote: str | None = None
    unlinked: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def for_provider(cls, provider: str, *, base: str, sha: str, **kw) -> "LinkContext":
        rng, line, whole, commit = TEMPLATES[provider]
        return cls(base=base, sha=sha, code_range=rng, code_line=line, code_file=whole,
                   commit_tpl=commit, provider=provider, **kw)

    @classmethod
    def for_templates(cls, code: str, commit: str, *, base: str, sha: str, **kw) -> "LinkContext":
        return cls(base=base, sha=sha, code_range=code, code_line=code,
                   code_file=_file_template(code), commit_tpl=commit, provider=None, **kw)

    def code(self, path: str, start: int | None = None, end: int | None = None) -> str | None:
        rel = c.ref_path(path)
        if not rel or rel in self.unlinked:
            return None
        if start is None:
            template = self.code_file
            if template is None:
                return None
        else:
            template = self.code_line if end is None or end == start else self.code_range
        url = _fill(template, {
            "base": self.base, "sha": self.sha, "path": encode_path(rel),
            "start": str(start or ""), "end": str(end if end is not None else start or "")})
        if self.provider in PLAIN_PROVIDERS and _ext(rel) in PLAIN_EXTS:
            head, sep, frag = url.partition("#")
            url = f"{head}?plain=1{sep}{frag}"
        return url

    def commit(self, full_sha: str) -> str:
        return _fill(self.commit_tpl, {"base": self.base, "sha": full_sha})


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[name.rfind("."):].lower() if "." in name else ""
