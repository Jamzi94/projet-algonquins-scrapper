"""Couche LLM optionnelle : re-ranking et explications du top-N via l'API Anthropic.

Désactivée par défaut. Activer dans config.yaml (llm.enabled: true) et fournir
ANTHROPIC_API_KEY dans .env. Ne sert jamais de moteur principal, seulement à
réordonner et expliquer un top-N déjà filtré par le pipeline.
"""
from __future__ import annotations

import json
import os


def rerank_and_explain(liked_titles, candidates, cfg: dict):
    """Renvoie une liste [{"index": int, "raison": str}] ou None si indisponible."""
    if not cfg.get("llm", {}).get("enabled"):
        return None
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except Exception:
        return None

    client = anthropic.Anthropic(api_key=api_key)
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

    text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()
    text = text.strip("`")
    if text.startswith("json"):
        text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return None
