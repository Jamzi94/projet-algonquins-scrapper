"""Tests de l'interrupteur unifié DATA_SOURCE + import paresseux de TMDB.

Vérifie que :
- DATA_SOURCE pilote catalog_source()/reco_via_bridge() (wikidata|seed|tmdb) ;
- les anciens toggles CATALOG_SOURCE/RECO_VIA_BRIDGE priment (rétro-compat) ;
- get_provider_status() expose data_source/catalog_source/reco_via_bridge ;
- le module TMDB n'est PAS importé tant que TMDB n'est pas activé (isolation).
"""
import subprocess
import sys
from pathlib import Path

import licensing as lic

_BACKEND = Path(__file__).resolve().parents[1]


def _clear(monkeypatch):
    for k in ("DATA_SOURCE", "CATALOG_SOURCE", "RECO_VIA_BRIDGE"):
        monkeypatch.delenv(k, raising=False)


def test_default_is_wikidata(monkeypatch):
    _clear(monkeypatch)
    assert lic.data_source() == "wikidata"
    assert lic.catalog_source() == "movreco"
    assert lic.reco_via_bridge() is True


def test_seed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATA_SOURCE", "seed")
    assert lic.data_source() == "seed"
    assert lic.catalog_source() == "seed"
    assert lic.reco_via_bridge() is False


def test_tmdb_source(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATA_SOURCE", "tmdb")
    # TMDB enrichit la base seed ; reco native.
    assert lic.data_source() == "tmdb"
    assert lic.catalog_source() == "seed"
    assert lic.reco_via_bridge() is False


def test_alias_and_unknown(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATA_SOURCE", "movreco")
    assert lic.data_source() == "wikidata"
    monkeypatch.setenv("DATA_SOURCE", "n_importe_quoi")
    assert lic.data_source() == "wikidata"


def test_legacy_overrides_win(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATA_SOURCE", "wikidata")
    monkeypatch.setenv("CATALOG_SOURCE", "seed")
    monkeypatch.setenv("RECO_VIA_BRIDGE", "0")
    assert lic.catalog_source() == "seed"          # override explicite
    assert lic.reco_via_bridge() is False           # override explicite


def test_provider_status_exposes_toggles(monkeypatch):
    _clear(monkeypatch)
    s = lic.get_provider_status()
    assert s["data_source"] == "wikidata"
    assert s["catalog_source"] == "movreco"
    assert s["reco_via_bridge"] is True
    assert "tmdb_enabled" in s  # forme TMDB conservée


def test_tmdb_module_not_imported_when_disabled():
    """Isolation : importer server ne doit PAS charger services.external.tmdb."""
    code = (
        "import sys; "
        "import server; "
        "print('LOADED' if 'services.external.tmdb' in sys.modules else 'LAZY')"
    )
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "MONGO_URL": "memory",
        "DATA_SOURCE": "wikidata",
        "JWT_SECRET": "test",
        "EXTERNAL_APIS_ENABLED": "false",
        "PYTHONPATH": f"{_BACKEND}:{_BACKEND.parents[1] / 'movie-reco'}",
    }
    out = subprocess.run([sys.executable, "-c", code], cwd=str(_BACKEND),
                         capture_output=True, text=True, env=env, timeout=120)
    assert "LAZY" in out.stdout, f"TMDB importé alors qu'il est désactivé :\n{out.stdout}\n{out.stderr}"
