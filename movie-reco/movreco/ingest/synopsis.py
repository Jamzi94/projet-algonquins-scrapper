"""Récupération des synopsis depuis Wikipédia (texte sous licence CC BY-SA).

Le texte récupéré est destiné au traitement local (calcul d'embeddings). Il ne
doit pas être redistribué tel quel sans respecter l'attribution et le partage à
l'identique (voir DATA_LICENSES.md).
"""
from __future__ import annotations

import time
import urllib.parse

import requests

from movreco.ingest import cache

DEFAULT_USER_AGENT = "movreco/0.1 (+https://github.com/movreco; contact@movreco.local)"


def fetch_summary(
    title: str,
    lang: str = "fr",
    session: requests.Session | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    cache_dir: str | None = None,
) -> str | None:
    """Renvoie le résumé (lead) d'un article Wikipédia, ou None si indisponible.

    Effectue quelques tentatives avec backoff sur erreur réseau ou statut
    transitoire (429 / 5xx) ; renvoie None si tout échoue.

    Si `cache_dir` est fourni, le résumé est mis en cache sur disque (clé
    make_key(f"{lang}:{title}")) ; le réseau n'est sollicité que sur cache miss.
    """
    if not title:
        return None
    key = cache.make_key(f"{lang}:{title}") if cache_dir else None
    if cache_dir:
        hit = cache.cache_get(cache_dir, key)
        if hit is not None:
            return hit
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
            extract = r.json().get("extract")
            if cache_dir and extract is not None:
                cache.cache_set(cache_dir, key, extract)
            return extract
        if r.status_code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
            time.sleep(2 ** attempt)
            continue
        return None
    return None
