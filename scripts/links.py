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
import subprocess
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
# provider -> a file's change history up to a commit; custom templates have none
HISTORY = {
    "github": "{base}/commits/{sha}/{path}",
    "gitlab": "{base}/-/commits/{sha}/{path}",
    "bitbucket": "{base}/history-node/{sha}/{path}",
}
MAX_NAMED = 5
# GitHub and GitLab render these and ignore line anchors unless ?plain=1.
PLAIN_PROVIDERS = frozenset({"github", "gitlab"})
PLAIN_EXTS = frozenset({".md", ".markdown", ".mdown", ".mkd", ".rst", ".adoc",
                        ".asciidoc", ".org", ".textile", ".rdoc", ".ipynb"})

PLACEHOLDERS = frozenset({"base", "sha", "path", "start", "end"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_SCP = re.compile(r"^(?:[^@/\s]+@)?(?P<host>[A-Za-z0-9.-]{2,}):(?P<path>[^/\\].*)$")
_URL_SCHEMES = frozenset({"http", "https", "ssh", "git", "git+ssh", "ssh+git"})
# A web base goes verbatim into Markdown link targets, so it is held to a
# strict set: nothing that could close the link, start a fragment or query,
# or be read as a template placeholder.
_SAFE_HOST = re.compile(r"^[A-Za-z0-9.-]+(?::\d+)?$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._~%/+-]+$")
# A template's literal text lands in link targets, some inside table cells:
# whitespace, controls and these would end the link or split the row.
_LINK_BREAKERS = frozenset("|()<>[]`\\\"")
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
    if not path or not _SAFE_PATH.match(path) or not _SAFE_HOST.match(netloc):
        return None
    return Remote(host=host, base=f"{web}://{netloc}/{path}")


def detect_provider(host: str) -> str | None:
    """Exact hosts only — a guessed provider yields links that silently 404."""
    return KNOWN_HOSTS.get((host or "").lower())


def valid_base_url(value: str) -> bool:
    """An http(s) web base with no credentials and nothing that breaks a link."""
    try:
        parts = urlsplit(value)
        parts.port
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False
    if parts.username or parts.password or parts.query or parts.fragment:
        return False
    path = parts.path.strip("/")
    return bool(_SAFE_HOST.match(parts.netloc)) and (not path or bool(_SAFE_PATH.match(path)))


def encode_path(path: str) -> str:
    """Normalise like the validator, then percent-encode each segment."""
    return "/".join(quote(seg, safe="") for seg in c.ref_path(path).split("/"))


def parse_lines(value, total: int | None) -> tuple[int, int] | None:
    """A finding's `location.lines` as (start, end), or None if unusable.

    validate.py rejects an unusable range; this still parses it on its own, so
    a tampered or older findings file can't produce a wrong anchor: an int or
    "a" / "a-b", inside the file. Anything else links the whole file.
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


def template_error(template: str, allowed=PLACEHOLDERS, required=()) -> str | None:
    """None when the template is usable, else what is wrong with it."""
    names = _PLACEHOLDER.findall(template)
    for name in names:
        if name not in allowed:
            return "{" + name + "}"
    rest = _PLACEHOLDER.sub("", template)
    if "{" in rest or "}" in rest:
        return "an unbalanced brace"
    for ch in template:
        if ch in _LINK_BREAKERS or ch.isspace() or not ch.isprintable():
            return f"the character {ch!r}, which cannot appear in a link"
    for name in required:
        if name not in names:
            return "no {" + name + "}"
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
    history_tpl: str | None = None

    @classmethod
    def for_provider(cls, provider: str, *, base: str, sha: str, **kw) -> "LinkContext":
        rng, line, whole, commit = TEMPLATES[provider]
        return cls(base=base, sha=sha, code_range=rng, code_line=line, code_file=whole,
                   commit_tpl=commit, provider=provider, history_tpl=HISTORY[provider], **kw)

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

    def history(self, path: str) -> str | None:
        """The file's change history up to the scanned commit, or None."""
        rel = c.ref_path(path)
        if not self.history_tpl or not rel or rel in self.unlinked:
            return None
        return _fill(self.history_tpl, {"base": self.base, "sha": self.sha,
                                        "path": encode_path(rel)})

    def commit(self, full_sha: str) -> str:
        return _fill(self.commit_tpl, {"base": self.base, "sha": full_sha})


def named(items, limit: int = MAX_NAMED) -> str:
    """The first `limit` items, then how many more: a warning never floods the report."""
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f" … and {len(items) - limit} more" if len(items) > limit else "")


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[name.rfind("."):].lower() if "." in name else ""


# --------------------------------------------------------------------------
# config and git — every linking git call lives below
# --------------------------------------------------------------------------

NOT_LINKED = "references are not linked: "
CONFIG_KEYS = frozenset({"enabled", "remote", "provider", "base_url",
                         "code_template", "commit_template"})
GIT_TIMEOUT = 30
PATHS_PER_CALL = 100
CHARS_PER_CALL = 8000
_HEX = re.compile(r"[0-9a-fA-F]{4,40}")
_FULL_SHA = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class LinkConfig:
    remote: str | None = None
    provider: str | None = None
    base_url: str | None = None
    code_template: str | None = None
    commit_template: str | None = None


@dataclass(frozen=True)
class LinkResult:
    ctx: LinkContext | None
    commits: dict[str, str]        # cited commit token -> full SHA
    warnings: list[str]


def config_from_profile(profile) -> tuple[LinkConfig | None, list[str]]:
    """Validate [links]. Disabled -> (None, []); invalid -> (None, [one warning])."""
    section = profile.get("links") if isinstance(profile, dict) else None
    if section is None:
        return LinkConfig(), []

    def bad(reason: str) -> tuple[None, list[str]]:
        return None, [f"{NOT_LINKED}[links] {reason} in .thunderstruck.toml"]

    if not isinstance(section, dict):
        return bad("must be a table")
    unknown = sorted(set(section) - CONFIG_KEYS)
    if unknown:
        return bad(f"has unknown key {unknown[0]!r}")
    enabled = section.get("enabled", True)
    if not isinstance(enabled, bool):
        return bad("enabled must be true or false")
    if not enabled:
        return None, []
    for key in CONFIG_KEYS - {"enabled"}:
        if key in section and not isinstance(section[key], str):
            return bad(f"{key} must be a string")
    provider = section.get("provider")
    if provider is not None and provider not in TEMPLATES:
        return bad(f"provider must be one of {', '.join(sorted(TEMPLATES))}")
    base_url = section.get("base_url")
    if base_url is not None and not valid_base_url(base_url):
        return bad("base_url must be a plain http(s) URL, with no credentials, query "
                   "or fragment")
    code_t, commit_t = section.get("code_template"), section.get("commit_template")
    if (code_t is None) != (commit_t is None):
        return bad("code_template and commit_template must be set together")
    rules = (("code_template", code_t, PLACEHOLDERS, ("sha", "path")),
             ("commit_template", commit_t, frozenset({"base", "sha"}), ("sha",)))
    for key, tpl, allowed, required in rules:
        if tpl is not None and (err := template_error(tpl, allowed, required)):
            if err.startswith("the character"):
                return bad(f"{key} has {err}")
            return bad(f"{key} has {err}; allowed: "
                       + " ".join("{" + p + "}" for p in sorted(allowed)))
    return LinkConfig(remote=section.get("remote"), provider=provider,
                      base_url=base_url.rstrip("/") if base_url else None,
                      code_template=code_t, commit_template=commit_t), []


def link_context(repo, profile, scanned_sha: str, cited_paths, cited_commits) -> LinkResult:
    """Everything the report needs to link refs, or None plus the reason.

    Never raises for a git problem: the report must render either way.
    """
    cfg, warnings = config_from_profile(profile)
    if cfg is None:
        return LinkResult(None, {}, warnings)
    if not _FULL_SHA.fullmatch(scanned_sha or ""):
        return LinkResult(None, {}, [f"{NOT_LINKED}the scanned commit is unknown"])
    try:
        return _resolve(repo, cfg, scanned_sha, cited_paths, cited_commits)
    except subprocess.TimeoutExpired as exc:
        return LinkResult(None, {}, [f"{NOT_LINKED}git {_verb(exc.cmd)} did not answer "
                                     f"within {GIT_TIMEOUT}s"])
    except (c.ThunderstruckError, OSError):
        # git's own message can carry local paths and full command lines; the
        # report is shareable, so it gets a fixed reason instead
        return LinkResult(None, {}, [f"{NOT_LINKED}a git command failed in this repository"])


def _verb(cmd) -> str:
    """The subcommand of a `git -C <repo> ...` argv, for a warning with no path."""
    args = list(cmd or [])[3:]
    return next((a for a in args if isinstance(a, str) and not a.startswith("-")), "command")


def _git(repo, *args: str, check: bool = True) -> str:
    return c.git(repo, *args, check=check, timeout=GIT_TIMEOUT)


def _resolve(repo, cfg: LinkConfig, sha: str, cited_paths, cited_commits) -> LinkResult:
    warnings: list[str] = []

    def stop(reason: str) -> LinkResult:
        return LinkResult(None, {}, warnings + [NOT_LINKED + reason])

    remotes = _git(repo, "remote").split()
    name: str | None = None
    if cfg.remote:
        if cfg.remote in remotes:
            name = cfg.remote
        elif not cfg.base_url:
            return stop(f"remote {cfg.remote!r} named in [links] does not exist")
        else:
            warnings.append(f"remote {cfg.remote!r} named in [links] does not exist; "
                            "links use base_url and their push state is not checked")
    elif "origin" in remotes:
        name = "origin"
    elif len(remotes) == 1:
        name = remotes[0]

    if cfg.base_url:
        base, host = cfg.base_url, (urlsplit(cfg.base_url).hostname or "")
    elif name:
        remote = parse_remote(_git(repo, "remote", "get-url", name).strip())
        if remote is None:
            return stop(f"git remote {name!r} has no web address; set base_url in [links]")
        base, host = remote.base, remote.host
    else:
        return stop("no git remote to link to; set remote or base_url in [links] "
                    "in .thunderstruck.toml")

    provider = None
    if not cfg.code_template:
        provider = cfg.provider or detect_provider(host)
        if provider is None:
            return stop(f"host {host} is not recognised; set provider (and base_url "
                        f"if {host} is an SSH alias) in [links] in .thunderstruck.toml")

    paths = sorted({p for p in (c.ref_path(x) for x in cited_paths) if p})
    escaping = {p for p in paths if _escapes(p)}
    unlinked = escaping | _stale_paths(repo, sha, [p for p in paths if p not in escaping])
    if unlinked:
        warnings.append(f"{len(unlinked)} file(s) differ from the scanned commit "
                        f"{sha[:7]} or are not in it, and are not linked: "
                        + named(sorted(unlinked)))

    commits: dict[str, str] = {}
    for token in sorted({t for t in cited_commits if _HEX.fullmatch(t or "")}):
        full = _git(repo, "rev-parse", "--verify", "--quiet", f"{token}^{{commit}}",
                    check=False).strip()
        if _FULL_SHA.fullmatch(full):
            commits[token] = full

    if name:
        unpushed = [s for s in [sha, *sorted(set(commits.values()) - {sha})]
                    if not _on_remote(repo, name, s)]
        if unpushed:
            shown = ", ".join(s[:7] for s in unpushed[:5]) + (", …" if len(unpushed) > 5 else "")
            warnings.append(f"{len(unpushed)} linked commit(s) are on no branch of {name} "
                            f"known locally ({shown}; normal in a detached or shallow CI "
                            "checkout); their links resolve once pushed")

    common = {"base": base, "sha": sha, "remote": name, "unlinked": frozenset(unlinked)}
    if cfg.code_template:
        ctx = LinkContext.for_templates(cfg.code_template, cfg.commit_template, **common)
    else:
        ctx = LinkContext.for_provider(provider, **common)
    return LinkResult(ctx, commits, warnings)


def _stale_paths(repo, sha: str, paths: list[str]) -> set[str]:
    """Paths (cited or listed) whose content at `sha` is not what is on disk now.

    Paths go to git in chunks, bounded by count and by length: a large --top
    must not overflow a command line (about 32K characters on Windows) and
    take every link down with it.
    """
    stale: set[str] = set()
    for chunk in _chunks(paths):
        stale |= _stale_chunk(repo, sha, chunk)
    return stale


def _chunks(paths: list[str]):
    chunk: list[str] = []
    size = 0
    for p in paths:
        if chunk and (len(chunk) >= PATHS_PER_CALL or size + len(p) + 1 > CHARS_PER_CALL):
            yield chunk
            chunk, size = [], 0
        chunk.append(p)
        size += len(p) + 1
    if chunk:
        yield chunk


def _stale_chunk(repo, sha: str, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    listed = _git(repo, "--literal-pathspecs", "ls-tree", "-z", "--full-tree", sha, "--", *paths)
    regular: set[str] = set()
    for entry in listed.split("\0"):
        meta, _, path = entry.partition("\t")
        # 100644/100755 are files; 120000 symlinks and 160000 submodules are not
        if path and meta.startswith("100"):
            regular.add(path)
    changed = set(filter(None, _git(repo, "--literal-pathspecs", "diff", "--name-only",
                                     "-z", sha, "--", *paths).split("\0")))
    # diff trusts the index; a file flagged assume-unchanged (lowercase tag) or
    # skip-worktree (S) can differ on disk without diff noticing
    for entry in _git(repo, "--literal-pathspecs", "ls-files", "-v", "-z", "--",
                      *paths).split("\0"):
        tag, _, path = entry.partition(" ")
        if path and (tag.islower() or tag == "S"):
            changed.add(path)
    return {p for p in paths if p not in regular or p in changed}


def _escapes(path: str) -> bool:
    """True for a path that is absolute or climbs out with '..'."""
    return path.startswith("/") or ".." in path.split("/")


def _on_remote(repo, remote: str, sha: str) -> bool:
    refs = _git(repo, "branch", "-r", "--contains", sha, "--format=%(refname)", check=False)
    return any(line.startswith(f"refs/remotes/{remote}/") for line in refs.splitlines())
