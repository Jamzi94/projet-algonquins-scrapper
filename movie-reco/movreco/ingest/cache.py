"""Cache disque simple (JSON) pour les appels réseau Wikidata/Wikipedia.

Évite de retoucher le réseau pour des requêtes/titres déjà récupérés. Chaque
entrée est un fichier `<key>.json` sous un dossier de cache donné. La lecture est
tolérante : un fichier absent ou corrompu renvoie simplement None (cache miss).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def make_key(text: str) -> str:
    """Clé de cache stable : sha256 hexdigest du texte (UTF-8)."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def cache_get(cache_dir: str | Path, key: str) -> Any | None:
    """Lit cache_dir/<key>.json et renvoie l'objet, ou None si absent/corrompu."""
    path = Path(cache_dir) / f"{key}.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        # fichier absent, illisible ou JSON invalide -> cache miss
        return None


def cache_set(cache_dir: str | Path, key: str, value: Any) -> None:
    """Écrit `value` (JSON UTF-8) dans cache_dir/<key>.json, créant le dossier."""
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{key}.json", "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
