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


def test_fetch_page_retries_transient_errors(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"rows":[{"row":{"trajectory_id":"a","instance_id":"a","resolved":0}}]}'

    def flaky_urlopen(req, timeout=60):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("502 Bad Gateway")
        return _Resp()

    monkeypatch.setattr(ing.urllib.request, "urlopen", flaky_urlopen)
    rows = ing._fetch_page(0, 1, max_retries=5, backoff=0)
    assert calls["n"] == 3          # failed twice, succeeded on third
    assert len(rows) == 1


def test_fetch_page_raises_after_max_retries(monkeypatch):
    def always_fail(req, timeout=60):
        raise OSError("502")
    monkeypatch.setattr(ing.urllib.request, "urlopen", always_fail)
    import pytest
    with pytest.raises(OSError):
        ing._fetch_page(0, 1, max_retries=3, backoff=0)
