"""API FastAPI d'intégration SwipeNight x movreco (SYNERGIE, sans Mongo).

Cette application MINIMALE expose le moteur de recommandation et le catalogue
*licence-clean* de movreco (métadonnées Wikidata CC0 + synopsis Wikipedia
CC BY-SA) à travers le pont :class:`recommender_bridge.SynergyEngine`. Elle ne
dépend PAS de MongoDB et n'importe AUCUNE source TMDB/seed : le catalogue et le
scoring proviennent intégralement de movreco, tandis que l'apport propre de
SwipeNight (rooms multi-utilisateurs via ``recommender.group_score``) est conservé.

Découpage volontaire :
- ``server.py`` (couplé Mongo) n'est PAS touché : cette app est un module en plus.
- FastAPI n'est importé que dans :func:`create_app` (convention movreco : garder
  l'import du module léger ; les libs lourdes restent dans les fonctions appelées).
- :class:`recommender_bridge.SynergyEngine` est importé paresseusement dans le
  lifespan : le module s'importe proprement même si le pont (ou ses artefacts)
  n'est pas encore disponible.

Démarrage tolérant : si les artefacts movreco (items/embeddings) sont absents,
``SynergyEngine.load`` lève ``RuntimeError``. Le lifespan capture cette erreur,
laisse ``app.state.engine`` à ``None`` et l'app démarre quand même ; les endpoints
qui exploitent les données renvoient alors un 503 avec un message en français.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# pydantic est léger (déjà tiré par FastAPI) : on définit les schémas au niveau
# module pour que FastAPI résolve les annotations de corps des endpoints même
# avec ``from __future__ import annotations``.
from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typage statique uniquement
    from fastapi import FastAPI


# --------------------------------------------------------------------------- #
# Schémas d'entrée (Pydantic)
# --------------------------------------------------------------------------- #
class Swipe(BaseModel):
    """Un swipe utilisateur : identifiant de contenu (qid movreco) + action.

    Le pont accepte indifféremment ``qid`` ou ``content_id`` ; on expose ``qid``
    comme clé canonique et ``content_id`` comme alias rétro-compatible. L'action
    est mappée en note via ``SWIPE_TO_RATING`` (``veto`` -> exclusion dure).
    """

    qid: str | None = Field(
        default=None, description="Identifiant Wikidata du contenu (ex. Q12345)."
    )
    content_id: str | None = Field(
        default=None, description="Alias de qid (compat SwipeNight)."
    )
    action: str = Field(
        ...,
        description=(
            "Action de swipe : superlike, like, watchlist, neutral, dislike, "
            "abandoned, ou veto (exclusion dure)."
        ),
    )


class RecommendationsRequest(BaseModel):
    """Corps de POST /api/recommendations : swipes d'un utilisateur (stateless)."""

    swipes: list[Swipe] = Field(
        default_factory=list, description="Historique de swipes de l'utilisateur."
    )
    n: int = Field(
        10, ge=1, description="Nombre de recommandations souhaitées (>= 1)."
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="qids à exclure en plus des veto et déjà-swipés.",
    )


class RoomMember(BaseModel):
    """Un membre d'une room : son pseudo et ses swipes."""

    user: str = Field(..., description="Identifiant/pseudo du membre.")
    swipes: list[Swipe] = Field(
        default_factory=list, description="Swipes du membre."
    )


class RoomRecommendRequest(BaseModel):
    """Corps de POST /api/rooms/recommend : membres d'une room multi-utilisateurs."""

    members: list[RoomMember] = Field(
        default_factory=list, description="Membres votants de la room."
    )
    n: int = Field(
        10, ge=1, description="Nombre de recommandations de groupe souhaitées (>= 1)."
    )


