"""Java detectors land in batches, and one positive sample per pattern can
hide a detector that never fires: the pattern-level sample test passes as
long as *any* of a pattern's detectors hits. This pins every Java detector
individually, and pins the confidence discipline from the spec (§5): no Java
detector claims `high` until calibration has earned it."""

from __future__ import annotations

from pathlib import Path

from detectors import run_detectors

SAMPLES = Path(__file__).parent / "samples"


def _java_detectors(catalog):
    for pattern in catalog["patterns"]:
        for det in (pattern.get("detectors") or {}).get("java", []) or []:
            yield pattern, det


def test_every_java_detector_fires_on_its_positive_sample(catalog):
    silent = []
    for pattern, det in _java_detectors(catalog):
        sample = SAMPLES / pattern["id"] / "java" / "positive.java"
        if not sample.exists():
            silent.append(f"{det['id']} (no {sample})")
            continue
        solo = {**catalog, "patterns": [{**pattern, "detectors": {"java": [det]}}]}
        hits = run_detectors(solo, f"src/{sample.name}",
                             sample.read_text(encoding="utf-8"), "java")
        if not any(h.detector_id == det["id"] for h in hits):
            silent.append(det["id"])
    assert not silent, (
        "Java detectors that never fire on their pattern's positive sample: "
        + ", ".join(silent))


def test_no_java_detector_claims_high_confidence(catalog):
    high = [det["id"] for _, det in _java_detectors(catalog)
            if det.get("confidence") == "high"]
    assert not high, f"Java detectors at confidence: high before calibration earned it: {high}"


# Synthetic inputs that have each exposed super-linear backtracking in a Java
# detector on this branch. The catch body is sized so the S15 regex that
# backtracked (~n^4) takes seconds rather than hours, and the test still ends.
_PATHOLOGICAL = {
    "long catch body": (
        "class A {\n  String f() {\n"
        "    try { return restTemplate.getForObject(u, String.class); }\n"
        "    catch (Exception e) {\n" + '      log.warn("x", e);\n' * 50
        + "    }\n    throw new IllegalStateException();\n  }\n}\n"),
    "many small methods": (
        "class A {\n" + ("  @Retryable(maxAttempts = 3)\n"
                         "  public String m(int a) { return x(a); }\n") * 2000 + "}\n"),
    "many for-loops": (
        "class A {\n  void f() {\n" + ("    for (int attempt = 0; attempt < n; attempt++) {\n"
                                      "      restTemplate.getForObject(u, String.class);\n"
                                      "    }\n") * 500 + "  }\n}\n"),
    "one long line": (
        "class A { void f() { " + "for ( catch ( q.poll( x.get( xs.forEach( " * 1000 + "} }\n"),
    "unclosed poll calls": "class A {\n" + "  q.poll(a\n" * 5000 + "}\n",
    "unclosed runnable params": (
        "class A {\n  E p = Executors.newFixedThreadPool(2);\n"
        + "  void m(Runnable r) { x();\n" * 5000 + "}\n"),
    "long response chain": (
        "class A {\n  public String f(String id) {\n    String a0 = rest.getForObject(u);\n"
        + "".join(f"    String a{i} = a{i - 1}.trim();\n" for i in range(1, 3000))
        + "    Objects.requireNonNull(id);\n  }\n}\n"),
}
_BUDGET_S = 1.0


def test_java_detectors_are_fast_on_pathological_input(catalog):
    import time

    slow = []
    for pattern, det in _java_detectors(catalog):
        solo = {**catalog, "patterns": [{**pattern, "detectors": {"java": [det]}}]}
        for name, text in _PATHOLOGICAL.items():
            start = time.perf_counter()
            run_detectors(solo, "src/A.java", text, "java")
            took = time.perf_counter() - start
            if took > _BUDGET_S:
                slow.append(f"{det['id']} on {name}: {took:.2f}s")
    assert not slow, f"Java detectors over the {_BUDGET_S}s budget: " + "; ".join(slow)
