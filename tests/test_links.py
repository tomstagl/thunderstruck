"""links.py: remote parsing, URL building and link context."""

from __future__ import annotations

import pytest

import links as L

GH = "https://github.com/acme/checkout"
SHA = "a" * 40


# ------------------------------------------------------------ parse_remote --


@pytest.mark.parametrize("url, host, base", [
    ("https://github.com/acme/checkout.git", "github.com", GH),
    ("https://github.com/acme/checkout/", "github.com", GH),
    ("https://github.com/acme/checkout", "github.com", GH),
    ("https://x-access-token:ghs_SECRET@github.com/acme/checkout.git", "github.com", GH),
    ("git@github.com:acme/checkout.git", "github.com", GH),
    ("GitHub.com:acme/checkout", "github.com", GH),
    ("ssh://git@git.example.com:2222/acme/checkout.git", "git.example.com",
     "https://git.example.com/acme/checkout"),
    ("git+ssh://git@git.example.com/acme/checkout.git", "git.example.com",
     "https://git.example.com/acme/checkout"),
    ("git://git.example.com/acme/checkout", "git.example.com",
     "https://git.example.com/acme/checkout"),
    ("https://git.example.com:8443/acme/checkout", "git.example.com",
     "https://git.example.com:8443/acme/checkout"),
    ("http://git.example.com/acme/checkout", "git.example.com",
     "http://git.example.com/acme/checkout"),
    ("git@gitlab.com:acme/platform/checkout.git", "gitlab.com",
     "https://gitlab.com/acme/platform/checkout"),
    ("git@github-work:acme/checkout.git", "github-work", "https://github-work/acme/checkout"),
])
def test_parse_remote(url, host, base):
    r = L.parse_remote(url)
    assert r is not None, url
    assert (r.host, r.base) == (host, base)


@pytest.mark.parametrize("url", [
    "", "   ", "/srv/git/checkout.git", "file:///srv/git/checkout.git", "../checkout",
    "./checkout", "C:\\repos\\checkout", "https://github.com/", "https://github.com",
    "https://github.com:bad/x", "ftp://github.com/acme/x", "https://github.com/acme/{sha}",
    "https://github.com/acme/x y", "git@github.com:acme/x#frag",
    "git@git.example.com:acme/x)y`<z>.git", "https://github.com/acme/x](y)",
    "https://[::1]:8443/acme/x.git"])
def test_unlinkable_remotes(url):
    assert L.parse_remote(url) is None


def test_credentials_never_survive_parsing():
    r = L.parse_remote("https://bob:ghs_SECRET@github.com/acme/checkout.git")
    assert "bob" not in r.base and "SECRET" not in r.base and "@" not in r.base


@pytest.mark.parametrize("host, provider", [
    ("github.com", "github"), ("gitlab.com", "gitlab"), ("bitbucket.org", "bitbucket"),
    ("GitHub.com", "github"), ("gitlab.example.com", None), ("github.example.com", None),
    ("github-work", None), ("", None)])
def test_provider_is_detected_from_exact_hosts_only(host, provider):
    assert L.detect_provider(host) == provider


@pytest.mark.parametrize("value, ok", [
    ("https://git.example.com/acme/x", True), ("http://git.example.com/x", True),
    ("javascript:alert(1)", False), ("https:///x", False), ("git.example.com/x", False),
    ("https://git.example.com/{x}", False), ("https://git.example.com/a b", False),
    ("https://bob:TOKEN@git.example.com/acme/x", False), ("https://git.example.com/a)b", False),
    ("https://git.example.com/a?x=1", False), ("https://git.example.com:bad/a", False),
    ("https://git.example.com:8443/acme/x", True)])
def test_valid_base_url(value, ok):
    assert L.valid_base_url(value) is ok


# ------------------------------------------------------------------ paths --


@pytest.mark.parametrize("path, encoded", [
    ("src/x.ts", "src/x.ts"),
    ("./src/x.ts", "src/x.ts"),
    ("../src/x.ts", "../src/x.ts"),       # kept as written: path_problem rejects it
    ("src/my file.ts", "src/my%20file.ts"),
    ("src/a#b?.ts", "src/a%23b%3F.ts"),
    ("src/100%.ts", "src/100%25.ts"),
    ("src/[id].ts", "src/%5Bid%5D.ts"),
    ("src/a](javascript:x).ts", "src/a%5D%28javascript%3Ax%29.ts"),
    ("src/ünï.py", "src/%C3%BCn%C3%AF.py"),
])
def test_paths_are_normalised_and_encoded_per_segment(path, encoded):
    assert L.encode_path(path) == encoded