# --------------------------------------------------------------------------- #
# Fabrique de l'application
# --------------------------------------------------------------------------- #
def create_app(cfg: dict | None = None) -> "FastAPI":
    """Construit l'app FastAPI d'intégration exposant la synergie via le pont.

    Le lifespan tente ``SynergyEngine.load(cfg)`` et place le moteur sur
    ``app.state.engine`` (ou ``None`` si les artefacts movreco sont absents :
    démarrage tolérant). Les endpoints délèguent au pont et traduisent l'absence
    de moteur en HTTP 503 (message FR). Les corps invalides sont rejetés en 422
    par FastAPI/pydantic.

    Paramètres
    ----------
    cfg : configuration movreco optionnelle (injectée en test). Si ``None``, le
        pont utilisera ``movreco.config.load_config`` via ``load_state``.
    """
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, HTTPException, Query

    @asynccontextmanager
    async def lifespan(app: "FastAPI"):
        # Import paresseux du pont : isole l'app d'une éventuelle indisponibilité
        # du module ``recommender_bridge`` au moment de l'import (Équipe 1).
        from recommender_bridge import SynergyEngine

        try:
            # Chargement UNIQUE du moteur movreco au démarrage.
            app.state.engine = SynergyEngine.load(cfg)
        except RuntimeError as exc:
            # Artefacts movreco manquants : démarrage tolérant. On mémorise la
            # cause pour la restituer telle quelle dans les 503 (message FR du pont).
            app.state.engine = None
            app.state.engine_error = str(exc)
        else:
            app.state.engine_error = None
        yield

    app = FastAPI(
        title="SwipeNight x movreco — API d'intégration (synergie)",
        description=(
            "API minimale sans Mongo exposant le catalogue licence-clean "
            "(Wikidata CC0 + Wikipedia CC BY-SA) et le moteur de recommandation "
            "movreco, avec les rooms multi-utilisateurs de SwipeNight "
            "(group_score). Aucune source TMDB."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    def _require_engine():
        """Renvoie le moteur chargé, ou lève une 503 (message FR) s'il est absent.

        L'absence de moteur signifie que les artefacts movreco (items/embeddings)
        n'ont pas pu être chargés au démarrage. On restitue le message du pont
        quand il est disponible.
        """
        engine = getattr(app.state, "engine", None)
        if engine is None:
            detail = getattr(app.state, "engine_error", None) or (
                "Moteur de recommandation indisponible : artefacts movreco "
                "(items/embeddings) absents. Lancez le pipeline movreco "
                "(ingest -> embed) puis redémarrez."
            )
            raise HTTPException(status_code=503, detail=detail)
        return engine

    # ----------------------------------------------------------------------- #
    # GET /api/provider-status — provenance et conformité de licence
    # ----------------------------------------------------------------------- #
    @app.get("/api/provider-status")
    def provider_status() -> dict:
        engine = _require_engine()
        return engine.provider_status()

    # ----------------------------------------------------------------------- #
    # GET /api/catalog — catalogue façon SwipeNight depuis movreco
    # ----------------------------------------------------------------------- #
    @app.get("/api/catalog")
    def catalog(
        limit: int = Query(
            default=50,
            ge=0,
            description="Nombre maximal de contenus renvoyés (0 = aucun).",
        ),
    ) -> dict:
        engine = _require_engine()
        return {"results": engine.catalog(limit=limit)}

    # ----------------------------------------------------------------------- #
    # POST /api/recommendations — recommandations individuelles depuis les swipes
    # ----------------------------------------------------------------------- #
    @app.post("/api/recommendations")
    def recommendations(req: RecommendationsRequest) -> dict:
        engine = _require_engine()
        # Le pont accepte des dicts {"qid"|"content_id", "action"} : on transmet
        # le modèle pydantic sérialisé pour rester fidèle au contrat du pont.
        swipes = [s.model_dump(exclude_none=True) for s in req.swipes]
        results = engine.recommend_for_user(
            swipes, n=req.n, exclude=req.exclude or None
        )
        return {"results": results}

    # ----------------------------------------------------------------------- #
    # POST /api/rooms/recommend — recommandations de groupe (group_score)
    # ----------------------------------------------------------------------- #
    @app.post("/api/rooms/recommend")
    def rooms_recommend(req: RoomRecommendRequest) -> dict:
        engine = _require_engine()
        members = [
            {
                "user": m.user,
                "swipes": [s.model_dump(exclude_none=True) for s in m.swipes],
            }
            for m in req.members
        ]
        results = engine.recommend_for_room(members, n=req.n)
        return {"results": results}

    # ----------------------------------------------------------------------- #
    # GET /api/calibration — films à proposer en priorité à la notation
    # ----------------------------------------------------------------------- #
    @app.get("/api/calibration")
    def calibration(
        n: int = Query(
            default=20, ge=1, description="Nombre de titres de calibration (>= 1)."
        ),
    ) -> dict:
        engine = _require_engine()
        return {"results": engine.calibration_titles(n=n)}

    return app


# Instance module exigée par le contrat (uvicorn "integrated_api:app").
# create_app() sans cfg => le pont chargera la config movreco par défaut.
app = create_app()
