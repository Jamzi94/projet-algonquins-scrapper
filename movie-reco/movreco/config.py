"""Chargement de la configuration et résolution des chemins de données."""
from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    """Charge config/config.yaml et renvoie un dictionnaire."""
    p = path or CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = str(ROOT)
    return cfg


def data_path(*parts: str) -> Path:
    """Construit un chemin sous data/."""
    return ROOT / "data" / Path(*parts)


def paths(cfg: dict | None = None) -> dict:
    """Emplacements canoniques des artefacts produits par le pipeline."""
    return {
        "items": data_path("processed", "items.parquet"),
        "rated": data_path("processed", "rated.parquet"),
        "synopsis": data_path("raw", "synopsis.parquet"),
        "embeddings": data_path("processed", "embeddings.npy"),
        "emb_ids": data_path("processed", "embeddings_ids.json"),
        "structured": data_path("processed", "structured.parquet"),
        "faiss": ROOT / "models" / "catalog.faiss",
        "model": ROOT / "models" / "preference.joblib",
    }