@pytest.mark.parametrize("value, total, expected", [
    (16, 40, (16, 16)),
    ("16", 40, (16, 16)),
    ("16-28", 40, (16, 28)),
    (" 16 - 28 ", 40, (16, 28)),
    ("1-40", 40, (1, 40)),
    ("L16", 40, None),
    ("16–28", 40, None),        # en dash
    ("28-16", 40, None),
    ("16-41", 40, None),
    (0, 40, None),
    ("16, 20-22", 40, None),
    (True, 40, None),
    (None, 40, None),
    ([16, 28], 40, None),
    ("16", None, None),
])
def test_location_lines_are_parsed_strictly(value, total, expected):
    assert L.parse_lines(value, total) == expected


# ------------------------------------------------------------------- urls --


@pytest.mark.parametrize("provider, start, end, url", [
    ("github", 16, 28, f"{GH}/blob/{SHA}/src/x.ts#L16-L28"),
    ("github", 16, None, f"{GH}/blob/{SHA}/src/x.ts#L16"),
    ("github", 16, 16, f"{GH}/blob/{SHA}/src/x.ts#L16"),
    ("github", None, None, f"{GH}/blob/{SHA}/src/x.ts"),
    ("gitlab", 16, 28, f"{GH}/-/blob/{SHA}/src/x.ts#L16-28"),
    ("gitlab", 16, None, f"{GH}/-/blob/{SHA}/src/x.ts#L16"),
    ("gitlab", None, None, f"{GH}/-/blob/{SHA}/src/x.ts"),
    ("bitbucket", 16, 28, f"{GH}/src/{SHA}/src/x.ts#lines-16:28"),
    ("bitbucket", 16, None, f"{GH}/src/{SHA}/src/x.ts#lines-16"),
    ("bitbucket", None, None, f"{GH}/src/{SHA}/src/x.ts"),
])
def test_code_urls(provider, start, end, url):
    ctx = L.LinkContext.for_provider(provider, base=GH, sha=SHA)
    assert ctx.code("src/x.ts", start, end) == url


@pytest.mark.parametrize("provider, url", [
    ("github", f"{GH}/commit/{SHA}"), ("gitlab", f"{GH}/-/commit/{SHA}"),
    ("bitbucket", f"{GH}/commits/{SHA}")])
def test_commit_urls(provider, url):
    assert L.LinkContext.for_provider(provider, base=GH, sha=SHA).commit(SHA) == url


@pytest.mark.parametrize("provider, path, start, url", [
    ("github", "docs/a.md", 3, f"{GH}/blob/{SHA}/docs/a.md?plain=1#L3"),
    ("github", "docs/a.MD", None, f"{GH}/blob/{SHA}/docs/a.MD?plain=1"),
    ("gitlab", "n.ipynb", 3, f"{GH}/-/blob/{SHA}/n.ipynb?plain=1#L3"),
    ("bitbucket", "docs/a.md", 3, f"{GH}/src/{SHA}/docs/a.md#lines-3"),
    ("github", "src/md.ts", 3, f"{GH}/blob/{SHA}/src/md.ts#L3"),
])
def test_rendered_files_get_plain_view(provider, path, start, url):
    assert L.LinkContext.for_provider(provider, base=GH, sha=SHA).code(path, start) == url


def test_unlinked_paths_get_no_url():
    ctx = L.LinkContext.for_provider("github", base=GH, sha=SHA,
                                     unlinked=frozenset({"src/x.ts"}))
    assert ctx.code("./src/x.ts", 3) is None
    assert ctx.code("src/y.ts", 3)


@pytest.mark.parametrize("provider, url", [
    ("github", f"{GH}/commits/{SHA}/src/%5Bid%5D%20x.md"),
    ("gitlab", f"{GH}/-/commits/{SHA}/src/%5Bid%5D%20x.md"),
    ("bitbucket", f"{GH}/history-node/{SHA}/src/%5Bid%5D%20x.md"),
])
def test_history_urls(provider, url):
    """Pinned to the scanned commit, encoded per segment, never ?plain=1."""
    assert L.LinkContext.for_provider(provider, base=GH, sha=SHA).history("./src/[id] x.md") == url


