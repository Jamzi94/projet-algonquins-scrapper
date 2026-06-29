"""Tests de la couche LLM de re-ranking (Équipe 2) — entièrement hors-ligne.

On n'appelle JAMAIS l'API Anthropic : un client factice est injecté via le
paramètre ``client=`` de ``rerank.rerank_and_explain``. Ce client expose
``messages.create(...)`` renvoyant un objet dont ``.content`` est une liste de
blocs ``(.type == "text", .text="...")``, exactement comme le SDK Anthropic.

On vérifie :
  - parsing robuste : JSON entouré de texte ou de balises de code Markdown ;
  - entrées invalides ignorées silencieusement ;
  - JSON cassé / réponse vide -> None ;
  - ``llm.enabled = false`` SANS client injecté -> None (désactivation par défaut) ;
  - la fonction optionnelle ``explain`` renvoie un dict {index -> raison}.
"""
from __future__ import annotations

from movreco.llm import rerank


# --------------------------------------------------------------------------- #
# Client factice (mime le SDK Anthropic, hors-ligne)
# --------------------------------------------------------------------------- #
class _TextBlock:
    """Bloc de contenu de type 'text' (comme un bloc de réponse Anthropic)."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Message:
    """Réponse minimaliste : ``.content`` est une liste de blocs."""

    def __init__(self, blocks):
        self.content = blocks


class _Messages:
    def __init__(self, text: str):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        # On mémorise l'appel pour pouvoir vérifier les arguments si besoin.
        self.calls.append(kwargs)
        return _Message([_TextBlock(self._text)])


class FakeClient:
    """Client injectable : renvoie toujours le texte fourni à la construction."""

    def __init__(self, text: str):
        self.messages = _Messages(text)


class RaisingClient:
    """Client dont ``messages.create`` lève (simule une panne réseau/API)."""

    class _M:
        def create(self, **kwargs):
            raise RuntimeError("panne simulée")

    def __init__(self):
        self.messages = self._M()


# Config minimale : la couche est activée, mais peu importe car on injecte le
# client (le paramètre `client=` court-circuite la création du vrai client).
CFG = {"llm": {"enabled": True, "model": "claude-sonnet-4-6"}}
CFG_OFF = {"llm": {"enabled": False, "model": "claude-sonnet-4-6"}}

LIKED = ["Inception", "Interstellar"]
CANDIDATES = ["Tenet", "Dunkerque", "Le Prestige"]


def test_json_pur(monkeypatch):
    client = FakeClient(
        '[{"index": 2, "raison": "même réalisateur"}, '
        '{"index": 0, "raison": "thème temporel"}]'
    )
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=client)
    assert out == [
        {"index": 2, "raison": "même réalisateur"},
        {"index": 0, "raison": "thème temporel"},
    ]


def test_json_entoure_de_texte(monkeypatch):
    # Le LLM bavarde autour du JSON : on doit extraire le PREMIER tableau valide.
    text = (
        "Bien sûr, voici mon classement :\n"
        '[{"index": 1, "raison": "guerre"}, {"index": 2, "raison": "Nolan"}]\n'
        "J'espère que cela vous convient."
    )
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == [
        {"index": 1, "raison": "guerre"},
        {"index": 2, "raison": "Nolan"},
    ]


def test_json_dans_balises_markdown(monkeypatch):
    # Réponse entourée d'un bloc de code Markdown ```json ... ```.
    text = (
        "Voici le résultat :\n"
        "```json\n"
        '[{"index": 0, "raison": "même univers"}]\n'
        "```\n"
    )
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == [{"index": 0, "raison": "même univers"}]


def test_entrees_invalides_ignorees(monkeypatch):
    # Mélange d'entrées : seules celles avec un index entier sont conservées.
    text = (
        "[\n"
        '  {"index": 0, "raison": "ok"},\n'
        '  {"raison": "sans index"},\n'        # index manquant -> ignorée
        '  "juste une chaîne",\n'              # pas un dict -> ignorée
        '  {"index": "deux", "raison": "x"},\n'  # index non entier -> ignorée
        '  {"index": true, "raison": "bool"},\n'  # bool n'est pas un int valide
        '  {"index": 2, "raison": "ok2"}\n'
        "]"
    )
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == [
        {"index": 0, "raison": "ok"},
        {"index": 2, "raison": "ok2"},
    ]


def test_raison_manquante_devient_chaine_vide(monkeypatch):
    text = '[{"index": 1}]'  # index valide mais pas de raison
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == [{"index": 1, "raison": ""}]


def test_json_casse_donne_none(monkeypatch):
    out = rerank.rerank_and_explain(
        LIKED, CANDIDATES, CFG, client=FakeClient("ceci n'est pas du JSON {[}")
    )
    assert out is None


def test_reponse_vide_donne_none(monkeypatch):
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(""))
    assert out is None


def test_tableau_vide_donne_none(monkeypatch):
    # Un tableau valide mais vide ne contient rien d'exploitable -> None.
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient("[]"))
    assert out is None


def test_objet_json_seul_non_liste_donne_none(monkeypatch):
    # Le LLM renvoie un objet, pas un tableau : aucun tableau exploitable -> None.
    out = rerank.rerank_and_explain(
        LIKED, CANDIDATES, CFG, client=FakeClient('{"index": 0, "raison": "x"}')
    )
    assert out is None


def test_exception_client_donne_none(monkeypatch):
    # Une panne de l'appel LLM ne doit jamais remonter : on renvoie None.
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=RaisingClient())
    assert out is None


def test_desactive_sans_client_donne_none(monkeypatch):
    # llm.enabled = false ET aucun client injecté -> aucun appel, None.
    # On s'assure qu'aucune clé d'environnement ne ré-active la couche.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG_OFF)
    assert out is None


def test_active_mais_sans_cle_donne_none(monkeypatch):
    # llm.enabled = true mais pas de clé et pas de client injecté -> None.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG)
    assert out is None


def test_premier_tableau_retenu(monkeypatch):
    # Deux tableaux dans le texte : on doit retenir le PREMIER valide.
    text = (
        'D\'abord [{"index": 0, "raison": "premier"}] '
        'puis [{"index": 1, "raison": "second"}].'
    )
    out = rerank.rerank_and_explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == [{"index": 0, "raison": "premier"}]


# --------------------------------------------------------------------------- #
# Fonction optionnelle explain -> dict {index -> raison}
# --------------------------------------------------------------------------- #
def test_explain_renvoie_dict(monkeypatch):
    text = (
        "Voici :\n```json\n"
        '[{"index": 0, "raison": "rythme"}, {"index": 1, "raison": "casting"}]\n```'
    )
    out = rerank.explain(LIKED, CANDIDATES, CFG, client=FakeClient(text))
    assert out == {0: "rythme", 1: "casting"}


def test_explain_json_casse_donne_none(monkeypatch):
    out = rerank.explain(LIKED, CANDIDATES, CFG, client=FakeClient("pas de json"))
    assert out is None


def test_explain_desactive_donne_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = rerank.explain(LIKED, CANDIDATES, CFG_OFF)
    assert out is None
