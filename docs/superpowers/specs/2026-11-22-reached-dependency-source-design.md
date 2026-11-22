# Dependency source for packages reached through a declared package: design

**Requirements:** [#101](https://github.com/tomstagl/thunderstruck/issues/101). The problem, stories, scope and acceptance criteria (AC-n) are in the ticket and are not repeated here.
**Plan:** `docs/superpowers/plans/2026-11-22-reached-dependency-source.md`.
**Evidence:** `scripts/deps.py` (`pypi_declared` reads manifests and `requirements*.txt`, `discover_pypi` snapshots only those names, `_installed`, `_metadata_version`, `Limits`, `DEP_REF`, `resolve_dependency_ref`); `docs/calibration/verification.md` "Celery benchmark" (4 of 73 declared packages had source; py-amqp and SQLAlchemy are installed, not declared, and #37's spike needed both); `docs/superpowers/specs/2026-10-03-finding-verification-design.md` §4 (the dependency contract).

## 1. What is wrong

On celery/celery, `kombu` is declared; `py-amqp` is a hard requirement of `kombu` and `SQLAlchemy` is `kombu[sqlalchemy]`. Both are installed in the environment, neither is declared by Celery, so `discover_pypi` made no entry and `resolve_dependency_ref` rejects a ref into them. A skeptic that needed to read what `amqp` does on a closed channel could not cite it.

## 2. Decisions

### 2.1 Answering the ticket's open questions

**Resolve from the installed environment?** Yes, from the metadata of packages already being snapshotted. `deps.py` already reads `.venv/…/site-packages/*.dist-info/METADATA` and `RECORD` as data for declared packages. A declared package's own `METADATA` lists what it requires (`Requires-Dist:`), with `extra == "…"` markers for extras. Reading those lines is the same kind of read. Nothing is downloaded, executed or installed; the module's contract ("reads manifests, lock files, package metadata and archives as data") is unchanged.

**What may a skeptic cite when the package is not declared?** A `dependency` ref into a reached package, in the same form (`pypi:amqp@5.3.1:amqp/connection.py:120-140`), resolved by the same function against the index. The index entry says it is reached, through what, and at what version, so the brief and the report can show that the project does not declare it. It is evidence about what the declared package does when called, never about the project's own choice of version.

### 2.2 What is reached

Starting from every declared PyPI package that is installed, follow `Requires-Dist` in the installed `METADATA`:

- A requirement without an `extra` marker is followed.
- A requirement with `extra == "x"` is followed only when a declared requirement names that extra: `kombu[sqlalchemy]` (from a `requirements` line or `pyproject.toml`, including optional dependency groups) follows `sqlalchemy`, `kombu` alone does not. The extras of each declared requirement are kept by `pypi_declared`.
- Other markers (`python_version`, `sys_platform`) are evaluated with `packaging.markers.Marker.evaluate` for the extra in question. A marker that cannot be evaluated excludes the requirement and names it in the package's `reason`, never guessed in.
- Depth is at most **2** hops from a declared package (declared → reached → reached), breadth first, names in sorted order. A package already declared, or already reached, is not added again, and is not re-listed under another parent: its `reached_via` lists every first path found, at most 3.
- At most **40** reached packages per scan; the rest are named in `warnings`.

**Why depth 2.** The ticket's two packages are at depth 1; depth 2 covers the library one layer under them without turning the snapshot into the whole environment. The caps keep total size under `Limits.total_bytes` as today.

### 2.3 The index entry

A reached package is an entry like a declared one, with:

```json
{"id": "pypi:amqp", "ecosystem": "pypi", "name": "amqp", "declared": null, "declared_in": [],
 "reached_via": ["kombu"], "version": "5.3.1", "basis": "installed", "status": "available", …}
```

`basis` is a new value, `installed`: the version is what the environment holds, checked against nothing the project says, except that a lock file listing it (`uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile.lock` all list transitive packages) makes it `locked`, with the same mismatch rule as for a declared one. `BASES` gains `installed`. An editable install is `unavailable` with the same reason as today.

`status`, `snapshot`, the size limits and the copy are as for declared packages; the snapshot directory is `deps/pypi/<name>@<version>/`.

### 2.4 Briefs, reports and verdict reuse

The skeptic's brief lists reached packages in the same table as declared ones, each marked `reached via <parent>`, after the declared ones, so a skeptic knows it is reading the parent's dependency. The brief stays deterministic (the order is sorted, no path or time). A scan on a project with a populated environment therefore has a different brief hash from one before this change, and its verdicts are checked again once; a project with no environment, and the fixture, are unchanged.

`report.py` prints a dependency citation as it does now; for a reached package it appends "(not declared by the project; reached through kombu)". The finding's own `check.dependency_versions` records it as for any other.

### 2.5 npm and Maven

Not changed. The ticket's evidence is PyPI. npm's installed tree and Maven's resolved graph are a different mechanism and get their own ticket if a measurement shows the same gap.

## 3. Out of scope

Installing, fetching or building anything; reading the project's own package metadata as dependencies; a size or depth that adapts to the project.

## 4. Degradation

A reached package with no `RECORD`, or no `.py` files, is `unavailable` with a reason. An unreadable `METADATA` stops following that branch and names it in `warnings`. No installed environment: nothing is reached, as today.

## 5. Test strategy

- A synthetic site-packages in `tmp_path` with `kombu` (requires `amqp`, and `sqlalchemy` under `extra == "sqlalchemy"`), `amqp` (requires `vine`) and `sqlalchemy`: declared `kombu` alone reaches `amqp` and `vine`, not `sqlalchemy`; declared `kombu[sqlalchemy]` reaches all three. Each has the entry of §2.3, a snapshot, and `reached_via`.
- The depth cap, the 40-package cap, the sorted order, and a cycle (A requires B requires A).
- A marker that cannot be evaluated excludes the requirement and says why.
- A lock file listing the reached package gives `basis: locked`, and a mismatched version is `unavailable`.
- `resolve_dependency_ref` accepts a ref into a reached package and rejects one into an undeclared package that is not reached.
- The brief lists reached packages after declared ones; two runs are byte-identical.
- `report.py` marks the citation; a sample report is unchanged (`gen_sample_report.py --check`).
- `deps.py` still imports only the stdlib and `_common` at module level (the existing AST test), and `tests/test_no_execution.py` passes.