def test_history_is_absent_for_templates_and_unlinked_paths():
    tpl = L.LinkContext.for_templates("{base}/{path}?at={sha}", "{base}/c/{sha}",
                                      base=GH, sha=SHA)
    assert tpl.history("src/x.ts") is None and tpl.code("src/x.ts")
    ctx = L.LinkContext.for_provider("github", base=GH, sha=SHA,
                                     unlinked=frozenset({"src/x.ts"}))
    assert ctx.history("./src/x.ts") is None and ctx.history("") is None


@pytest.mark.parametrize("items, text", [
    ([], ""),
    (["a"], "a"),
    (list("abcde"), "a, b, c, d, e"),
    (list("abcdefg"), "a, b, c, d, e … and 2 more"),
])
def test_named_shows_at_most_five(items, text):
    assert L.named(items) == text


BASE_DC = "https://git.example.com/projects/ACME/repos/checkout"


def test_templates_fill_in_one_pass():
    ctx = L.LinkContext.for_templates(
        "{base}/browse/{path}?at={sha}#{start}-{end}", "{base}/commits/{sha}",
        base=BASE_DC, sha=SHA)
    assert ctx.code("src/x.ts", 4, 9) == f"{BASE_DC}/browse/src/x.ts?at={SHA}#4-9"
    assert ctx.code("src/x.ts", 4) == f"{BASE_DC}/browse/src/x.ts?at={SHA}#4-4"
    assert ctx.code("src/x.ts") == f"{BASE_DC}/browse/src/x.ts?at={SHA}"
    assert ctx.commit(SHA) == f"{BASE_DC}/commits/{SHA}"
    # a value that looks like a placeholder is never expanded again
    assert L._fill("{base}/{sha}", {"base": "{sha}", "sha": "x"}) == "{sha}/x"


def test_template_without_fragment_has_no_whole_file_link_when_lines_are_in_the_path():
    ctx = L.LinkContext.for_templates("{base}/{path}/{start}", "{base}/c/{sha}",
                                      base=BASE_DC, sha=SHA)
    assert ctx.code("x.ts") is None
    assert ctx.code("x.ts", 3) == f"{BASE_DC}/x.ts/3"


@pytest.mark.parametrize("template, error", [
    ("{base}/{path}#{start}", None),
    ("{base}/{sha.__class__}", "{sha.__class__}"),
    ("{base}/{branch}", "{branch}"),
    ("{base}/{path", "an unbalanced brace"),
    ("{base}/browse/{path}?at={sha}&x=1;y#{start}-{end}", None),
    ("{base}/browse/{path};{sha}${start}-{end}", None),   # Phabricator
    ("{base}/{path}?at={sha}&v=!*'~@,", None),
    *[(f"{{base}}/{{path}}{ch}{{sha}}", f"the character {ch!r}, which cannot appear in a link")
      for ch in ["|", " ", ")", "(", "<", ">", "`", "[", "]", "\\", '"', "\n", "\t", "\x7f"]],
])
def test_template_error(template, error):
    assert L.template_error(template) == error


# ----------------------------------------------------------------- config --


@pytest.mark.parametrize("links, fragment", [
    ("yes", "must be a table"),
    ({"provder": "github"}, "unknown key 'provder'"),
    ({"enabled": "yes"}, "enabled"),
    ({"remote": 1}, "remote must be a string"),
    ({"provider": "gitea"}, "provider"),
    ({"base_url": "javascript:alert(1)"}, "base_url"),
    ({"base_url": "https://git.example.com/{x}"}, "base_url"),
    ({"code_template": "{base}/{sha.__class__}", "commit_template": "{base}"}, "{sha.__class__}"),
    ({"code_template": "{base}/{path}"}, "set together"),
    ({"code_template": "{base}/static/page", "commit_template": "{base}/{sha}"}, "no {sha}"),
    ({"code_template": "{base}/{sha}", "commit_template": "{base}/{sha}"}, "no {path}"),
    ({"code_template": "{base}/{sha}/{path}", "commit_template": "{base}/c/{sha}#{path}"},
     "commit_template has {path}"),
    ({"code_template": "{base}/{sha}/{path}", "commit_template": "{base}/c"}, "no {sha}"),
    ({"commit_template": "{base}/{sha}"}, "set together"),
])
def test_invalid_config_disables_links_with_one_warning(links, fragment):
    cfg, warnings = L.config_from_profile({"links": links})
    assert cfg is None
    assert len(warnings) == 1 and fragment in warnings[0], warnings
    assert warnings[0].startswith(L.NOT_LINKED)


