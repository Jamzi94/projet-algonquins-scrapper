"""Tests hors-ligne de synopsis.fetch_extract_full (Équipe 1, texte intégral).

On monkeypatche ``synopsis.requests.get`` : aucun réseau réel. On valide que
l'extrait est correctement parsé depuis ``query.pages``, que ``max_chars`` tronque
le texte, que le cache évite un second appel réseau, et que les cas dégradés
(page manquante, titre vide) renvoient None.
"""
from __future__ import annotations

from movreco.ingest import cache, synopsis


class _Resp:
    """Réponse HTTP factice compatible avec l'usage de fetch_extract_full."""

    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


def _patch_get(monkeypatch, payload: dict, status_code: int = 200):
    """Remplace synopsis.requests.get par un faux qui compte les appels."""
    calls = {"n": 0, "url": None, "params": None}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        calls["url"] = url
        calls["params"] = params
        return _Resp(payload, status_code=status_code)

    monkeypatch.setattr(synopsis.requests, "get", fake_get)
    return calls


def _pages_payload(title: str, extract: str | None) -> dict:
    """Construit une réponse action=query&prop=extracts réaliste."""
    page: dict = {"pageid": 42, "ns": 0, "title": title}
    if extract is not None:
        page["extract"] = extract
    return {"batchcomplete": "", "query": {"pages": {"42": page}}}


# --------------------------------------------------------------------------- #
# Parsing du texte intégral depuis query.pages
# --------------------------------------------------------------------------- #
def test_fetch_extract_full_parse_le_texte_integral(monkeypatch):
    texte = "Ligne un.\n\nLigne deux : l'intrigue complète, pas seulement le lead."
    calls = _patch_get(monkeypatch, _pages_payload("Inception", texte))

    out = synopsis.fetch_extract_full("Inception", lang="fr")

    assert out == texte
    assert calls["n"] == 1
    # On vise bien l'API action=query (texte intégral), pas le résumé REST.
    assert calls["url"].endswith("/w/api.php")
    params = calls["params"]
    assert params["action"] == "query"
    assert params["prop"] == "extracts"
    assert params["explaintext"] == 1
    assert params["redirects"] == 1
    assert params["titles"] == "Inception"


def test_fetch_extract_full_respecte_max_chars(monkeypatch):
    texte = "A" * 500
    _patch_get(monkeypatch, _pages_payload("Long", texte))

    out = synopsis.fetch_extract_full("Long", lang="fr", max_chars=100)

    assert out is not None
    assert len(out) == 100
    assert out == "A" * 100


def test_fetch_extract_full_max_chars_none_ne_tronque_pas(monkeypatch):
    texte = "B" * 250
    _patch_get(monkeypatch, _pages_payload("Plein", texte))

    out = synopsis.fetch_extract_full("Plein", lang="fr", max_chars=None)

    assert out == texte


# --------------------------------------------------------------------------- #
# Cache : 2e appel sans réseau
# --------------------------------------------------------------------------- #
def test_fetch_extract_full_met_en_cache(tmp_path, monkeypatch):
    texte = "Texte intégral mis en cache."
    calls = _patch_get(monkeypatch, _pages_payload("Matrix", texte))

    s1 = synopsis.fetch_extract_full("Matrix", lang="fr", cache_dir=str(tmp_path))
    s2 = synopsis.fetch_extract_full("Matrix", lang="fr", cache_dir=str(tmp_path))

    assert s1 == s2 == texte
    # Le second appel est servi depuis le cache : un seul accès réseau.
    assert calls["n"] == 1
    # Clé de cache conforme au contrat (préfixe "full:").
    key = cache.make_key("full:fr:Matrix")
    assert (tmp_path / f"{key}.json").exists()


def test_cache_stocke_le_texte_brut_avant_troncature(tmp_path, monkeypatch):
    """Le cache garde l'extrait complet : changer max_chars reste honoré sur hit."""
    texte = "C" * 300
    calls = _patch_get(monkeypatch, _pages_payload("Brut", texte))

    # 1er appel tronqué : remplit le cache avec le texte BRUT (non tronqué).
    first = synopsis.fetch_extract_full(
        "Brut", lang="fr", cache_dir=str(tmp_path), max_chars=50
    )
    assert len(first) == 50
    assert calls["n"] == 1

    # 2e appel sans troncature : doit renvoyer le texte complet depuis le cache.
    second = synopsis.fetch_extract_full("Brut", lang="fr", cache_dir=str(tmp_path))
    assert second == texte
    assert calls["n"] == 1  # toujours aucun nouvel accès réseau

    # 3e appel avec une autre troncature : honorée sur cache hit.
    third = synopsis.fetch_extract_full(
        "Brut", lang="fr", cache_dir=str(tmp_path), max_chars=120
    )
    assert len(third) == 120
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# Cas dégradés
# --------------------------------------------------------------------------- #
def test_fetch_extract_full_titre_vide_renvoie_none(monkeypatch):
    calls = _patch_get(monkeypatch, _pages_payload("X", "ignore"))
    assert synopsis.fetch_extract_full("", lang="fr") is None
    # Aucun appel réseau pour un titre vide.
    assert calls["n"] == 0


def test_fetch_extract_full_page_manquante_renvoie_none(monkeypatch):
    # Page introuvable : id négatif, aucun champ "extract".
    payload = {"query": {"pages": {"-1": {"ns": 0, "title": "Inconnu", "missing": ""}}}}
    _patch_get(monkeypatch, payload)
    assert synopsis.fetch_extract_full("Inconnu", lang="fr") is None


def test_fetch_extract_full_sans_cache_inchange(monkeypatch):
    """Sans cache_dir, le comportement reste un simple aller-retour réseau."""
    _patch_get(monkeypatch, _pages_payload("Direct", "contenu direct"))
    assert synopsis.fetch_extract_full("Direct") == "contenu direct"


def test_fetch_summary_reste_inchange(monkeypatch):
    """Garde-fou rétro-compatibilité : fetch_summary (lead) n'est pas affecté."""

    class _SummaryResp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"extract": "résumé court (lead)"}

    monkeypatch.setattr(synopsis.requests, "get", lambda *a, **k: _SummaryResp())
    assert synopsis.fetch_summary("Inception", lang="fr") == "résumé court (lead)"
