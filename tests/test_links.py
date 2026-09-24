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
    "https://github.com/acme/x y", "git@github.com:acme/x#frag"])
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
    ("https://git.example.com/{x}", False), ("https://git.example.com/a b", False)])
def test_valid_base_url(value, ok):
    assert L.valid_base_url(value) is ok


# ------------------------------------------------------------------ paths --


@pytest.mark.parametrize("path, encoded", [
    ("src/x.ts", "src/x.ts"),
    ("./src/x.ts", "src/x.ts"),
    ("../src/x.ts", "src/x.ts"),          # same rule as validate.py
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
    ("{base}/{path", "unbalanced brace"),
])
def test_template_error(template, error):
    assert L.template_error(template) == error
