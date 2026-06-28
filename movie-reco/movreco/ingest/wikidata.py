"""Accès à Wikidata via le service SPARQL (données sous licence CC0).

Toutes les requêtes utilisent l'endpoint public. Un User-Agent identifiant est
obligatoire (voir config.yaml > wikidata.user_agent).
"""
from __future__ import annotations

import time
import unicodedata
from pathlib import Path
from typing import Iterable

import requests

from movreco.ingest import cache
from movreco.ingest.cache import make_key

PREFIXES = """
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX mwapi: <https://www.mediawiki.org/ontology#API/>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""

FILM_QID = "Q11424"  # entité "film" dans Wikidata


def _chunks(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _cache_dir(cfg: dict) -> Path:
    """Dossier de cache absolu (cfg.cache.dir sinon ROOT/data/cache).

    Un chemin relatif est resolu contre la racine du projet (cfg["_root"]), comme
    cli._cache_dir, pour que les deux etapes du pipeline pointent au meme endroit
    quel que soit le repertoire courant.
    """
    root = Path(cfg.get("_root", "."))
    cdir = cfg.get("cache", {}).get("dir")
    d = Path(cdir) if cdir else root / "data" / "cache"
    if not d.is_absolute():
        d = root / d
    return d


def run_sparql(query: str, cfg: dict, retries: int = 3) -> list[dict]:
    """Exécute une requête SPARQL et renvoie une liste de lignes (valeurs simples).

    Si le cache est activé (cfg.cache.enabled, défaut True), une requête déjà vue
    est servie depuis le disque ; le réseau n'est sollicité que sur cache miss.
    """
    cache_cfg = cfg.get("cache", {})
    use_cache = cache_cfg.get("enabled", True)
    key = make_key(query) if use_cache else None
    cache_dir = _cache_dir(cfg) if use_cache else None
    if use_cache:
        hit = cache.cache_get(cache_dir, key)
        if hit is not None:
            return hit

    wd = cfg["wikidata"]
    headers = {
        "User-Agent": wd["user_agent"],
        "Accept": "application/sparql-results+json",
    }
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(
                wd["endpoint"],
                params={"query": query, "format": "json"},
                headers=headers,
                timeout=wd.get("timeout", 60),
            )
        except requests.RequestException as exc:  # réseau
            last_exc = exc
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            rows = _simplify(r.json())
            if use_cache:
                cache.cache_set(cache_dir, key, rows)
            return rows
        if r.status_code in (429, 500, 502, 503, 504):
            backoff = 2 ** attempt
            if r.status_code == 429:
                backoff = _retry_after(r, default=backoff)
            time.sleep(backoff)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Echec de la requete SPARQL apres {retries} tentatives ({last_exc})")


def _retry_after(resp: requests.Response, default: float) -> float:
    """Durée d'attente déduite de l'en-tête Retry-After (sinon `default`).

    Gère le format delta-secondes ainsi que le format HTTP-date.
    """
    value = resp.headers.get("Retry-After")
    if not value:
        return default
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        from datetime import datetime, timezone

        when = parsedate_to_datetime(value)
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        pass
    return default


def _simplify(payload: dict) -> list[dict]:
    rows = []
    for binding in payload["results"]["bindings"]:
        rows.append({k: v.get("value") for k, v in binding.items()})
    return rows


def _sparql_literal(value: str) -> str:
    """Neutralise une valeur utilisateur insérée dans un littéral SPARQL entre guillemets.

    Échappe d'abord le backslash, puis le guillemet double, et supprime les
    retours à la ligne et autres caractères de contrôle (qui termineraient ou
    casseraient le littéral).
    """
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = "".join(ch for ch in s if ch == " " or unicodedata.category(ch)[0] != "C")
    return s.strip()


def lookup_film(title: str, cfg: dict, limit: int = 12) -> list[dict]:
    """Cherche des films Wikidata correspondant à un titre (via l'API EntitySearch).

    En plus de ?filmLabel, deux champs OPTIONNELS sont renvoyés pour faciliter
    l'appariement des titres localisés ou originaux :
      - ?title : titre officiel (wdt:P1476), agrégé par GROUP_CONCAT (un film peut
        porter plusieurs titres officiels, p.ex. plusieurs langues) ;
      - ?altLabels : noms alternatifs (skos:altLabel) dans la langue configurée et
        en anglais, agrégés (GROUP_CONCAT DISTINCT) et séparés par '|'.
    Ces clés peuvent être absentes/vides si le film ne déclare pas ces valeurs.
    """
    safe = _sparql_literal(title)
    lang = _sparql_literal(cfg.get("language", "fr"))
    query = PREFIXES + f"""
    SELECT ?film ?filmLabel ?imdb
           (SAMPLE(?date) AS ?date)
           (GROUP_CONCAT(DISTINCT ?ti; separator="|") AS ?title)
           (GROUP_CONCAT(DISTINCT ?al; separator="|") AS ?altLabels)
    WHERE {{
      SERVICE wikibase:mwapi {{
        bd:serviceParam wikibase:api "EntitySearch" .
        bd:serviceParam wikibase:endpoint "www.wikidata.org" .
        bd:serviceParam mwapi:search "{safe}" .
        bd:serviceParam mwapi:language "{lang}" .
        ?film wikibase:apiOutputItem mwapi:item .
      }}
      ?film wdt:P31 wd:{FILM_QID} .
      OPTIONAL {{ ?film wdt:P577 ?date . }}
      OPTIONAL {{ ?film wdt:P345 ?imdb . }}
      OPTIONAL {{ ?film wdt:P1476 ?ti . }}
      OPTIONAL {{
        ?film skos:altLabel ?al .
        FILTER(lang(?al) = "{lang}" || lang(?al) = "en")
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }}
    }}
    GROUP BY ?film ?filmLabel ?imdb
    LIMIT {limit}
    """
    return run_sparql(query, cfg)


def fetch_catalog_by_year(year: int, cfg: dict) -> list[dict]:
    """Récupère les films d'une année donnée avec leurs métadonnées agrégées."""
    lang = cfg.get("language", "fr")
    maxn = cfg["catalog"].get("max_per_year", 1500)
    query = PREFIXES + f"""
    SELECT ?film ?filmLabel ?imdb
           (SAMPLE(?date) AS ?date)
           (SAMPLE(?sl) AS ?popularity)
           (GROUP_CONCAT(DISTINCT ?g; separator="|") AS ?genres)
           (GROUP_CONCAT(DISTINCT ?d; separator="|") AS ?directors)
           (GROUP_CONCAT(DISTINCT ?c; separator="|") AS ?countries)
           (GROUP_CONCAT(DISTINCT ?a; separator="|") AS ?cast)
           (GROUP_CONCAT(DISTINCT ?k; separator="|") AS ?keywords)
           (GROUP_CONCAT(DISTINCT ?lg; separator="|") AS ?languages)
           (SAMPLE(?dur) AS ?duration)
    WHERE {{
      ?film wdt:P31 wd:{FILM_QID} ; wdt:P577 ?date .
      FILTER(YEAR(?date) = {int(year)})
      OPTIONAL {{ ?film wikibase:sitelinks ?sl . }}
      OPTIONAL {{ ?film wdt:P136 ?gi . ?gi rdfs:label ?g . FILTER(lang(?g)="{lang}") }}
      OPTIONAL {{ ?film wdt:P57 ?di . ?di rdfs:label ?d . FILTER(lang(?d)="{lang}") }}
      OPTIONAL {{ ?film wdt:P495 ?ci . ?ci rdfs:label ?c . FILTER(lang(?c)="{lang}") }}
      OPTIONAL {{ ?film wdt:P161 ?ai . ?ai rdfs:label ?a . FILTER(lang(?a)="{lang}") }}
      OPTIONAL {{ ?film wdt:P921 ?ki . ?ki rdfs:label ?k . FILTER(lang(?k)="{lang}") }}
      OPTIONAL {{ ?film wdt:P364 ?lgi . ?lgi rdfs:label ?lg . FILTER(lang(?lg)="{lang}") }}
      OPTIONAL {{ ?film wdt:P2047 ?dur . }}
      OPTIONAL {{ ?film wdt:P345 ?imdb . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }}
    }}
    GROUP BY ?film ?filmLabel ?imdb
    ORDER BY DESC(?popularity)
    LIMIT {maxn}
    """
    return run_sparql(query, cfg)


def fetch_items_metadata(qids: list[str], cfg: dict) -> list[dict]:
    """Récupère les métadonnées d'un ensemble de films identifiés par leur QID."""
    lang = cfg.get("language", "fr")
    out: list[dict] = []
    for batch in _chunks(list(qids), 150):
        values = " ".join(f"wd:{q}" for q in batch)
        query = PREFIXES + f"""
        SELECT ?film ?filmLabel ?imdb
               (SAMPLE(?date) AS ?date)
               (SAMPLE(?sl) AS ?popularity)
               (GROUP_CONCAT(DISTINCT ?g; separator="|") AS ?genres)
               (GROUP_CONCAT(DISTINCT ?d; separator="|") AS ?directors)
               (GROUP_CONCAT(DISTINCT ?c; separator="|") AS ?countries)
               (GROUP_CONCAT(DISTINCT ?a; separator="|") AS ?cast)
               (GROUP_CONCAT(DISTINCT ?k; separator="|") AS ?keywords)
               (GROUP_CONCAT(DISTINCT ?lg; separator="|") AS ?languages)
               (SAMPLE(?dur) AS ?duration)
        WHERE {{
          VALUES ?film {{ {values} }}
          OPTIONAL {{ ?film wdt:P577 ?date . }}
          OPTIONAL {{ ?film wikibase:sitelinks ?sl . }}
          OPTIONAL {{ ?film wdt:P136 ?gi . ?gi rdfs:label ?g . FILTER(lang(?g)="{lang}") }}
          OPTIONAL {{ ?film wdt:P57 ?di . ?di rdfs:label ?d . FILTER(lang(?d)="{lang}") }}
          OPTIONAL {{ ?film wdt:P495 ?ci . ?ci rdfs:label ?c . FILTER(lang(?c)="{lang}") }}
          OPTIONAL {{ ?film wdt:P161 ?ai . ?ai rdfs:label ?a . FILTER(lang(?a)="{lang}") }}
          OPTIONAL {{ ?film wdt:P921 ?ki . ?ki rdfs:label ?k . FILTER(lang(?k)="{lang}") }}
          OPTIONAL {{ ?film wdt:P364 ?lgi . ?lgi rdfs:label ?lg . FILTER(lang(?lg)="{lang}") }}
          OPTIONAL {{ ?film wdt:P2047 ?dur . }}
          OPTIONAL {{ ?film wdt:P345 ?imdb . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }}
        }}
        GROUP BY ?film ?filmLabel ?imdb
        """
        out.extend(run_sparql(query, cfg))
    return out


def get_wikipedia_titles(qids: list[str], cfg: dict) -> dict[str, str]:
    """Renvoie {qid: titre_article_wikipedia} pour la langue configurée."""
    lang = cfg.get("language", "fr")
    mapping: dict[str, str] = {}
    for batch in _chunks(list(qids), 180):
        values = " ".join(f"wd:{q}" for q in batch)
        query = PREFIXES + f"""
        SELECT ?film ?title WHERE {{
          VALUES ?film {{ {values} }}
          ?article schema:about ?film ;
                   schema:isPartOf <https://{lang}.wikipedia.org/> ;
                   schema:name ?title .
        }}
        """
        for row in run_sparql(query, cfg):
            qid = row["film"].rsplit("/", 1)[-1]
            mapping[qid] = row["title"]
    return mapping
