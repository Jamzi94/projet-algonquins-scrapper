"""Package API : service FastAPI exposant le moteur de recommandation movreco.

Point d'entrée : :func:`movreco.api.app.create_app` (et la variable module
``movreco.api.app.app``). Le service charge les artefacts du pipeline une seule
fois au démarrage (lifespan) puis rend le moteur disponible en HTTP, sans
réseau au moment des requêtes.
"""
from __future__ import annotations

__all__ = ["create_app", "app"]


def __getattr__(name: str):  # pragma: no cover - simple proxy paresseux
    # Import paresseux : ne tire FastAPI (dépendance extra) que si on accède
    # réellement à l'app, pas au simple import du package.
    if name in {"create_app", "app"}:
        from movreco.api.app import app, create_app

        return {"create_app": create_app, "app": app}[name]
    raise AttributeError(f"module {__name__!r} n'a pas d'attribut {name!r}")
