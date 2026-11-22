"""The alias table, the weights and the documented table agree (#100, spec 2026-11-22 §2.4)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _common as c  # noqa: E402

ORCHESTRATION = ROOT / "skills" / "thunderstruck-scan" / "references" / "orchestration.md"
COLUMNS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


def test_every_alias_has_a_weights_row():
    assert {m: m in c.TOKEN_WEIGHTS for m in c.MODEL_ALIASES.values()} == \
        {m: True for m in c.MODEL_ALIASES.values()}


def test_the_skeptic_model_is_an_alias_key():
    front = yaml.safe_load((ROOT / "agents" / "thunderstruck-skeptic.md").read_text().split("---")[1])
    assert front["model"] in c.MODEL_ALIASES
    verify = (ROOT / "scripts" / "verify.py").read_text()
    default = re.search(r'add_argument\("--model", default="(\w+)"', verify)[1]
    assert default in c.MODEL_ALIASES


def test_the_orchestration_table_equals_the_weights_and_names_each_tier():
    text = ORCHESTRATION.read_text()
    table = {}
    for name, rest in re.findall(r"^\| `([^`]+)` \|(.+)\|$", text, re.M):
        table[name] = dict(zip(COLUMNS, (float(v) for v in rest.split("|"))))
    assert table == c.TOKEN_WEIGHTS
    flat = " ".join(text.split())
    for model, (threshold, row) in c.LONG_PROMPT_WEIGHTS.items():
        assert f"`{model}` is priced by prompt length" in flat
        assert f"{threshold:,}" in flat
        assert " | ".join(f"{row[k]:g}" for k in COLUMNS) in flat
