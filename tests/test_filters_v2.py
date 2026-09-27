from __future__ import annotations

import pytest

import _common as c

F = c.Filters()


@pytest.mark.parametrize("path,reason", [
    ("app/tests.py", "test"), ("app/api_tests.py", "test"),
    ("cypress/support/commands.ts", "test"),
    ("playwright.config.ts", "tooling"), ("vitest.config.mts", "tooling"),
    ("src/types/api.d.ts", "generated"), ("stubs/requests.pyi", "generated"),
    ("src/__generated__/graphql.ts", "generated"), ("api/generated/Client.java", "generated"),
    ("benchmarks/load.py", "test"),
    ("scripts/testing/test-admin-page.js", "test"),
    (".github/workflows/ci.yml", "tooling"), ("docker-compose.dev.yml", "tooling"),
    ("openapi.yaml", "generated"),
    ("db/migrations/001.py", "migration"), ("node_modules/x/index.js", "vendored"),
    ("dist/app.js", "build"), ("yarn.lock", "asset"),
    ("src/client/releases.ts", None), ("src/app.config/loader.ts", None),
    ("jest.config.js", "tooling"), ("next.config.mjs", "tooling"),
    ("webpack.config.cjs", "tooling"), ("vite.config.ts", "tooling"),
    # runtime configuration is production code (NestJS, Angular)
    ("src/config/database.config.ts", None), ("src/app/app.config.ts", None),
])
def test_exclusion_reason(path, reason):
    assert F.exclusion_reason(path) == reason
    assert F.excludes_path(path) == (reason is not None)


def test_include_tests_keeps_test_paths():
    f = c.Filters(include_tests=True)
    assert f.exclusion_reason("app/tests.py") is None
    assert f.exclusion_reason("cypress/support/commands.ts") is None


def test_profile_and_path_reasons():
    f = c.Filters.from_profile({"filters": {"exclude_dirs": ["legacy"],
                                            "exclude_globs": ["*.gen.ts"]}},
                               path_prefix="src")
    assert f.exclusion_reason("src/legacy/a.ts") == "profile"
    assert f.exclusion_reason("src/api.gen.ts") == "profile"
    assert f.exclusion_reason("lib/a.ts") == "path"
    assert f.exclusion_reason("src/a.ts") is None


def test_profile_additions_take_effect():
    """from_profile used to extend the lists after they were compiled, so a
    profile's exclude_dirs, exclude_globs and exclude_authors were ignored."""
    f = c.Filters.from_profile({"filters": {"exclude_authors": ["release-bot"],
                                            "exclude_dirs": ["legacy"]}})
    assert f.excludes_author("Release-Bot <bot@example.com>")
    assert f.excludes_path("src/legacy/a.ts")
    assert not f.excludes_path("src/a.ts")
