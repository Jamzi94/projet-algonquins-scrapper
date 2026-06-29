"""Couche LLM optionnelle : re-ranking et explications du top-N via l'API Anthropic.

Désactivée par défaut. Activer dans config.yaml (llm.enabled: true) et fournir
ANTHROPIC_API_KEY dans .env. Ne sert jamais de moteur principal, seulement à
réordonner et expliquer un top-N déjà filtré par le pipeline.

Le paramètre ``client`` permet d'injecter un client compatible
(``client.messages.create(...)`` renvoyant un objet dont ``.content`` est une
liste d'objets ``(.type, .text)``) — utile pour les tests hors-ligne. Quand il
est fourni, on ne crée ni n'importe ``anthropic`` ; sinon on conserve le
comportement actuel (création du client si ``llm.enabled`` et ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import json
import os


def _build_client(cfg: dict):
    """Crée un client anthropic si la couche LLM est activée et la clé présente.

    Renvoie le client ou ``None`` (désactivée, pas de clé, ou import indisponible).
    L'import d'``anthropic`` reste local à la fonction (convention CLAUDE.md).
    """
    if not cfg.get("llm", {}).get("enabled"):
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None
    try:
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


def _message_text(message) -> str:
    """Concatène le texte des blocs de type ``text`` d'une réponse Anthropic."""
    try:
        blocks = message.content
    except Exception:
        return ""
    parts = []
    for b in blocks or []:
        if getattr(b, "type", None) == "text":
            txt = getattr(b, "text", None)
            if isinstance(txt, str):
                parts.append(txt)
    return "".join(parts).strip()


def _extract_first_json_array(text: str):
    """Extrait le PREMIER tableau JSON valide d'un texte arbitraire.

    Tolère le texte autour, les balises de code Markdown (```json ... ```), et
    les tableaux imbriqués. Parcourt le texte caractère par caractère, repère
    chaque ``[`` puis tente de décoder un tableau complet en suivant les niveaux
    d'accolades/crochets et en ignorant ce qui est entre guillemets. Renvoie la
    liste Python décodée, ou ``None`` si aucun tableau exploitable.
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    n = len(text)
    i = 0
    while i < n:
        if text[i] == "[":
            try:
                value, _ = decoder.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            if isinstance(value, list):
                return value
            # Décodage réussi mais pas une liste : on continue après ce point.
            i += 1
            continue
        i += 1
    return None


def _coerce_order(value) -> list[dict] | None:
    """Nettoie une liste brute en [{"index": int, "raison": str}, ...].

    Ignore silencieusement les entrées mal formées (non-dict, index absent ou
    non entier). Renvoie ``None`` si rien d'exploitable ne subsiste.
    """
    if not isinstance(value, list):
        return None
    out: list[dict] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("index")
        # bool est une sous-classe d'int : on l'exclut explicitement.
        if isinstance(idx, bool) or not isinstance(idx, int):
            continue
        raison = entry.get("raison", "")
        if not isinstance(raison, str):
            raison = "" if raison is None else str(raison)
        out.append({"index": idx, "raison": raison})
    return out or None


def rerank_and_explain(liked_titles, candidates, cfg: dict, client=None):
    """Réordonne et explique les candidats via le LLM.

    Renvoie une liste ``[{"index": int, "raison": str}]`` ou ``None`` si
    indisponible (couche désactivée, pas de clé, erreur réseau, réponse vide ou
    illisible).

    Args:
        liked_titles: titres des films aimés par l'utilisateur (contexte).
        candidates: titres des candidats à réordonner (l'index renvoyé pointe
            dans cette liste).
        cfg: configuration globale (utilise ``cfg["llm"]``).
        client: client optionnel injecté (pour les tests). Si fourni, il est
            utilisé tel quel ; sinon un client ``anthropic`` est créé selon la
            configuration.
    """
    if client is None:
        client = _build_client(cfg)
        if client is None:
            return None

    liked = "\n".join(f"- {t}" for t in list(liked_titles)[:40])
    cand = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates))
    prompt = (
        f"Voici des films aimes par l'utilisateur :\n{liked}\n\n"
        f"Candidats a recommander :\n{cand}\n\n"
        "Reordonne les candidats du plus au moins pertinent pour cet utilisateur. "
        'Reponds uniquement en JSON : une liste d\'objets {"index": int, "raison": "phrase courte"}.'
    )
    try:
        message = client.messages.create(
            model=cfg["llm"]["model"],
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None

    text = _message_text(message)
    parsed = _extract_first_json_array(text)
    return _coerce_order(parsed)


def explain(liked_titles, recommended_titles, cfg: dict, client=None) -> dict[int, str] | None:
    """Renvoie un dict {index -> raison} expliquant chaque recommandation.

    Variante de ``rerank_and_explain`` qui ne réordonne pas : on demande au LLM
    une courte justification par recommandation, dans l'ordre fourni. Renvoie
    ``None`` si la couche est indisponible ou la réponse illisible.

    Args:
        liked_titles: titres des films aimés (contexte).
        recommended_titles: titres déjà recommandés (l'index pointe dedans).
        cfg: configuration globale (utilise ``cfg["llm"]``).
        client: client optionnel injecté (pour les tests).
    """
    if client is None:
        client = _build_client(cfg)
        if client is None:
            return None

    liked = "\n".join(f"- {t}" for t in list(liked_titles)[:40])
    reco = "\n".join(f"{i}. {c}" for i, c in enumerate(recommended_titles))
    prompt = (
        f"Voici des films aimes par l'utilisateur :\n{liked}\n\n"
        f"Films recommandes :\n{reco}\n\n"
        "Pour chaque film recommande, donne une phrase courte expliquant pourquoi "
        "il pourrait plaire a cet utilisateur. "
        'Reponds uniquement en JSON : une liste d\'objets {"index": int, "raison": "phrase courte"}.'
    )
    try:
        message = client.messages.create(
            model=cfg["llm"]["model"],
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None

    text = _message_text(message)
    parsed = _coerce_order(_extract_first_json_array(text))
    if not parsed:
        return None
    return {o["index"]: o["raison"] for o in parsed}
