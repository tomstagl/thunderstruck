"""Python detector regexes must stay roughly linear. The #19 review repair
gave S05-py an anchor whose `[^\\n]*` and `\\w*` overlapped, and it backtracked
for minutes on a real netbox file (docs/calibration/python.md)."""

from __future__ import annotations

import time

import _common
from detectors import run_detectors


def test_s05_loop_body_with_long_identifier_lines_is_fast():
    catalog = _common.load_catalog()
    line = "a" * 2000
    body = ("import requests\n\nfor item in items:\n"
            + "".join(f"    {line}\n" for _ in range(8)) + "x = 1\n")
    start = time.monotonic()
    run_detectors(catalog, "src/a.py", body, "python", pattern_ids=["S05"])
    assert time.monotonic() - start < 0.5
