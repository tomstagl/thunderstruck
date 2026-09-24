# Source Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every file:line, detector and commit ref in `report.md` becomes a web permalink pinned to the scanned commit, on GitHub, GitLab and Bitbucket, and on self-hosted hosts through the profile.

**Architecture:** A new stdlib-only module, `scripts/links.py`, parses the git remote and builds URLs. `report.py` builds one `LinkContext` after validation and wraps refs that have already been resolved. The scan, bundles, validator, index and guardrail do not change.

**Tech Stack:** Python ≥ 3.11 stdlib, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-source-links-design.md`. Requirements and AC-1…AC-9 are in GitHub issue #22.

**Branch:** `feat/source-links`. Each task ends in one commit. When it lands, tick the task in the issue's *Implementation progress* checklist.

## Global constraints

- `scripts/links.py` imports stdlib only. All `git` calls go through `_common.git` inside `link_context`, and every other function is pure.
- No change to `signals.py`, `bundle.py`, `validate.py`, `guardrail.py`, the investigator prompt or `index.json`. `test_bundles_are_within_budget_and_deterministic` must pass unchanged on every commit.
- A URL is built only from git config, the profile and a ref already resolved by `validate.py`. A `url` field in a finding JSON is ignored and overwritten.
- `report.py` never fails because of linking. Every failure path ends in plain refs plus a warning.
- `examples/sample-report.md` is regenerated once, in Task 5. Until then, `test_docs_in_sync.py::test_sample_report_*` may fail on intermediate commits; they are the only failures allowed.
- Full suite: `uv run --with pytest --with pyyaml --with lizard pytest tests/ -q`.
- Commit messages are imperative sentences in the repo's style and end with the session's attribution trailer.

---

### Task 1: Parse remotes and build URLs (AC-1, AC-4)

**Files:**
- Create: `scripts/links.py`
- Create: `tests/test_links.py`

- [ ] **Step 1: Write the failing tests**

```python
"""links.py: remote parsing and URL building. Pure, table-driven."""
import pytest

import links as L

GH = "https://github.com/acme/checkout"


@pytest.mark.parametrize("url, host, base", [
    ("https://github.com/acme/checkout.git", "github.com", GH),
    ("https://github.com/acme/checkout/", "github.com", GH),
    ("https://x-access-token:ghs_SECRET@github.com/acme/checkout.git", "github.com", GH),
    ("git@github.com:acme/checkout.git", "github.com", GH),
    ("ssh://git@git.example.com:2222/acme/checkout.git", "git.example.com",
     "https://git.example.com/acme/checkout"),
    ("git://git.example.com/acme/checkout", "git.example.com",
     "https://git.example.com/acme/checkout"),
    ("https://git.example.com:8443/acme/checkout", "git.example.com",
     "https://git.example.com:8443/acme/checkout"),
    ("http://git.example.com/acme/checkout", "git.example.com",
     "http://git.example.com/acme/checkout"),
    ("git@gitlab.com:acme/platform/checkout.git", "gitlab.com",
     "https://gitlab.com/acme/platform/checkout"),
])
def test_parse_remote(url, host, base):
    r = L.parse_remote(url)
    assert (r.host, r.base) == (host, base)


@pytest.mark.parametrize("url", [
    "/srv/git/checkout.git", "file:///srv/git/checkout.git", "../checkout",
    "C:\\repos\\checkout", "https://github.com/", "https://github.com:bad/x", ""])
def test_unlinkable_remotes(url):
    assert L.parse_remote(url) is None


def test_credentials_never_survive():
    r = L.parse_remote("https://bob:ghs_SECRET@github.com/acme/checkout.git")
    assert "bob" not in r.base and "SECRET" not in r.base and "@" not in r.base


@pytest.mark.parametrize("host, provider", [
    ("github.com", "github"), ("gitlab.com", "gitlab"), ("bitbucket.org", "bitbucket"),
    ("gitlab.example.com", None), ("github.example.com", None)])
def test_provider_is_detected_from_exact_hosts_only(host, provider):
    assert L.detect_provider(host) == provider


