"""Récupération des synopsis depuis Wikipédia (texte sous licence CC BY-SA).

Le texte récupéré est destiné au traitement local (calcul d'embeddings). Il ne
doit pas être redistribué tel quel sans respecter l'attribution et le partage à
l'identique (voir DATA_LICENSES.md).
"""
from __future__ import annotations

import time
import urllib.parse

import requests

DEFAULT_USER_AGENT = "movreco/0.1 (+https://github.com/movreco; contact@movreco.local)"


def fetch_summary(
    title: str,
    lang: str = "fr",
    session: requests.Session | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str | None:
    """Renvoie le résumé (lead) d'un article Wikipédia, ou None si indisponible.

    Effectue quelques tentatives avec backoff sur erreur réseau ou statut
    transitoire (429 / 5xx) ; renvoie None si tout échoue.
    """
    if not title:
        return None
    sess = session or requests
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    headers = {"User-Agent": user_agent}
    retries = 3
    for attempt in range(retries):
        try:
            r = sess.get(url, headers=headers, timeout=30)
        except requests.RequestException:
            if attempt + 1 >= retries:
                return None
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json().get("extract")
        if r.status_code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
            time.sleep(2 ** attempt)
            continue
        return None
    return None
