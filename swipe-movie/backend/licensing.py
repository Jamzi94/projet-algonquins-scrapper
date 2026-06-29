"""
Commercial-mode / licensing guardrails for external API usage.

The app is a FREE NON-COMMERCIAL BETA by default. TMDB may be used only when:
  - EXTERNAL_APIS_ENABLED is true, and
  - a TMDB_API_KEY is configured, and
  - either COMMERCIAL_MODE is false, or TMDB_COMMERCIAL_LICENSE_CONFIRMED is true.

Always call can_use_tmdb() before any TMDB request.
"""
import os


def _flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def external_apis_enabled() -> bool:
    return _flag("EXTERNAL_APIS_ENABLED", "true")


def is_commercial_mode() -> bool:
    return _flag("COMMERCIAL_MODE", "false")


def tmdb_license_confirmed() -> bool:
    return _flag("TMDB_COMMERCIAL_LICENSE_CONFIRMED", "false")


def has_tmdb_key() -> bool:
    return bool(os.environ.get("TMDB_API_KEY", "").strip())


def can_use_tmdb() -> bool:
    if not external_apis_enabled():
        return False
    if not has_tmdb_key():
        return False
    if is_commercial_mode() and not tmdb_license_confirmed():
        return False
    return True


# ---------------------------------------------------------------------------
# Interrupteur UNIFIÉ de source de données + toggles dérivés
# ---------------------------------------------------------------------------
# DATA_SOURCE est l'unique interrupteur de haut niveau qui choisit d'où vient le
# catalogue et quel moteur de recommandation est utilisé :
#   - "wikidata" (défaut) : catalogue Wikidata via le pont movie-reco, reco via le pont.
#   - "seed"              : catalogue mock embarqué (seed_data), reco native SwipeNight.
#   - "tmdb"              : base seed enrichie par TMDB (effectif seulement si can_use_tmdb()),
#                           reco native. TMDB reste activable/désactivable via ses propres
#                           variables (EXTERNAL_APIS_ENABLED / TMDB_API_KEY / COMMERCIAL_MODE /
#                           TMDB_COMMERCIAL_LICENSE_CONFIRMED), cf. can_use_tmdb().
# Les anciens toggles granulaires CATALOG_SOURCE / RECO_VIA_BRIDGE restent honorés
# (rétro-compatibilité) et, s'ils sont définis explicitement, ils PRIMENT sur DATA_SOURCE.
_DATA_SOURCES = {"wikidata", "seed", "tmdb"}
_CATALOG_SOURCES = {"movreco", "seed"}


def data_source() -> str:
    """Interrupteur unifié : "wikidata" (défaut) | "seed" | "tmdb".

    Accepte l'alias "movreco" pour "wikidata". Valeur absente/inconnue -> "wikidata".
    """
    value = os.environ.get("DATA_SOURCE", "wikidata").strip().lower()
    if value == "movreco":
        return "wikidata"
    return value if value in _DATA_SOURCES else "wikidata"


def catalog_source() -> str:
    """Source du catalogue de base : "movreco" (pont Wikidata) ou "seed".

    Dérivé de DATA_SOURCE ("wikidata" -> "movreco" ; "seed"/"tmdb" -> "seed"), sauf si
    CATALOG_SOURCE est défini EXPLICITEMENT (rétro-compat) auquel cas il prime.
    """
    raw = os.environ.get("CATALOG_SOURCE")
    if raw is not None and raw.strip().lower() in _CATALOG_SOURCES:
        return raw.strip().lower()
    return "movreco" if data_source() == "wikidata" else "seed"


def reco_via_bridge() -> bool:
    """Vrai si les endpoints de reco délèguent au pont movreco.

    Dérivé de DATA_SOURCE ("wikidata" -> True ; "seed"/"tmdb" -> False), sauf si
    RECO_VIA_BRIDGE est défini EXPLICITEMENT (rétro-compat) auquel cas il prime.
    """
    if os.environ.get("RECO_VIA_BRIDGE") is not None:
        return _flag("RECO_VIA_BRIDGE", "1")
    return data_source() == "wikidata"


def tmdb_disabled_reason() -> str | None:
    """Human-readable reason TMDB is disabled, or None if it's usable."""
    if not external_apis_enabled():
        return "EXTERNAL_APIS_ENABLED is false"
    if not has_tmdb_key():
        return "TMDB_API_KEY is not configured"
    if is_commercial_mode() and not tmdb_license_confirmed():
        return ("COMMERCIAL_MODE is true but TMDB_COMMERCIAL_LICENSE_CONFIRMED "
                "is false — a commercial TMDB license is required")
    return None


def get_provider_status() -> dict:
    """Status payload describing external-data availability and why.

    Expose aussi les toggles de SYNERGIE movie-reco (``catalog_source`` et
    ``reco_via_bridge``) en plus de l'état TMDB, afin que l'UI/les ops voient
    d'où viennent le catalogue et les recommandations.
    """
    usable = can_use_tmdb()
    return {
        "tmdb_enabled": usable,
        "external_apis_enabled": external_apis_enabled(),
        "commercial_mode": is_commercial_mode(),
        "tmdb_license_confirmed": tmdb_license_confirmed(),
        "tmdb_key_present": has_tmdb_key(),
        "seed_catalog_fallback": True,
        "reason": tmdb_disabled_reason(),
        "default_country": os.environ.get("DEFAULT_COUNTRY", "FR"),
        "default_language": os.environ.get("TMDB_DEFAULT_LANGUAGE", "fr-FR"),
        # Interrupteur unifié + toggles de synergie movie-reco dérivés.
        "data_source": data_source(),
        "catalog_source": catalog_source(),
        "reco_via_bridge": reco_via_bridge(),
        # Étendue de l'enrichissement TMDB : full (affiche + date/note réelles) | covers.
        "tmdb_enrich": os.environ.get("TMDB_ENRICH", "full").strip().lower(),
    }