def test_disabled_is_silent():
    assert L.config_from_profile({"links": {"enabled": False}}) == (None, [])


def test_absent_table_uses_defaults():
    assert L.config_from_profile({}) == (L.LinkConfig(), [])


def test_base_url_trailing_slash_is_dropped():
    cfg, _ = L.config_from_profile({"links": {"base_url": "https://git.example.com/a/b/"}})
    assert cfg.base_url == "https://git.example.com/a/b"


# ----------------------------------------------------------- link_context --

import subprocess  # noqa: E402

GIT_ID = ["-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false"]


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *GIT_ID, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path, remote="https://github.com/acme/checkout.git", tracking=True,
          name="origin"):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "src").mkdir()
    for f in ("a.ts", "b.ts", "[id].ts"):
        (repo / "src" / f).write_text("one\ntwo\nthree\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    if remote:
        _git(repo, "remote", "add", name, remote)
        if tracking:
            _git(repo, "update-ref", f"refs/remotes/{name}/main", "HEAD")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_github_remote_links_with_no_warning(tmp_path):
    repo, sha = _repo(tmp_path)
    res = L.link_context(repo, {}, sha, ["src/a.ts"], [sha[:7]])
    assert res.warnings == []
    assert res.ctx.provider == "github" and res.ctx.remote == "origin"
    assert res.ctx.code("src/a.ts", 2) == f"{GH}/blob/{sha}/src/a.ts#L2"
    assert res.commits == {sha[:7]: sha}


def test_no_remote_is_reported(tmp_path):
    repo, sha = _repo(tmp_path, remote=None)
    res = L.link_context(repo, {}, sha, [], [])
    assert res.ctx is None and "no git remote" in res.warnings[0]


def test_sole_remote_is_used_when_there_is_no_origin(tmp_path):
    repo, sha = _repo(tmp_path, name="upstream")
    res = L.link_context(repo, {}, sha, [], [])
    assert res.ctx.remote == "upstream" and res.warnings == []


def test_named_remote_must_exist(tmp_path):
    repo, sha = _repo(tmp_path)
    res = L.link_context(repo, {"links": {"remote": "fork"}}, sha, [], [])
    assert res.ctx is None and "'fork'" in res.warnings[0]


def test_base_url_without_remote_links_and_skips_push_check(tmp_path):
    repo, sha = _repo(tmp_path, remote=None)
    profile = {"links": {"provider": "gitlab", "base_url": "https://git.example.com/acme/x"}}
    res = L.link_context(repo, profile, sha, ["src/a.ts"], [])
    assert res.warnings == []
    assert res.ctx.remote is None
    assert res.ctx.code("src/a.ts", 1) == f"https://git.example.com/acme/x/-/blob/{sha}/src/a.ts#L1"


def test_unrecognised_host_names_provider_and_base_url(tmp_path):
    repo, sha = _repo(tmp_path, remote="git@github-work:acme/checkout.git")
    res = L.link_context(repo, {}, sha, [], [])
    assert res.ctx is None
    assert "github-work" in res.warnings[0] and "provider" in res.warnings[0]
    assert "base_url" in res.warnings[0]


def test_self_hosted_provider_from_profile(tmp_path):
    repo, sha = _repo(tmp_path, remote="git@git.example.com:acme/checkout.git")
    res = L.link_context(repo, {"links": {"provider": "gitlab"}}, sha, [], [])
    assert res.ctx.commit(sha) == f"https://git.example.com/acme/checkout/-/commit/{sha}"


def test_templates_from_profile(tmp_path):
    repo, sha = _repo(tmp_path, remote="ssh://git@git.example.com:7999/acme/checkout.git")
    profile = {"links": {"code_template": "{base}/browse/{path}?at={sha}#{start}-{end}",
                         "commit_template": "{base}/commits/{sha}"}}
    res = L.link_context(repo, profile, sha, ["src/a.ts"], [])
    assert res.ctx.code("src/a.ts", 2, 3) == \
        f"https://git.example.com/acme/checkout/browse/src/a.ts?at={sha}#2-3"


def test_token_in_remote_never_reaches_a_url_or_warning(tmp_path):
    repo, sha = _repo(tmp_path, remote="https://bob:ghs_SECRET@github.com/acme/checkout.git")
    res = L.link_context(repo, {}, sha, ["src/a.ts"], [sha])
    blob = " ".join([res.ctx.base, res.ctx.code("src/a.ts", 1), res.ctx.commit(sha),
                     *res.warnings])
    assert "SECRET" not in blob and "bob" not in blob


@pytest.mark.parametrize("change", [
    "modified", "staged", "committed_after_scan", "untracked", "ignored", "symlink", "deleted",
    "assume_unchanged", "skip_worktree", "symlinked_dir", "submodule"])
def test_files_that_differ_from_the_scanned_commit_are_not_linked(tmp_path, change):
    repo, sha = _repo(tmp_path)
    target = "src/a.ts"
    if change == "modified":
        (repo / target).write_text("changed\n")
    elif change == "staged":
        (repo / target).write_text("changed\n")
        _git(repo, "add", target)
    elif change == "committed_after_scan":
        (repo / target).write_text("changed\n")
        _git(repo, "commit", "-qam", "later")
    elif change == "untracked":
        target = "src/new.ts"
        (repo / target).write_text("x\n")
    elif change == "ignored":
        (repo / ".gitignore").write_text("gen/\n")
        (repo / "gen").mkdir()
        target = "gen/out.ts"
        (repo / target).write_text("x\n")
    elif change == "symlink":
        (repo / "src" / "link.ts").symlink_to("a.ts")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "link")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        sha = _git(repo, "rev-parse", "HEAD")
        target = "src/link.ts"
    elif change == "deleted":
        (repo / target).unlink()
    elif change in ("assume_unchanged", "skip_worktree"):
        _git(repo, "update-index", f"--{change.replace('_', '-')}", target)
        (repo / target).write_text("changed\n")
    elif change == "symlinked_dir":
        (repo / "lnk").symlink_to("src")
        _git(repo, "add", "lnk")
        _git(repo, "commit", "-qm", "dir link")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        sha = _git(repo, "rev-parse", "HEAD")
        target = "lnk/a.ts"
    elif change == "submodule":
        sub = tmp_path / "sub"
        sub.mkdir()
        _git(sub, "init", "-q")
        (sub / "f.c").write_text("int x;\n")
        _git(sub, "add", ".")
        _git(sub, "commit", "-qm", "sub")
        _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "vendor")
        _git(repo, "commit", "-qm", "add submodule")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        sha = _git(repo, "rev-parse", "HEAD")
        target = "vendor/f.c"
    res = L.link_context(repo, {}, sha, [target, "./src/b.ts"], [])
    assert res.ctx.code(target, 1) is None and res.ctx.history(target) is None
    assert res.ctx.code("src/b.ts", 1), "an unchanged file stays linked"
    stale = [w for w in res.warnings if "not linked" in w]
    assert len(stale) == 1 and target in stale[0] and "src/b.ts" not in stale[0]