SHA = "a" * 40


@pytest.mark.parametrize("provider, start, end, url", [
    ("github", 16, 28, f"{GH}/blob/{SHA}/src/x.ts#L16-L28"),
    ("github", 16, None, f"{GH}/blob/{SHA}/src/x.ts#L16"),
    ("gitlab", 16, 28, f"{GH}/-/blob/{SHA}/src/x.ts#L16-28"),
    ("bitbucket", 16, 28, f"{GH}/src/{SHA}/src/x.ts#lines-16:28"),
    ("bitbucket", 16, None, f"{GH}/src/{SHA}/src/x.ts#lines-16"),
])
def test_code_urls(provider, start, end, url):
    ctx = L.LinkContext.for_provider(provider, base=GH, sha=SHA)
    assert ctx.code("src/x.ts", start, end) == url


@pytest.mark.parametrize("provider, url", [
    ("github", f"{GH}/commit/{SHA}"), ("gitlab", f"{GH}/-/commit/{SHA}"),
    ("bitbucket", f"{GH}/commits/{SHA}")])
def test_commit_urls(provider, url):
    assert L.LinkContext.for_provider(provider, base=GH, sha=SHA).commit(SHA) == url


@pytest.mark.parametrize("path, encoded", [
    ("./src/x.ts", "src/x.ts"),
    ("src/my file.ts", "src/my%20file.ts"),
    ("src/a#b?.ts", "src/a%23b%3F.ts"),
    ("src/a](javascript:x).ts", "src/a%5D%28javascript%3Ax%29.ts"),
    ("src/ünï.py", "src/%C3%BCn%C3%AF.py"),
])
def test_paths_are_encoded_per_segment(path, encoded):
    assert L.encode_path(path) == encoded


def test_start_equal_end_is_a_single_line():
    ctx = L.LinkContext.for_provider("github", base=GH, sha=SHA)
    assert ctx.code("x.ts", 5, 5).endswith("#L5")
