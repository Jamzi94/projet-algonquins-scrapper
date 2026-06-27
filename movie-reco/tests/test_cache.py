"""Tests hors-ligne du cache disque (Équipe 1)."""
from movreco.ingest import cache, synopsis, wikidata


def test_make_key_stable_et_sha256():
    k = cache.make_key("hello")
    assert k == cache.make_key("hello")
    assert len(k) == 64 and all(c in "0123456789abcdef" for c in k)


def test_cache_roundtrip(tmp_path):
    key = cache.make_key("q")
    assert cache.cache_get(tmp_path, key) is None  # miss avant écriture
    cache.cache_set(tmp_path, key, {"a": 1})
    assert cache.cache_get(tmp_path, key) == {"a": 1}


def test_cache_cree_le_dossier(tmp_path):
    sub = tmp_path / "n1" / "n2"
    cache.cache_set(sub, cache.make_key("x"), [1, 2, 3])
    assert cache.cache_get(sub, cache.make_key("x")) == [1, 2, 3]


def test_cache_get_tolerant_au_corrompu(tmp_path):
    key = cache.make_key("bad")
    (tmp_path / f"{key}.json").write_text("{ pas du json", encoding="utf-8")
    assert cache.cache_get(tmp_path, key) is None


def test_run_sparql_utilise_le_cache_avant_le_reseau(tmp_path, monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": {"bindings": [{"film": {"value": "wd:Q1"}}]}}

    def _fake_get(*a, **k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(wikidata.requests, "get", _fake_get)
    cfg = {
        "wikidata": {"endpoint": "http://x", "user_agent": "ua", "timeout": 1},
        "cache": {"enabled": True, "dir": str(tmp_path)},
    }
    q = "SELECT * WHERE {}"
    r1 = wikidata.run_sparql(q, cfg)
    r2 = wikidata.run_sparql(q, cfg)  # doit venir du cache
    assert r1 == r2 == [{"film": "wd:Q1"}]
    assert calls["n"] == 1  # reseau touche une seule fois


def test_run_sparql_cache_desactive_touche_le_reseau(tmp_path, monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": {"bindings": []}}

    def _fake_get(*a, **k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(wikidata.requests, "get", _fake_get)
    cfg = {
        "wikidata": {"endpoint": "http://x", "user_agent": "ua", "timeout": 1},
        "cache": {"enabled": False, "dir": str(tmp_path)},
    }
    wikidata.run_sparql("Q", cfg)
    wikidata.run_sparql("Q", cfg)
    assert calls["n"] == 2


def test_fetch_summary_met_en_cache(tmp_path, monkeypatch):
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"extract": "résumé"}

    def _fake_get(*a, **k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(synopsis.requests, "get", _fake_get)
    s1 = synopsis.fetch_summary("Inception", lang="fr", cache_dir=str(tmp_path))
    s2 = synopsis.fetch_summary("Inception", lang="fr", cache_dir=str(tmp_path))
    assert s1 == s2 == "résumé"
    assert calls["n"] == 1


def test_run_sparql_cache_dir_relatif_resolu_contre_root(tmp_path, monkeypatch):
    """Un dir de cache RELATIF est ancre a cfg['_root'], pas au CWD du process."""
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"results": {"bindings": [{"film": {"value": "wd:Q1"}}]}}

    def _fake_get(*a, **k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr(wikidata.requests, "get", _fake_get)
    cfg = {
        "wikidata": {"endpoint": "http://x", "user_agent": "ua", "timeout": 1},
        "cache": {"enabled": True, "dir": "data/cache"},  # RELATIF
        "_root": str(tmp_path),
    }
    q = "SELECT * WHERE {}"
    wikidata.run_sparql(q, cfg)
    wikidata.run_sparql(q, cfg)  # hit cache si bien ancre a _root
    assert calls["n"] == 1
    # Le fichier de cache existe bien sous <_root>/data/cache, pas sous le CWD.
    assert (tmp_path / "data" / "cache" / f"{cache.make_key(q)}.json").exists()


def test_fetch_summary_sans_cache_inchange(monkeypatch):
    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"extract": "ok"}

    monkeypatch.setattr(synopsis.requests, "get", lambda *a, **k: _Resp())
    assert synopsis.fetch_summary("X") == "ok"
