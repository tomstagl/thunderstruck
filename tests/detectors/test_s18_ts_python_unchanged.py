"""AC-16 guard: S18 gained a Java branch, and TypeScript/Python must keep
exactly the behaviour they had before it. S18 has no TypeScript or Python
sample directory (it is Tier B), so these snippets pin the current hits."""

from __future__ import annotations

from detectors import run_detectors

_TS_AFTER = """export async function placeOrder(payload: string) {
  const quote = await fetch("https://pricing.example.com");
  if (!validate(payload)) {
    throw new Error("bad payload");
  }
  return quote;
}
"""
_TS_BEFORE = """export async function placeOrder(payload: string) {
  if (!validate(payload)) {
    throw new Error("bad payload");
  }
  return await fetch("https://pricing.example.com");
}
"""
_PY_AFTER = """def place_order(payload):
    quote = requests.get("https://pricing.example.com", timeout=5)
    if not payload:
        raise ValueError("payload required")
    return quote
"""
_PY_BEFORE = """def place_order(payload):
    if not payload:
        raise ValueError("payload required")
    return requests.get("https://pricing.example.com", timeout=5)
"""


def _s18(catalog, text: str, lang: str, name: str) -> list[tuple[str, int]]:
    return [(h.detector_id, h.line)
            for h in run_detectors(catalog, name, text, lang, pattern_ids=["S18"])]


def test_s18_typescript_behaviour_is_pinned(catalog):
    assert _s18(catalog, _TS_AFTER, "typescript", "src/order.ts") == [
        ("S18-ts-validate-after-call", 3)]
    assert _s18(catalog, _TS_BEFORE, "typescript", "src/order.ts") == []


def test_s18_python_behaviour_is_pinned(catalog):
    assert _s18(catalog, _PY_AFTER, "python", "src/order.py") == [
        ("S18-py-validate-after-call", 4)]
    assert _s18(catalog, _PY_BEFORE, "python", "src/order.py") == []
