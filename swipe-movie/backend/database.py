"""Connexion MongoDB (Motor). Client/db unique partagé par tout le backend.

SYNERGIE SANDBOX
----------------
Le backend a été codé avec Motor/Mongo (API ``db[col].find_one/insert_one...``).
Pour le rendre exécutable DANS la sandbox SANS serveur ``mongod``, ce module
choisit automatiquement le moteur :

- ``MONGO_URL`` absent OU dans ("", "memory", "mock", "memory://")
  -> Mongo EN MÉMOIRE via ``mongomock-motor`` (``AsyncMongoMockClient``),
     API STRICTEMENT identique à Motor (mêmes appels asynchrones).
- ``MONGO_URL`` défini sur une vraie URI (ex. ``mongodb://localhost:27017``)
  -> vrai Motor (``AsyncIOMotorClient``) : comportement d'origine, inchangé.

Les exports ``client`` et ``db`` ainsi que l'API restent EXACTEMENT les mêmes
dans les deux modes : l'app codée avec Mongo marche à l'identique si
``MONGO_URL`` est fourni (rétro-compatible).
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger("swipenight.database")

# Valeurs qui déclenchent le mode mémoire (mongomock-motor).
_MEMORY_SENTINELS = {"", "memory", "mock", "memory://"}

# MONGO_URL est OPTIONNEL : absent -> mode mémoire (sandbox). On NE plante PLUS
# avec un KeyError comme l'ancien ``os.environ["MONGO_URL"]``.
mongo_url = os.environ.get("MONGO_URL", "").strip()

# DB_NAME garde son défaut historique "swipenight".
db_name = os.environ.get("DB_NAME", "swipenight").strip() or "swipenight"

if mongo_url.lower() in _MEMORY_SENTINELS:
    # --- Mode MÉMOIRE : aucun mongod requis, idéal pour la sandbox/les tests. ---
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    db = client[db_name]
    logger.info(
        "MongoDB en MÉMOIRE (mongomock-motor) — DB_NAME=%r. "
        "Aucun serveur mongod requis. Définissez MONGO_URL pour un vrai Mongo.",
        db_name,
    )
else:
    # --- Mode RÉEL : vrai Motor, comportement d'origine inchangé. ---
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    logger.info(
        "MongoDB RÉEL (Motor) — MONGO_URL=%r, DB_NAME=%r.",
        mongo_url,
        db_name,
    )
