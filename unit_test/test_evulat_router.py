import json

from routing_engine import evulat_router


def test_run_benchmark_uses_default_neighboring_dataset(tmp_path, monkeypatch, capsys):
    dataset_path = tmp_path / "ground_trooth.json"
    dataset_path.write_text(
        json.dumps([{"id": "1", "query": "dog", "expected_tool": "dog_tool"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(evulat_router, "__file__", str(tmp_path / "evulat_router.py"))
    monkeypatch.setattr(
        evulat_router,
        "system_one_decision",
        lambda query: ("dog_tool", 0.93),
    )

    evulat_router.run_benchmark()

    assert "1/1 (100.00% Accuracy)" in capsys.readouterr().out


def test_run_benchmark_reports_mismatches(tmp_path, monkeypatch, capsys):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps([{"id": "1", "query": "weather", "expected_tool": "weather_tool"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evulat_router,
        "system_one_decision",
        lambda query: ("books_tool", 0.42),
    )

    evulat_router.run_benchmark(dataset_path)

    output = capsys.readouterr().out
    assert "MISMATCHES FOUND (1)" in output
    assert "Expected: weather_tool | Predicted: books_tool" in output


def test_run_benchmark_handles_empty_dataset(tmp_path, capsys):
    dataset_path = tmp_path / "empty.json"
    dataset_path.write_text("[]", encoding="utf-8")

    evulat_router.run_benchmark(dataset_path)

    assert "No benchmark data found." in capsys.readouterr().out