def test_many_stale_files_are_summarised(tmp_path):
    repo, sha = _repo(tmp_path)
    paths = [f"src/n{i}.ts" for i in range(7)]
    for p in paths:
        (repo / p).write_text("x\n")
    res = L.link_context(repo, {}, sha, paths, [])
    assert res.warnings == [f"7 file(s) differ from the scanned commit {sha[:7]} or are not "
                            "in it, and are not linked: src/n0.ts, src/n1.ts, src/n2.ts, "
                            "src/n3.ts, src/n4.ts … and 2 more"]


def test_many_paths_are_checked_in_chunks(tmp_path, monkeypatch):
    repo, sha = _repo(tmp_path)
    paths = [f"src/p{i:03d}.ts" for i in range(250)] + ["src/a.ts"]
    calls = []
    real = L._git
    monkeypatch.setattr(L, "_git", lambda r, *a, **k: calls.append(a) or real(r, *a, **k))
    res = L.link_context(repo, {}, sha, paths, [])
    assert res.ctx.code("src/a.ts") and res.ctx.code("src/p000.ts") is None
    assert res.warnings[0].startswith("250 file(s)")
    assert max(len(a) for a in calls) < L.PATHS_PER_CALL + 10


def test_chunks_are_bounded_by_count_and_length():
    many = [f"p{i}" for i in range(250)]
    assert [len(c) for c in L._chunks(many)] == [100, 100, 50]
    long = ["d/" * 200 + f"f{i}" for i in range(100)]
    chunks = list(L._chunks(long))
    assert sum(chunks, []) == long
    assert all(sum(len(p) + 1 for p in c) <= L.CHARS_PER_CALL for c in chunks)
    assert list(L._chunks([])) == [] and list(L._chunks(["x" * 9000])) == [["x" * 9000]]


