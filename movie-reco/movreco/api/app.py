"""Application FastAPI : câblage HTTP du moteur de recommandation movreco.

Ce module assemble l'API à partir de la couche métier (:mod:`movreco.api.service`)
et des schémas (:mod:`movreco.api.schemas`). Il ne réimplémente AUCUNE logique de
scoring : chaque endpoint délègue à une fonction de ``service`` opérant sur l'état
applicatif chargé une seule fois au démarrage (lifespan), puis stocké sur
``app.state``. Aucun réseau au moment des requêtes.

Conformément à CLAUDE.md, FastAPI (dépendance extra) n'est importé que dans
:func:`create_app`/le lifespan, jamais au niveau module, pour ne pas alourdir le
simple import du package.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# schemas ne dépend que de pydantic (léger, déjà requis par FastAPI) : on
# l'importe au niveau module pour que FastAPI puisse résoudre les annotations
# de corps/réponse des endpoints (sinon, avec `from __future__ import
# annotations`, RecommendRequest serait pris pour un paramètre de requête).
from movreco.api import schemas

if TYPE_CHECKING:  # pragma: no cover - uniquement pour le typage statique
    from fastapi import FastAPI


def create_app(cfg: dict | None = None) -> "FastAPI":
    """Construit l'application FastAPI exposant le moteur de recommandation.

    Le lifespan charge les artefacts du pipeline via :func:`service.load_state`
    (tolérant aux artefacts manquants) et place l'état résultant sur
    ``app.state.engine``. Les endpoints délèguent à la couche ``service`` et
    traduisent les exceptions métier en codes HTTP :
    :class:`service.ArtifactMissing` -> 503, :class:`service.InvalidRequest` -> 422.

    Paramètres
    ----------
    cfg : configuration optionnelle. Si ``None``, ``service.load_state`` utilisera
        :func:`movreco.config.load_config`. Permet l'injection en test.
    """
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, HTTPException, Query

    from movreco.api import service

    @asynccontextmanager
    async def lifespan(app: "FastAPI"):
        # Chargement UNIQUE des artefacts au démarrage. Tolérant : un artefact
        # manquant n'empêche pas le démarrage (endpoints concernés -> 503).
        from movreco.config import load_config

        app.state.engine = service.load_state(cfg or load_config())
        yield

    app = FastAPI(
        title="movreco — API de recommandation de films",
        description=(
            "Moteur de recommandation content-based mono-utilisateur exposé en "
            "service. POST /recommend est stateless (notes fournies par le client) ; "
            "GET /recommend utilise les notes persistées du propriétaire."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    def _state() -> service.AppState:
        """Récupère l'état applicatif chargé au démarrage."""
        return app.state.engine

    # ----------------------------------------------------------------------- #
    # /health
    # ----------------------------------------------------------------------- #
    @app.get("/health", response_model=schemas.HealthResponse)
    def health() -> schemas.HealthResponse:
        st = _state()
        arts = schemas.HealthArtifacts(
            items=int(len(st.items)) if st.items is not None else 0,
            embeddings=st.emb is not None,
            structured=st.structured is not None,
            model=st.model is not None,
            rated=int(len(st.rated)) if st.rated is not None else 0,
        )
        return schemas.HealthResponse(status="ok", artifacts=arts)

    # ----------------------------------------------------------------------- #
    # /movies (recherche)
    # ----------------------------------------------------------------------- #
    @app.get("/movies", response_model=schemas.MoviesResponse)
    def movies(
        q: str | None = Query(default=None, description="Sous-chaîne du titre (optionnel)."),
        limit: int = Query(default=20, ge=0, description="Nombre maximal de résultats."),
    ) -> schemas.MoviesResponse:
        try:
            results = service.search_movies(_state(), q=q, limit=limit)
        except service.ArtifactMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return schemas.MoviesResponse(results=results)

    # ----------------------------------------------------------------------- #
    # /movies/{qid} (détail)
    # ----------------------------------------------------------------------- #
    @app.get("/movies/{qid}", response_model=schemas.MovieDetail)
    def movie_detail(qid: str) -> schemas.MovieDetail:
        try:
            detail = service.get_movie(_state(), qid)
        except service.ArtifactMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Film inconnu : {qid}.")
        return schemas.MovieDetail(**detail)

    # ----------------------------------------------------------------------- #
    # /movies/{qid}/similar (voisins cosinus)
    # ----------------------------------------------------------------------- #
    @app.get("/movies/{qid}/similar", response_model=schemas.SimilarResponse)
    def movie_similar(
        qid: str,
        n: int = Query(default=10, ge=1, description="Nombre de voisins souhaités."),
    ) -> schemas.SimilarResponse:
        try:
            result = service.similar(_state(), qid, n=n)
        except service.ArtifactMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail=f"Film inconnu : {qid}.")
        return schemas.SimilarResponse(**result)

    # ----------------------------------------------------------------------- #
    # POST /recommend (stateless : notes du client)
    # ----------------------------------------------------------------------- #
    @app.post("/recommend", response_model=schemas.RecommendResponse)
    def post_recommend(req: schemas.RecommendRequest) -> schemas.RecommendResponse:
        ratings = [{"qid": r.qid, "rating": r.rating} for r in req.ratings]
        try:
            mode, results = service.recommend_from_ratings(
                _state(),
                ratings=ratings,
                mode=req.mode,
                n=req.n,
                exclude=req.exclude,
            )
        except service.ArtifactMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except service.InvalidRequest as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return schemas.RecommendResponse(mode=mode, results=results)

    # ----------------------------------------------------------------------- #
    # GET /recommend (notes persistées du propriétaire)
    # ----------------------------------------------------------------------- #
    @app.get("/recommend", response_model=schemas.RecommendResponse)
    def get_recommend(
        mode: schemas.ModeEnum = Query(
            default=schemas.ModeEnum.hybrid, description="Mode de scoring demandé."
        ),
        n: int = Query(default=10, ge=1, description="Nombre de recommandations."),
    ) -> schemas.RecommendResponse:
        try:
            effective, results = service.recommend_owner(
                _state(), mode=mode.value, n=n
            )
        except service.ArtifactMissing as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except service.InvalidRequest as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return schemas.RecommendResponse(mode=effective, results=results)

    return app


# Variable module exigée par le contrat (uvicorn "movreco.api.app:app", proxy
# paresseux de movreco/api/__init__.py). create_app() sans cfg => load_config().
app = create_app()
