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
    """Emplacements canoniques des artefacts produits par le pipeline.

    Surcharges optionnelles via cfg["paths"]["data_dir"] / ["models_dir"]
    (defauts : ROOT/data et ROOT/models).
    """
    paths_cfg = (cfg or {}).get("paths", {}) or {}
    data_dir = Path(paths_cfg.get("data_dir") or (ROOT / "data"))
    models_dir = Path(paths_cfg.get("models_dir") or (ROOT / "models"))
    return {
        "items": data_dir / "processed" / "items.parquet",
        "rated": data_dir / "processed" / "rated.parquet",
        "synopsis": data_dir / "raw" / "synopsis.parquet",
        "embeddings": data_dir / "processed" / "embeddings.npy",
        "emb_ids": data_dir / "processed" / "embeddings_ids.json",
        "structured": data_dir / "processed" / "structured.parquet",
        "cache": data_dir / "cache",
        "faiss": models_dir / "catalog.faiss",
        "model": models_dir / "preference.joblib",
    }