def test_bad_template_character_is_named(tmp_path):
    cfg, warnings = L.config_from_profile({"links": {"code_template": "{base}/{path} {sha}",
                                                     "commit_template": "{base}/{sha}"}})
    assert cfg is None and warnings == [
        "references are not linked: [links] code_template has the character ' ', which "
        "cannot appear in a link in .thunderstruck.toml"]


def test_bracketed_paths_are_literal(tmp_path):
    repo, sha = _repo(tmp_path)
    res = L.link_context(repo, {}, sha, ["src/[id].ts"], [])
    assert res.warnings == []
    assert res.ctx.code("src/[id].ts", 1).endswith("/src/%5Bid%5D.ts#L1")


def test_bad_commit_tokens_are_not_expanded(tmp_path):
    repo, sha = _repo(tmp_path)
    res = L.link_context(repo, {}, sha, [], ["deadbeef", "not-hex", sha])
    assert res.commits == {sha: sha}


def test_unpushed_scanned_commit_is_linked_with_a_warning(tmp_path):
    repo, sha = _repo(tmp_path, tracking=False)
    res = L.link_context(repo, {}, sha, ["src/a.ts"], [])
    assert res.ctx.code("src/a.ts", 1)
    assert len(res.warnings) == 1 and sha[:7] in res.warnings[0]
    assert "resolve once pushed" in res.warnings[0]


def test_unpushed_cited_commit_is_warned(tmp_path):
    repo, scanned = _repo(tmp_path)
    _git(repo, "checkout", "-qb", "side")
    (repo / "src" / "b.ts").write_text("side\n")
    _git(repo, "commit", "-qam", "side")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-")
    res = L.link_context(repo, {}, scanned, [], [side])
    assert res.commits == {side: side}
    assert len(res.warnings) == 1 and side[:7] in res.warnings[0] and scanned[:7] not in res.warnings[0]


def test_git_failure_degrades_to_one_warning(tmp_path):
    res = L.link_context(tmp_path, {}, "a" * 40, ["x.ts"], [])
    assert res.ctx is None and len(res.warnings) == 1
    assert res.warnings[0].startswith(L.NOT_LINKED)


def test_unknown_scanned_commit_is_reported(tmp_path):
    repo, _ = _repo(tmp_path)
    res = L.link_context(repo, {}, "HEAD", [], [])
    assert res.ctx is None and "scanned commit" in res.warnings[0]


def test_paths_leaving_the_repo_are_unlinked_without_touching_git(tmp_path):
    repo, sha = _repo(tmp_path)
    res = L.link_context(repo, {}, sha, ["src/../../outside.txt", "src/a.ts"], [])
    assert res.ctx is not None, res.warnings
    assert res.ctx.code("src/../../outside.txt", 1) is None
    assert res.ctx.code("src/a.ts", 1)
    assert str(tmp_path) not in " ".join(res.warnings)


def test_git_failures_name_no_local_path(tmp_path, monkeypatch):
    repo, sha = _repo(tmp_path)

    def boom(repo_root, *args, **kw):
        raise L.c.ThunderstruckError(f"git {' '.join(args)} failed: fatal: {repo_root} is broken")
    monkeypatch.setattr(L.c, "git", boom)
    res = L.link_context(repo, {}, sha, ["src/a.ts"], [])
    assert res.ctx is None
    assert res.warnings == [f"{L.NOT_LINKED}a git command failed in this repository"]


def test_git_timeout_is_named(tmp_path, monkeypatch):
    repo, sha = _repo(tmp_path)

    def slow(repo_root, *args, **kw):
        raise subprocess.TimeoutExpired(["git", "-C", str(repo_root), *args], 30)
    monkeypatch.setattr(L.c, "git", slow)
    res = L.link_context(repo, {}, sha, [], [])
    assert res.warnings == [f"{L.NOT_LINKED}git remote did not answer within 30s"]