```

- [ ] **Step 2: Run to confirm they fail**

`uv run --with pytest --with pyyaml --with lizard pytest tests/test_links.py -q` → `ModuleNotFoundError: links`.

- [ ] **Step 3: Implement `scripts/links.py`**

```python
"""Web permalinks for evidence refs the validator has already resolved.

A URL is built from three things only: the git remote, the repo profile's
[links] table, and a ref that validate.py resolved. Never from model output,
never from repository text. Userinfo in a remote (tokens, usernames) is dropped
at parse time and cannot reach any output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

KNOWN_HOSTS = {"github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket"}

# provider -> (code range, code single line, commit)
TEMPLATES = {
    "github": ("{base}/blob/{sha}/{path}#L{start}-L{end}",
               "{base}/blob/{sha}/{path}#L{start}", "{base}/commit/{sha}"),
    "gitlab": ("{base}/-/blob/{sha}/{path}#L{start}-{end}",
               "{base}/-/blob/{sha}/{path}#L{start}", "{base}/-/commit/{sha}"),
    "bitbucket": ("{base}/src/{sha}/{path}#lines-{start}:{end}",
                  "{base}/src/{sha}/{path}#lines-{start}", "{base}/commits/{sha}"),
}
PLACEHOLDERS = frozenset({"base", "sha", "path", "start", "end"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_SCP = re.compile(r"^(?:[^@/\s]+@)?(?P<host>[A-Za-z0-9.-]{2,}):(?P<path>[^/\\].*)$")
_URL_SCHEMES = {"http", "https", "ssh", "git", "git+ssh", "ssh+git"}


@dataclass(frozen=True)
class Remote:
    host: str
    base: str  # web base: scheme://host[:port]/path, no userinfo, no .git


def parse_remote(url: str) -> Remote | None:
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
        netloc = f"{host}:{port}" if port and scheme in {"http", "https"} else host
        path = parts.path
    else:
        m = _SCP.match(url)
        if not m:
            return None
        host, web, path = m["host"].lower(), "https", m["path"]
        netloc = host
    path = path.strip("/")
    path = path[:-4] if path.endswith(".git") else path
    if not path:
        return None
    return Remote(host=host, base=f"{web}://{netloc}/{path}")


def detect_provider(host: str) -> str | None:
    return KNOWN_HOSTS.get(host.lower())


def encode_path(path: str) -> str:
    path = path[2:] if path.startswith("./") else path
    return "/".join(quote(seg, safe="") for seg in path.split("/"))


def template_error(template: str) -> str | None:
    """None when every placeholder is allowed; else the offending one."""
    for name in _PLACEHOLDER.findall(template):
        if name not in PLACEHOLDERS:
            return "{" + name + "}"
    return None


def _fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


@dataclass(frozen=True)
class LinkContext:
    base: str
    sha: str
    code_range: str
    code_line: str
    commit_tpl: str
    provider: str | None = None
    remote: str | None = None
    unlinked: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def for_provider(cls, provider: str, *, base: str, sha: str, **kw) -> "LinkContext":
        rng, line, commit = TEMPLATES[provider]
        return cls(base=base, sha=sha, code_range=rng, code_line=line,
                   commit_tpl=commit, provider=provider, **kw)

    def code(self, path: str, start: int, end: int | None = None) -> str | None:
        path = path[2:] if path.startswith("./") else path
        if path in self.unlinked:
            return None
        single = end is None or end == start
        tpl = self.code_line if single else self.code_range
        return _fill(tpl, base=self.base, sha=self.sha, path=encode_path(path),
                     start=str(start), end=str(start if single else end))

    def commit(self, full_sha: str) -> str:
        return _fill(self.commit_tpl, base=self.base, sha=full_sha)
```

Templates configured by the user have no single-line variant, so `code_line = code_range` with `{end}` filled from `start` (spec §4).

- [ ] **Step 4: Run the tests**

`uv run --with pytest --with pyyaml --with lizard pytest tests/test_links.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/links.py tests/test_links.py
git commit -m "Parse git remotes and build permalinks for GitHub, GitLab and Bitbucket"
```

---

### Task 2: `[links]` profile config and link context (AC-3, AC-5, AC-6)

**Files:**
- Modify: `scripts/links.py` (add `config_from_profile`, `link_context`)
- Modify: `tests/test_links.py`

- [ ] **Step 1: Write the failing tests**

Config tests are pure: they call `config_from_profile(profile) -> (LinkConfig | None, list[str])`:

```python
@pytest.mark.parametrize("links, error_fragment", [
    ({"provider": "gitea"}, "provider"),
    ({"base_url": "javascript:alert(1)"}, "base_url"),
    ({"base_url": "https://git.example.com/{x}"}, "base_url"),
    ({"code_template": "{base}/{sha.__class__}", "commit_template": "{base}"}, "{sha.__class__}"),
    ({"code_template": "{base}/{path}"}, "commit_template"),
    ({"enabled": "yes"}, "enabled"),
])
def test_invalid_config_disables_links_with_one_warning(links, error_fragment):
    cfg, warnings = L.config_from_profile({"links": links})
    assert cfg is None and len(warnings) == 1 and error_fragment in warnings[0]


def test_disabled_is_silent():
    assert L.config_from_profile({"links": {"enabled": False}}) == (None, [])


def test_absent_table_uses_defaults():
    cfg, warnings = L.config_from_profile({})
    assert cfg.remote == "origin" and cfg.provider is None and not warnings
```

`link_context` tests build tiny git repos in `tmp_path` (`git init`, one commit, `git remote add`, `git update-ref refs/remotes/origin/main HEAD`):

- github.com remote + remote-tracking ref → context, no warnings.
- no remote → `None`, warning contains `"no git remote 'origin'"`.
- single remote named `upstream`, no `origin` → uses it.
- `git.example.com` remote, no provider → `None`, warning names the host and `provider`.
- same, with `provider = "gitlab"` → gitlab context.
- only `base_url` + `provider`, no remote → context.
- HEAD not under `refs/remotes/origin/` → context **and** the "resolve once it is pushed" warning.
- a cited file modified in the working tree, and an untracked cited file → both in `ctx.unlinked`, with one warning listing both, sorted.

- [ ] **Step 2: Run to confirm they fail**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True)
class LinkConfig:
    remote: str = "origin"
    provider: str | None = None
    base_url: str | None = None
    code_template: str | None = None
    commit_template: str | None = None


def config_from_profile(profile: dict) -> tuple[LinkConfig | None, list[str]]:
    """Validate [links]. Any error disables linking with exactly one warning."""
    ...  # checks per spec §2, message prefix "references are not linked: [links] "


def link_context(repo, profile, head, cited_paths) -> tuple[LinkContext | None, list[str]]:
    ...
```

`link_context` follows spec §3 and §6. It uses `c.git(repo, "remote")`, `c.git(repo, "remote", "get-url", name)`, `c.git(repo, "branch", "-r", "--contains", head, "--format=%(refname)")` and `c.git(repo, "status", "--porcelain", "-z", "--untracked-files=all", "--", *cited_paths)`. Any `ThunderstruckError` from `c.git` → `(None, ["references are not linked: <reason>"])`. `cited_paths` is sorted and deduplicated before the status call so the warning text is deterministic. With `-z`, rename entries carry two paths, and both count as unlinked.

- [ ] **Step 4: Run** `pytest tests/test_links.py -q` → pass.

- [ ] **Step 5: Commit** `"Read [links] from the profile and resolve the remote, dirty files and push state"`

---

### Task 3: Linked refs in report.md (AC-1, AC-2, AC-5, AC-6)

**Files:**
- Modify: `scripts/report.py` (`collect`, `render_markdown`)
- Modify: `tests/test_pipeline.py`
- Modify: `tests/fixtures/build_fixture.py` (add `add_remote(repo, url, tracking=True)`)

- [ ] **Step 1: Write the failing tests**

In `tests/test_pipeline.py`, add a fixture `linked_repo` that copies the scanned fixture (as `context_repo_template` does), calls `add_remote(repo, "https://github.com/acme/fixture.git")`, writes the `_valid_finding`, validates and renders. Tests:

```python
def test_report_links_every_resolved_ref(linked_repo):
    report = (linked_repo / ".thunderstruck" / "report.md").read_text()
    head = _hotspots(linked_repo)["repo"]["head"]
    base = f"https://github.com/acme/fixture/blob/{head}/"
    assert re.search(r"\*\* · \[`[^`]+:\d+(-\d+)?`\]\(" + re.escape(base), report)  # location
    assert re.search(r"_code_ \[`[^`]+`\]\(" + re.escape(base), report)
    assert re.search(r"_detector_ \[`S\d+@[^`]+`\]\(" + re.escape(base), report)
    assert re.search(r"_commit_ \[`[0-9a-f]{7}`\]\(https://github.com/acme/fixture/commit/[0-9a-f]{40}\)", report)


def test_catalog_refs_stay_plain(...)            # when context is present
def test_no_remote_renders_plain_refs_and_warns(scanned_repo, ...)
def test_disabled_links_are_silent(...)
def test_dirty_cited_file_is_not_linked(...)     # append a line to the finding's file after validate
def test_token_in_remote_never_reaches_output(...)  # https://bob:ghs_SECRET@github.com/…; grep report.md + report.json
def test_finding_supplied_url_is_ignored(...)    # evidence item with "url": "https://evil.example" is replaced
```

Also extend `test_report_renders_and_indexes` so it asserts that `index.json` contains no `"url"` key anywhere.

- [ ] **Step 2: Run to confirm they fail**

- [ ] **Step 3: Implement**

In `collect()`: gather `cited_paths` from every finding's `location.file` plus the path of every `code`/`detector` ref (parsed with `validate.CODE_REF` / `validate.DETECTOR_REF`, imported, not copied). Call `links.link_context(repo, c.load_profile(repo), head, cited_paths)`, and store `data["links"]` and `data["link_warnings"]`.

In `render_markdown()`:
- add `link_warnings` after `context_warnings` in *Run warnings*;
- a helper `_linked(text, url)` returns ``f"[`{text}`]({url})"`` when `url` is set, else ``f"`{text}`"``;
- a helper `_ref_url(links, repo, ev)` dispatches on `ev["type"]`. `code` and `detector` go through the regexes to `links.code(...)`. `commit` goes through `c.git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")` to `links.commit(full)`, with the text shortened to `full[:7]`. Anything else → `None`. Any parse or git failure → `None`;
- the location line uses `links.code(loc["file"], start, end)` from `loc["lines"]`.

- [ ] **Step 4: Run** the full suite. Only the allowed `test_docs_in_sync` sample checks may fail.

- [ ] **Step 5: Commit** `"Link finding locations and evidence refs to permalinks at the scanned commit"`

---

### Task 4: URLs in report.json (AC-7)

**Files:**
- Modify: `scripts/report.py` (`render_json`)
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Failing tests.** In `linked_repo`, `report.json` has a `links` object with `provider`, `base_url`, `sha` and `remote`. Every finding's `location.url` is a string. Every evidence item has a `url` key, and it is `null` for `catalog`. Link warnings appear in top-level `warnings`. In the no-remote repo, `links` is `null` and every `url` is `null`. The files in `.thunderstruck/findings/` are byte-identical before and after `report.py`.

- [ ] **Step 2: Implement.** Compute URLs once, in `collect()`, onto **deep copies** of the findings (`copy.deepcopy`), so the Markdown and JSON renderers read the same `url` values and the source finding files are never written. Refactor Task 3's renderer to read `ev["url"]` instead of computing it.

- [ ] **Step 3: Run** the suite. **Commit** `"Carry permalinks in report.json"`

---

### Task 5: Sample report, docs, version (AC-8, AC-9)

**Files:**
- Modify: `scripts/gen_sample_report.py`: after building the fixture, `add_remote(repo, "https://github.example.com/acme/fixture.git")` and a profile `[links] provider = "github"`. Extend the header comment: *"Links point at a placeholder host (github.example.com); in a real scan they open the cited line."*
- Regenerate: `examples/sample-report.md`
- Modify: `README.md`: a `### Source links` subsection under *Per-repository profiles* with the `[links]` table and the degradation table from spec §9, in short form
- Modify: `examples/thunderstruck.toml.example`: a commented `[links]` block
- Modify: `CHANGELOG.md` (`## 0.4.0`), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` → `0.4.0`
- Modify: `tests/test_docs_in_sync.py`: `test_sample_report_links_its_refs` asserts every `_code_`, `_detector_` and `_commit_` line in the sample is a link

- [ ] **Step 1:** Write `test_sample_report_links_its_refs`. It fails on the stale sample.
- [ ] **Step 2:** Update the generator, then `uv run scripts/gen_sample_report.py`. Read the diff: only ref formatting and the header comment should change.
- [ ] **Step 3:** Docs, example profile, version bump, CHANGELOG entry.
- [ ] **Step 4: Verify everything**

```bash
uv run --with pytest --with pyyaml --with lizard pytest tests/ -q
uv run scripts/gen_catalog_docs.py --check
uv run scripts/gen_sample_report.py --check
claude plugin validate . --strict
claude plugin marketplace add "$PWD" && claude plugin install thunderstruck@thunderstruck && claude plugin list
```

Then scan a real clone with an https remote (for example this repo), open three links from its `report.md` in a browser, and confirm each one lands on the cited line.

- [ ] **Step 5: Commit** `"Show permalinks in the sample report and document [links]; bump to 0.4.0"`

---

## AC coverage

| AC | Tasks |
|---|---|
| AC-1 | 1, 3 |
| AC-2 | 3 |
| AC-3 | 2 |
| AC-4 | 1, 3 |
| AC-5 | 2, 3 |
| AC-6 | 2, 3 |
| AC-7 | 4 |
| AC-8 | 3 (determinism test unchanged), 5 |
| AC-9 | 5 |
