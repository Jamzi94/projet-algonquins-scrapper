"""Récupération des synopsis depuis Wikipédia (texte sous licence CC BY-SA).

Le texte récupéré est destiné au traitement local (calcul d'embeddings). Il ne
doit pas être redistribué tel quel sans respecter l'attribution et le partage à
l'identique (voir DATA_LICENSES.md).
"""
from __future__ import annotations

import urllib.parse

import requests


def fetch_summary(title: str, lang: str = "fr", session: requests.Session | None = None) -> str | None:
    """Renvoie le résumé (lead) d'un article Wikipédia, ou None si indisponible."""
    if not title:
        return None
    sess = session or requests
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        r = sess.get(url, headers={"User-Agent": "movreco/0.1"}, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    return data.get("extract")
