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
    """Status payload describing external-data availability and why."""
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
    }
