import math

import pytest

from lattice.evaluation.quality import score
from lattice.observability.measure import export_csv, percentile, summarize


def test_percentiles_and_sparse_tail():
    assert percentile([], 0.5) is None
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    summary = summarize([1, 2, 3, 4])
    assert summary["mean"] == 2.5
    assert summary["stddev"] == pytest.approx(math.sqrt(5 / 3))
    assert summary["p99"] is None
    assert summarize(list(range(1000)))["p99"] is not None


def test_quality_does_not_execute_code(tmp_path):
    malicious = f"open({str(tmp_path / 'executed')!r}, 'w').write('bad')"
    assert not score({"scorer": "python_add_ast"}, malicious)
    assert not (tmp_path / "executed").exists()
    assert score({"scorer": "python_add_ast"}, "def add(a,b):\n return a+b")
    assert not score({"scorer": "python_add_ast"}, "def add(a,b):\n return b+a")
    assert score({"scorer": "json", "expected": {"x": 1}}, '{"x":1}')
    assert not score({"scorer": "json", "expected": {"x": 1}}, '```json\n{"x":1}\n```')


def test_export_keeps_failures(tmp_path):
    path = tmp_path / "out.csv"
    export_csv(
        [
            {"status": "error", "workload": "memory", "total_ms": None},
            {"status": "completed", "workload": "short", "total_ms": 3.5},
        ],
        path,
    )
    assert "error" in path.read_text() and "3.5" in path.read_text()
