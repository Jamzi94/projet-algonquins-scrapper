"""Schémas Pydantic du service API (entrées/sorties des endpoints).

Conventions : messages en français, validation stricte (n >= 1). Ces modèles
décrivent EXACTEMENT le contrat d'API et restent indépendants du pipeline.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# Modes de scoring autorisés par le contrat d'API. Centralisé ici pour que le
# schéma POST (Literal) et le paramètre de requête GET (enum) restent cohérents.
Mode = Literal["mvp", "hybrid"]


class ModeEnum(str, Enum):
    """Modes de scoring valides pour les paramètres de requête (GET /recommend).

    FastAPI valide automatiquement un paramètre de requête typé par un Enum et
    renvoie 422 pour toute valeur hors de cet ensemble.
    """

    mvp = "mvp"
    hybrid = "hybrid"


# --------------------------------------------------------------------------- #
# Entrées
# --------------------------------------------------------------------------- #
class Rating(BaseModel):
    """Une note utilisateur : identifiant Wikidata du film + note."""

    qid: str = Field(..., description="Identifiant Wikidata du film (ex. Q12345).")
    rating: float = Field(..., description="Note attribuée par l'utilisateur.")


class RecommendRequest(BaseModel):
    """Corps de POST /recommend : notes d'un client, sans état serveur.

    Le moteur calcule un vecteur de goût à la volée (mode mvp) à partir de ces
    notes ; aucun réentraînement n'est nécessaire.
    """

    ratings: list[Rating] = Field(default_factory=list, description="Liste des notes.")
    mode: Mode = Field("mvp", description="Mode de scoring : 'mvp' ou 'hybrid'.")
    n: int = Field(10, ge=1, description="Nombre de recommandations souhaitées (>= 1).")
    exclude: list[str] = Field(
        default_factory=list, description="qids à exclure des résultats."
    )
    explain: bool = Field(
        False,
        description=(
            "Si vrai ET llm.enabled, attache une raison (champ 'raison') à chaque "
            "recommandation via la couche LLM. Ignoré silencieusement sinon."
        ),
    )


# --------------------------------------------------------------------------- #
# Sorties
# --------------------------------------------------------------------------- #
class MovieSummary(BaseModel):
    """Résumé d'un film pour la recherche (GET /movies)."""

    qid: str
    label: str
    year: int | None = None
    genres: list[str] = Field(default_factory=list)


class MovieDetail(BaseModel):
    """Détail d'un film (GET /movies/{qid})."""

    qid: str
    label: str
    year: int | None = None
    genres: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)


class ScoredMovie(BaseModel):
    """Film accompagné de son score (recommandation ou similarité).

    ``raison`` est une justification optionnelle (couche LLM) ; absente par
    défaut, donc rétro-compatible avec les clients existants.
    """

    qid: str
    label: str
    score: float
    raison: str | None = Field(
        default=None, description="Justification LLM optionnelle (si explain demandé)."
    )


class QueryMovie(BaseModel):
    """Film requête renvoyé par GET /movies/{qid}/similar."""

    qid: str
    label: str


class MoviesResponse(BaseModel):
    """Réponse de GET /movies."""

    results: list[MovieSummary] = Field(default_factory=list)


class SimilarResponse(BaseModel):
    """Réponse de GET /movies/{qid}/similar."""

    query: QueryMovie
    results: list[ScoredMovie] = Field(default_factory=list)


class RecommendResponse(BaseModel):
    """Réponse de GET/POST /recommend."""

    mode: str = Field(..., description="Mode réellement utilisé (peut différer du demandé).")
    results: list[ScoredMovie] = Field(default_factory=list)


class SuggestedMovie(BaseModel):
    """Film proposé à la notation (apprentissage actif)."""

    qid: str
    label: str


class SuggestResponse(BaseModel):
    """Réponse de GET /suggest (films à noter en priorité)."""

    results: list[SuggestedMovie] = Field(default_factory=list)


class HealthArtifacts(BaseModel):
    """Présence/volumétrie des artefacts chargés."""

    items: int = 0
    embeddings: bool = False
    structured: bool = False
    model: bool = False
    rated: int = 0


class HealthResponse(BaseModel):
    """Réponse de GET /health."""

    status: str = "ok"
    artifacts: HealthArtifacts = Field(default_factory=HealthArtifacts)
