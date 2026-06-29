"""Pont (bridge) entre SwipeNight et le moteur movie-reco (movreco).

Ce module est le COEUR DE LA SYNERGIE entre les deux projets : il remplace
TMDB/seed comme source de catalogue et de scoring par le moteur licence-clean de
movie-reco (métadonnées Wikidata CC0 + synopsis Wikipedia CC BY-SA, stockés sous
forme d'embeddings). Il conserve l'apport propre de SwipeNight pour les ROOMS
multi-utilisateurs en réutilisant ``recommender.group_score``.

Principes :
- Pur Python, AUCUNE dépendance à MongoDB, à TMDB, ni à torch. On n'appelle
  JAMAIS ``movreco.features.embeddings.embed`` (qui, lui, peut tirer
  ``sentence_transformers``). On lit uniquement des artefacts déjà produits.
- Le paquet ``movreco`` n'est PAS pip-installé : on l'importe en ajoutant le
  dossier ``movie-reco`` (frère de ``swipe-movie``) en tête de ``sys.path``.
  movreco n'importe les libs lourdes que dans la fonction ``embed`` ; importer
  ``recommend``/``model``/``api.service`` reste léger.
- On NE MODIFIE PAS movie-reco : on réutilise strictement son API publique
  (``load_state``, ``pipeline.recommend``, ``taste_vector``, ``active``).
- Messages et docstrings en français, conventions movreco respectées.

Contrat exposé (cf. plan d'intégration §3.3) :
- ``SWIPE_TO_RATING`` : table de conversion geste de swipe -> note movreco.
- ``SynergyEngine`` : façade chargée une fois, exposant catalogue, recommandation
  individuelle, recommandation de room (group_score), calibration et statut.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Insertion de movie-reco dans sys.path (movreco n'est pas pip-installé).
# Ce fichier vit dans swipe-movie/backend/ ; movie-reco est le frère de
# swipe-movie, donc deux niveaux au-dessus puis /movie-reco. On insère en TÊTE
# pour que ``import movreco`` résolve ce paquet local, sans rien installer.
# --------------------------------------------------------------------------- #
import sys
from pathlib import Path

_MOVRECO_ROOT = Path(__file__).resolve().parents[2] / "movie-reco"
if _MOVRECO_ROOT.exists() and str(_MOVRECO_ROOT) not in sys.path:
    sys.path.insert(0, str(_MOVRECO_ROOT))

from typing import Any

import numpy as np

# Import léger du moteur de groupe propre à SwipeNight (réutilisé pour les rooms).
# ``recommender`` est dans le même dossier (backend) ; on le rend importable que
# le bridge soit chargé en module top-level (server.py) ou en package.
try:  # pragma: no cover - dépend du contexte d'import
    from . import recommender as _swipe_reco
except ImportError:  # pragma: no cover
    _backend_dir = str(Path(__file__).resolve().parent)
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)
    import recommender as _swipe_reco


# --------------------------------------------------------------------------- #
# Table de conversion geste de swipe -> note movreco [0..5].
# veto n'est PAS une note : c'est une exclusion dure (cf. swipes_to_ratings).
# neutral -> None : aucune note produite (ignoré).
# --------------------------------------------------------------------------- #
SWIPE_TO_RATING: dict[str, float | None] = {
    "superlike": 5.0,
    "like": 4.5,
    "watchlist": 4.0,
    "neutral": None,
    "dislike": 2.0,
    "abandoned": 1.5,
}

# Action de swipe qui déclenche une exclusion dure (jamais une note).
_VETO_ACTION = "veto"


def _split_pipe(value: Any) -> list[str]:
    """Découpe une colonne '|'-séparée en liste (vide si NaN/None/'').

    Réplique la sémantique de ``movreco.api.service._split_pipe`` sans importer
    de privé : tolérant aux valeurs manquantes (NaN pandas, None, chaîne vide).
    """
    if value is None:
        return []
    # NaN flottant pandas : value != value est vrai uniquement pour NaN.
    if isinstance(value, float) and value != value:
        return []
    return [t for t in str(value).split("|") if t]


def _year_of(value: Any) -> int | None:
    """Extrait une année (int) depuis une valeur de colonne ``date``.

    Tolérant : renvoie None si la date est absente/illisible. On évite toute
    dépendance à pandas ici en tentant plusieurs formats courants.
    """
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    # Objets datetime/Timestamp exposent .year.
    year = getattr(value, "year", None)
    if isinstance(year, int):
        return year
    s = str(value).strip()
    if not s:
        return None
    # Format ISO ou "YYYY..." : les 4 premiers caractères numériques.
    head = s[:4]
    if head.isdigit():
        return int(head)
    return None


def _content_id(swipe: dict) -> str | None:
    """Extrait l'identifiant de contenu d'un swipe (``content_id`` ou ``qid``)."""
    cid = swipe.get("content_id", swipe.get("qid"))
    if cid is None:
        return None
    cid = str(cid)
    return cid or None


class SynergyEngine:
    """Façade in-process reliant SwipeNight au moteur movie-reco.

    Charge l'état movreco une fois (catalogue + embeddings alignés) via
    ``movreco.api.service.load_state`` et expose des opérations façon SwipeNight :
    catalogue, recommandation individuelle, recommandation de room (group_score),
    calibration (apprentissage actif) et statut du fournisseur de données.

    L'instance est destinée à être créée une fois au démarrage du backend
    (``SynergyEngine.load()``) puis partagée en lecture seule entre requêtes.
    """

    def __init__(self, state: Any) -> None:
        """Initialise depuis un ``AppState`` movreco déjà chargé.

        Préférer la fabrique :func:`load`, qui valide la présence des artefacts.
        """
        self._state = state
        self._items = state.items
        self._emb = state.emb
        # Index qid -> position de ligne dans items/emb (alignés), pour un accès
        # O(1) lors du scoring des rooms. ``items["qid"]`` est aligné sur ``emb``.
        if self._items is not None:
            self._posmap: dict[str, int] = {
                str(q): i for i, q in enumerate(self._items["qid"].values)
            }
            self._labels: dict[str, str] = dict(
                zip(
                    (str(q) for q in self._items["qid"].values),
                    (str(l) for l in self._items["label"].values),
                )
            )
        else:  # pragma: no cover - écarté par load(), filet de sécurité
            self._posmap = {}
            self._labels = {}

    # ----------------------------------------------------------------------- #
    # Fabrique
    # ----------------------------------------------------------------------- #
    @classmethod
    def load(cls, cfg: dict | None = None) -> "SynergyEngine":
        """Charge le moteur depuis les artefacts movreco.

        Réutilise ``movreco.api.service.load_state`` (tolérant aux artefacts
        manquants), puis VÉRIFIE que catalogue ET embeddings sont présents : sans
        eux, aucune recommandation n'est possible. Lève alors une ``RuntimeError``
        claire indiquant la commande movreco à lancer.

        Paramètres
        ----------
        cfg : configuration movreco optionnelle. Si None, ``load_state`` charge la
            config par défaut (``movreco.config.load_config``). On peut surcharger
            ``cfg["paths"]["data_dir"]`` / ``["models_dir"]`` pour pointer un autre
            jeu d'artefacts (utile en test).

        Lève
        ----
        RuntimeError
            Si les items (catalogue) ou les embeddings sont absents.
        """
        # Imports légers (numpy/pandas seulement) ; aucun import lourd ici.
        from movreco.api import service as movreco_service

        if cfg is None:
            from movreco.config import load_config

            cfg = load_config()

        state = movreco_service.load_state(cfg)

        if state.items is None:
            raise RuntimeError(
                "Catalogue movie-reco indisponible : items.parquet manquant. "
                "Lancez le pipeline movreco (ingest -> synopsis -> embed -> "
                "features) pour produire le catalogue licence-clean."
            )
        if state.emb is None:
            raise RuntimeError(
                "Embeddings movie-reco indisponibles : embeddings.npy manquant "
                "ou désaligné. Lancez 'movreco embed' (backend tfidf, sans torch) "
                "pour produire les embeddings du catalogue."
            )
        return cls(state)

    # ----------------------------------------------------------------------- #
    # Statut du fournisseur
    # ----------------------------------------------------------------------- #
    def provider_status(self) -> dict:
        """Décrit la source de données du catalogue (licence-clean, sans TMDB).

        Renvoie un statut stable pour l'UI / l'endpoint providers de SwipeNight :
        source Wikidata + Wikipedia, TMDB désactivé, taille du catalogue, licence.
        """
        catalog_size = 0 if self._items is None else int(len(self._items))
        return {
            "source": "wikidata+wikipedia",
            "tmdb_enabled": False,
            "catalog_size": catalog_size,
            "license": "CC0 + CC BY-SA",
        }

    # ----------------------------------------------------------------------- #
    # Catalogue
    # ----------------------------------------------------------------------- #
    def catalog(self, limit: int | None = None) -> list[dict]:
        """Renvoie le catalogue au format contenu SwipeNight.

        Mappe chaque ligne d'``items`` movreco vers un dict de contenu attendu par
        le frontend SwipeNight. Les colonnes '|'-séparées (genres, directors,
        cast, keywords, languages) sont parsées en listes. ``id`` = qid Wikidata
        (le pivot d'intégration). ``source`` = "wikidata".

        Paramètres
        ----------
        limit : nombre maximal de contenus renvoyés (None = tout le catalogue).
        """
        if self._items is None:  # pragma: no cover - écarté par load()
            return []
        items = self._items
        if limit is not None:
            items = items.head(max(int(limit), 0))

        out: list[dict] = []
        for row in items.itertuples(index=False):
            d = row._asdict()
            _img = d.get("image")
            # Image Wikidata (P18) -> URL Commons mise à l'échelle : base "libre"
            # des covers (souvent une photo/scène plutôt qu'une affiche). TMDB peut
            # ensuite fournir la vraie affiche si activé (enrichissement, cf. server).
            _poster = f"{_img}?width=500" if isinstance(_img, str) and _img else None
            out.append(
                {
                    "id": str(d["qid"]),
                    "type": "movie",
                    "title": str(d["label"]),
                    "year": _year_of(d.get("date")),
                    "genres": _split_pipe(d.get("genres")),
                    "directors": _split_pipe(d.get("directors")),
                    "cast": _split_pipe(d.get("cast")),
                    "keywords": _split_pipe(d.get("keywords")),
                    "languages": _split_pipe(d.get("languages")),
                    "poster_url": _poster,
                    "source": "wikidata",
                }
            )
        return out

    # ----------------------------------------------------------------------- #
    # Conversion swipes -> notes
    # ----------------------------------------------------------------------- #
    def swipes_to_ratings(
        self, swipes: list[dict]
    ) -> tuple[list[str], list[float], list[str]]:
        """Convertit des swipes SwipeNight en entrées pour le moteur movreco.

        Chaque swipe est un dict ``{"content_id"|"qid": str, "action": str}``.
        - ``neutral`` (et toute action sans note dans :data:`SWIPE_TO_RATING`) est
          ignoré : ni note, ni exclusion.
        - ``veto`` -> exclusion dure : ajouté à ``exclude``, jamais noté.
        - les autres actions connues -> note via :data:`SWIPE_TO_RATING`.

        Un même contenu vu plusieurs fois : la DERNIÈRE action l'emporte (le swipe
        le plus récent reflète l'avis courant). Un veto sur un contenu prime sur
        toute note (il finit dans ``exclude`` et hors des notes).

        Retour
        ------
        (rated_qids, ratings, exclude)
            ``rated_qids`` et ``ratings`` sont alignés (même longueur) ;
            ``exclude`` liste les qids vetotés (dédupliqués, ordre d'apparition).
        """
        # On garde la dernière action par contenu pour rester déterministe.
        last_action: dict[str, str] = {}
        order: list[str] = []
        for swipe in swipes or []:
            cid = _content_id(swipe)
            if cid is None:
                continue
            action = str(swipe.get("action", "")).strip().lower()
            if cid not in last_action:
                order.append(cid)
            last_action[cid] = action

        rated_qids: list[str] = []
        ratings: list[float] = []
        exclude: list[str] = []
        seen_exclude: set[str] = set()

        for cid in order:
            action = last_action[cid]
            if action == _VETO_ACTION:
                if cid not in seen_exclude:
                    seen_exclude.add(cid)
                    exclude.append(cid)
                continue
            rating = SWIPE_TO_RATING.get(action)
            if rating is None:
                # neutral ou action inconnue : aucune note.
                continue
            rated_qids.append(cid)
            ratings.append(float(rating))

        return rated_qids, ratings, exclude

    # ----------------------------------------------------------------------- #
    # Recommandation individuelle
    # ----------------------------------------------------------------------- #
    def recommend_for_user(
        self,
        swipes: list[dict],
        n: int = 10,
        exclude: list[str] | None = None,
    ) -> list[dict]:
        """Recommande ``n`` contenus à un utilisateur d'après ses swipes.

        Mappe les swipes en notes (:meth:`swipes_to_ratings`), appelle
        ``movreco.recommend.pipeline.recommend`` en mode "mvp" (similarité au
        vecteur de goût, pas de modèle supervisé requis), puis renvoie une liste
        ``[{"id", "title", "score", "reasons"}]``.

        Exclusions : les contenus vetotés ET les contenus déjà swipés (notés)
        sont exclus du résultat, en plus de ``exclude`` fourni par l'appelant.

        Cas limites gérés (cf. contrat) :
        - utilisateur sans aucun like : le pipeline mvp tombe sur la moyenne des
          embeddings (repli interne movreco) -> recommandations « populaires/au
          centre du goût » plutôt qu'une erreur ;
        - qid inconnu du catalogue : ignoré silencieusement par le pipeline
          (filtré via la posmap interne) ;
        - aucun candidat : renvoie une liste vide.
        """
        from movreco.recommend.pipeline import recommend as movreco_recommend

        rated_qids, ratings, veto_exclude = self.swipes_to_ratings(swipes)

        # Exclusions = veto + déjà-swipés (notés) + exclude appelant. Les notés
        # sont déjà retirés par le pipeline, mais on les liste explicitement pour
        # un comportement robuste (et pour ne jamais re-proposer un film vu).
        excluded: list[str] = list(dict.fromkeys((exclude or []) + veto_exclude + rated_qids))

        cfg = self._cfg_with_top_n(n)

        result = movreco_recommend(
            self._items,
            self._emb,
            rated_qids,
            np.asarray(ratings, dtype=float),
            mode="mvp",
            structured=None,
            model=None,
            cfg=cfg,
            exclude=excluded,
            index_path=self._faiss_path(),
        )

        out: list[dict] = []
        for r in result.itertuples(index=False):
            d = r._asdict()
            out.append(
                {
                    "id": str(d["qid"]),
                    "title": str(d["label"]),
                    "score": float(d["score"]),
                    "reasons": self._reasons_for(str(d["qid"]), rated_qids),
                }
            )
        return out

    # ----------------------------------------------------------------------- #
    # Recommandation de room (SYNERGIE group_score)
    # ----------------------------------------------------------------------- #
    def recommend_for_room(self, members: list[dict], n: int = 10) -> list[dict]:
        """Recommande ``n`` contenus à une room multi-utilisateurs.

        Pour CHAQUE candidat du catalogue (moins les déjà-vus et les vetos), on
        calcule le score INDIVIDUEL de chaque membre, puis on agrège via
        ``recommender.group_score`` (apport propre de SwipeNight) — c'est ici que
        le moteur movreco alimente le scoring de groupe de SwipeNight.

        Détail du score individuel par membre :
        - on construit son vecteur de goût signé avec
          ``signed_taste_vector(emb des films notés du membre, notes)`` ;
        - on projette sur l'embedding du candidat par cosinus
          (``cosine_scores``), ramené de [-1, 1] vers [0, 1] ;
        - un membre sans aucune note obtient un score neutre 0.5 (pas d'a priori).

        Exclusions : tout candidat vu (noté/swipé) par un membre est retiré ; un
        veto d'UN SEUL membre sur un candidat -> exclusion dure de ce candidat
        pour toute la room.

        Paramètres
        ----------
        members : liste de ``{"user": str, "swipes": [...]}``.
        n : taille du top renvoyé.

        Retour
        ------
        list[dict]
            top-n trié par ``group_score`` décroissant :
            ``[{"id", "title", "group_score", "components"}]``.
        """
        # 1) Vecteur de goût par membre + ensemble des exclusions de la room.
        member_vectors: list[np.ndarray | None] = []
        seen_any: set[str] = set()  # contenus vus par au moins un membre
        vetoed: set[str] = set()    # contenus vetotés par au moins un membre

        for member in members or []:
            rated_qids, ratings, veto_exclude = self.swipes_to_ratings(
                member.get("swipes", [])
            )
            vetoed.update(veto_exclude)
            seen_any.update(rated_qids)
            seen_any.update(veto_exclude)
            member_vectors.append(self._taste_vector(rated_qids, ratings))

        if not member_vectors:
            return []

        # 2) Candidats = catalogue moins (vus ∪ vetotés).
        cand_pos: list[int] = []
        cand_qids: list[str] = []
        for qid, pos in self._posmap.items():
            if qid in seen_any or qid in vetoed:
                continue
            cand_pos.append(pos)
            cand_qids.append(qid)
        if not cand_pos:
            return []

        cand_emb = self._emb[cand_pos]  # (n_cand, dim)

        # 3) Score individuel de chaque membre pour TOUS les candidats (matriciel).
        from movreco.model.taste_vector import cosine_scores

        # member_scores_per_cand[c] = liste des scores [0,1] des membres pour le
        # candidat c. On calcule par membre (cosinus matriciel) puis on transpose.
        per_member_scores: list[np.ndarray] = []
        for vec in member_vectors:
            if vec is None:
                # Membre sans note : score neutre pour tous les candidats.
                scores = np.full(len(cand_pos), 0.5, dtype=float)
            else:
                cos = cosine_scores(vec, cand_emb)  # [-1, 1]
                scores = (np.asarray(cos, dtype=float) + 1.0) / 2.0  # -> [0, 1]
                scores = np.clip(scores, 0.0, 1.0)
            per_member_scores.append(scores)

        score_matrix = np.vstack(per_member_scores)  # (n_members, n_cand)

        # 4) Agrégation group_score par candidat (aucun veto ici : déjà exclus).
        scored: list[tuple[float, str, dict]] = []
        for j, qid in enumerate(cand_qids):
            member_scores = [float(score_matrix[m, j]) for m in range(score_matrix.shape[0])]
            gs, comp = _swipe_reco.group_score(member_scores, veto_count=0)
            scored.append((gs, qid, comp))

        # 5) Tri décroissant par group_score, départage déterministe par qid.
        scored.sort(key=lambda t: (-t[0], t[1]))
        top = scored[: max(int(n), 0)]

        return [
            {
                "id": qid,
                "title": self._labels.get(qid, ""),
                "group_score": float(gs),
                "components": comp,
            }
            for gs, qid, comp in top
        ]

    # ----------------------------------------------------------------------- #
    # Calibration (apprentissage actif)
    # ----------------------------------------------------------------------- #
    def calibration_titles(self, n: int = 20) -> list[dict]:
        """Propose ``n`` titres à noter pour la calibration d'onboarding.

        Réutilise ``movreco.model.active.suggest_to_rate`` (échantillonnage du
        point le plus éloigné) avec un historique vide : on couvre au mieux
        l'espace des goûts plutôt que de proposer des titres « populaires
        aléatoires ». Renvoie ``[{"id", "title"}]``.
        """
        from movreco.model import active

        qids = [str(q) for q in self._items["qid"].values]
        # popularité optionnelle (proxy sitelinks Wikidata), si la colonne existe.
        popularity = None
        if "popularity" in self._items.columns:
            popularity = (
                np.nan_to_num(
                    self._items["popularity"].to_numpy(dtype=float, na_value=0.0),
                    nan=0.0,
                )
            )
        lambda_pop = float(
            (self._state.cfg.get("active", {}) or {}).get("lambda_pop", 0.0) or 0.0
        )

        suggestions = active.suggest_to_rate(
            self._emb,
            qids,
            [],  # aucun film déjà noté en onboarding
            n=int(n),
            popularity=popularity,
            lambda_pop=lambda_pop,
        )
        return [
            {"id": str(qid), "title": self._labels.get(str(qid), "")}
            for qid in suggestions
        ]

    # ----------------------------------------------------------------------- #
    # Helpers internes
    # ----------------------------------------------------------------------- #
    def _taste_vector(
        self, rated_qids: list[str], ratings: list[float]
    ) -> np.ndarray | None:
        """Vecteur de goût signé d'un membre (None si aucune note appariée).

        Aligne les notes sur les embeddings via la posmap interne, puis appelle
        ``signed_taste_vector``. Renvoie None si aucun film noté n'est connu du
        catalogue (le membre sera traité en score neutre par la room).
        """
        from movreco.model.taste_vector import signed_taste_vector

        rows: list[int] = []
        aligned_ratings: list[float] = []
        for qid, rating in zip(rated_qids, ratings):
            pos = self._posmap.get(qid)
            if pos is not None:
                rows.append(pos)
                aligned_ratings.append(float(rating))
        if not rows:
            return None
        return signed_taste_vector(self._emb[rows], np.asarray(aligned_ratings, dtype=float))

    def _reasons_for(self, qid: str, rated_qids: list[str]) -> list[str]:
        """Construit des raisons courtes, déterministes, pour une reco individuelle.

        Raisons légères basées sur les métadonnées CC0 (genres) : pas d'appel LLM
        (movreco.llm reste optionnel/désactivé) et pas de note externe. Si aucun
        signal exploitable, une raison générique licence-clean est renvoyée.
        """
        reasons: list[str] = []
        pos = self._posmap.get(qid)
        if pos is not None and self._items is not None:
            row = self._items.iloc[pos]
            genres = _split_pipe(row.get("genres"))
            if genres:
                reasons.append(
                    "Correspond à vos goûts : " + ", ".join(genres[:2]) + "."
                )
        if rated_qids:
            reasons.append("Recommandé d'après les films que vous avez aimés.")
        else:
            reasons.append("Sélection pour démarrer (catalogue Wikidata).")
        return reasons[:3]

    def _cfg_with_top_n(self, n: int) -> dict:
        """Copie superficielle de la config movreco avec ``recommend.top_n = n``.

        Ne mute jamais l'état partagé : ``pipeline.recommend`` lit
        ``cfg["recommend"]["top_n"]`` pour dimensionner le top renvoyé.
        """
        cfg = dict(self._state.cfg)
        rc = dict(cfg.get("recommend", {}) or {})
        rc["top_n"] = int(n)
        cfg["recommend"] = rc
        return cfg

    def _faiss_path(self) -> str | None:
        """Chemin d'index FAISS persistant (cache), si défini dans les paths."""
        return self._state.paths.get("faiss")
