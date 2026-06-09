import src.ingest_hf as ing


def _fake_pages(monkeypatch, pages):
    """pages: list of lists of api-row dicts, returned per call in order."""
    calls = {"i": 0}

    def fake_fetch(offset, length):
        i = calls["i"]
        calls["i"] += 1
        return pages[i] if i < len(pages) else []

    monkeypatch.setattr(ing, "_fetch_page", fake_fetch)


def _row(tid):
    return {"row": {"trajectory_id": tid, "instance_id": tid, "repo": "r",
                    "trajectory": [], "model_patch": "", "resolved": 0,
                    "pred_passes_gen_tests": 1.0, "gen_tests_correct": 0.0}}


def test_iter_normalized_yields_limit(monkeypatch):
    _fake_pages(monkeypatch, [[_row("a"), _row("b")], [_row("c"), _row("d")]])
    out = list(ing.iter_normalized(limit=3))
    assert len(out) == 3
    assert out[0]["task_id"] == "a"
    assert out[0]["test_results"]["pred_passes_gen_tests"] == 1.0


def test_iter_normalized_stops_on_empty_page(monkeypatch):
    _fake_pages(monkeypatch, [[_row("a")], []])
    out = list(ing.iter_normalized(limit=100))
    assert len(out) == 1
