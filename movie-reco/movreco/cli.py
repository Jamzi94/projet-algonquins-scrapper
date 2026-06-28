"""Interface en ligne de commande movreco.

Flux complet :
    movreco ingest --ratings data/input/ratings.csv
    movreco synopsis
    movreco embed
    movreco features
    movreco train          # uniquement pour le mode hybride
    movreco recommend --mode hybrid   (ou --mode mvp)
    movreco evaluate
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import typer
from rich import print as rprint
from rich.table import Table

from movreco.config import data_path, load_config, paths

app = typer.Typer(add_completion=False, help="Recommandeur de films personnel (Wikidata CC0 + embeddings).")


def _cfg() -> dict:
    return load_config()


def _cache_dir(cfg: dict) -> str | None:
    """Dossier de cache absolu si le cache est actif, sinon None.

    Respecte cfg["cache"]["dir"] (relatif resolu contre la racine du projet),
    avec repli sur ROOT/data/cache. Renvoie None quand le cache est desactive.
    """
    cache_cfg = cfg.get("cache", {}) or {}
    if not cache_cfg.get("enabled", True):
        return None
    root = Path(cfg.get("_root", "."))
    cdir = cache_cfg.get("dir")
    d = Path(cdir) if cdir else root / "data" / "cache"
    if not d.is_absolute():
        d = root / d
    return str(d)


def _load_aligned_emb(P: dict, items: pd.DataFrame) -> np.ndarray:
    """Charge les embeddings et les réaligne sur `items` (contrat align_embeddings)."""
    from movreco.features.combine import align_embeddings

    emb = np.load(P["embeddings"])
    emb_ids = json.loads(P["emb_ids"].read_text()) if P["emb_ids"].exists() else None
    try:
        return align_embeddings(emb, emb_ids, items)
    except ValueError as exc:
        rprint(f"[red]{exc}[/red]")
        raise typer.Exit(1)


def _normalize_catalog(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["qid", "label", "genres", "directors", "countries", "date", "popularity", "imdb"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df.copy()
    df["qid"] = df["film"].str.rsplit("/", n=1).str[-1]
    df = df.rename(columns={"filmLabel": "label"})
    for col in ["genres", "directors", "countries", "imdb"]:
        if col not in df:
            df[col] = ""
    if "popularity" not in df:
        df["popularity"] = 0
    df["popularity"] = pd.to_numeric(df["popularity"], errors="coerce").fillna(0)
    for col in cols:
        if col not in df:
            df[col] = None
    return df[cols]


@app.command()
def ingest(
    ratings: Path = typer.Option(Path("data/input/ratings.csv"), help="CSV : title,year,rating"),
):
    """Apparie ta liste à Wikidata et construit le catalogue de candidats."""
    from movreco.ingest import matching, wikidata

    cfg = _cfg()
    P = paths(cfg)
    if not ratings.exists():
        rprint(f"[red]Fichier introuvable :[/red] {ratings}")
        rprint("Vois data/input/ratings.example.csv pour le format attendu.")
        raise typer.Exit(1)

    rdf = pd.read_csv(ratings)
    missing = [c for c in ("title", "rating") if c not in rdf.columns]
    if missing:
        rprint(f"[red]Colonnes requises manquantes :[/red] {', '.join(missing)}")
        rprint("Format attendu : title,year,rating (voir data/input/ratings.example.csv).")
        raise typer.Exit(1)
    rdf["rating"] = pd.to_numeric(rdf["rating"], errors="coerce")
    n_bad = int(rdf["rating"].isna().sum())
    if n_bad:
        rprint(f"[yellow]{n_bad} ligne(s) au rating invalide ecartee(s).[/yellow]")
    rdf = rdf.dropna(subset=["rating"]).reset_index(drop=True)
    if rdf.empty:
        rprint("[red]Aucune ligne valide apres nettoyage des notes.[/red]")
        raise typer.Exit(1)
    if "year" in rdf.columns:
        rdf["year"] = pd.to_numeric(rdf["year"], errors="coerce")
    rprint(f"[cyan]Appariement de {len(rdf)} films a Wikidata...[/cyan]")
    matched = matching.match_ratings(rdf, cfg)
    n_ok = int(matched["qid"].notna().sum())
    rprint(f"[green]{n_ok}/{len(matched)} apparies.[/green]")

    y0 = int(cfg["catalog"]["year_min"])
    y1 = int(cfg["catalog"]["year_max"])
    rows: list[dict] = []
    for year in range(y0, y1 + 1):
        rprint(f"  catalogue {year}...")
        try:
            rows.extend(wikidata.fetch_catalog_by_year(year, cfg))
        except Exception as exc:  # tolérant aux timeouts ponctuels
            rprint(f"[yellow]  annee {year} ignoree : {exc}[/yellow]")
    catalog = _normalize_catalog(pd.DataFrame(rows))

    rated_qids = matched.dropna(subset=["qid"])["qid"].tolist()
    rated_meta = _normalize_catalog(pd.DataFrame(wikidata.fetch_items_metadata(rated_qids, cfg))) if rated_qids else _normalize_catalog(pd.DataFrame())

    items = pd.concat([catalog, rated_meta], ignore_index=True)
    items = items.dropna(subset=["qid"]).drop_duplicates(subset=["qid"]).reset_index(drop=True)

    P["items"].parent.mkdir(parents=True, exist_ok=True)
    P["rated"].parent.mkdir(parents=True, exist_ok=True)
    items.to_parquet(P["items"])
    matched.dropna(subset=["qid"])[["qid", "rating"]].to_parquet(P["rated"])
    report = data_path("processed", "matching_report.csv")
    matched.to_csv(report, index=False)
    # Le catalogue vient d'etre re-recupere : l'ordre des lignes SPARQL n'est pas
    # garanti stable et un film peut etre remplace a effectif constant. L'index FAISS
    # persistant a pu etre construit sur l'ancien ordre/contenu et build_or_load ne
    # detecte pas un changement a ntotal/dimension constants -> on l'invalide ici
    # (comme embed) pour que recommend reconstruise un index aligne.
    P["faiss"].unlink(missing_ok=True)

    rprint(f"[green]items : {len(items)} | notes utilisables : {n_ok}[/green]")
    rprint(f"Rapport d'appariement (a verifier) : {report}")


@app.command()
def synopsis():
    """Récupère les synopsis Wikipédia pour tous les items."""
    import requests
    import tqdm

    from movreco.ingest import synopsis as syn
    from movreco.ingest import wikidata

    cfg = _cfg()
    P = paths(cfg)
    items = pd.read_parquet(P["items"])
    rprint("[cyan]Resolution des titres Wikipedia...[/cyan]")
    titles = wikidata.get_wikipedia_titles(items["qid"].tolist(), cfg)

    session = requests.Session()
    cache_dir = _cache_dir(cfg)
    rows = []
    for qid in tqdm.tqdm(items["qid"].tolist(), desc="synopsis"):
        title = titles.get(qid)
        text = (
            syn.fetch_summary(title, cfg.get("language", "fr"), session, cache_dir=cache_dir)
            if title
            else None
        )
        rows.append({"qid": qid, "text": text})

    sdf = pd.DataFrame(rows)
    P["synopsis"].parent.mkdir(parents=True, exist_ok=True)
    sdf.to_parquet(P["synopsis"])
    rprint(f"[green]synopsis recuperes : {int(sdf['text'].notna().sum())}/{len(sdf)}[/green]")


@app.command()
def embed():
    """Calcule les embeddings (synopsis, repli sur le titre si absent)."""
    from movreco.features import embeddings as E

    cfg = _cfg()
    P = paths(cfg)
    items = pd.read_parquet(P["items"])
    if P["synopsis"].exists():
        syn = pd.read_parquet(P["synopsis"])
        text_map = dict(zip(syn["qid"], syn["text"]))
    else:
        text_map = {}

    texts = []
    for _, row in items.iterrows():
        t = text_map.get(row["qid"])
        texts.append(t if isinstance(t, str) and t.strip() else str(row["label"]))

    emb = E.embed_texts(texts, cfg)
    P["embeddings"].parent.mkdir(parents=True, exist_ok=True)
    np.save(P["embeddings"], emb)
    P["emb_ids"].write_text(json.dumps(items["qid"].tolist()))
    # Invalide l'index FAISS persistant : meme nombre de lignes mais contenu/ordre
    # potentiellement different -> recommend reconstruira un index aligne.
    P["faiss"].unlink(missing_ok=True)
    rprint(f"[green]embeddings : {emb.shape}[/green]")


@app.command()
def features():
    """Construit les features structurées (genres, réalisateurs, pays, décennie)."""
    from movreco.features.structured import build_structured_features

    cfg = _cfg()
    P = paths(cfg)
    items = pd.read_parquet(P["items"])
    feats = build_structured_features(items)
    P["structured"].parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(P["structured"])
    rprint(f"[green]features structurees : {feats.shape}[/green]")


@app.command()
def train():
    """Entraîne le modèle de préférence (mode hybride) et affiche la MAE LOO."""
    from movreco.features.combine import feature_matrix
    from movreco.model import evaluate, preference

    cfg = _cfg()
    P = paths(cfg)
    items = pd.read_parquet(P["items"])
    emb = _load_aligned_emb(P, items)
    structured = pd.read_parquet(P["structured"])
    rated = pd.read_parquet(P["rated"])

    qids = rated["qid"].tolist()
    y = rated["rating"].values.astype(float)
    X = feature_matrix(qids, items, emb, structured)

    model = preference.train(X, y, cfg)
    P["model"].parent.mkdir(parents=True, exist_ok=True)
    preference.save(model, P["model"])

    mae = evaluate.loo_mae(X, y, lambda a, b: preference.train(a, b, cfg))
    rprint(f"[green]Modele entraine.[/green] MAE leave-one-out : {mae:.3f}")


def _print_reco(result: pd.DataFrame, expl: dict | None = None) -> None:
    table = Table(title="Recommandations")
    table.add_column("#", justify="right")
    table.add_column("Film")
    table.add_column("Score", justify="right")
    if expl:
        table.add_column("Pourquoi")
    for i, row in result.iterrows():
        cells = [str(i + 1), str(row["label"]), f"{row['score']:.3f}"]
        if expl:
            cells.append(str(expl.get(i, "")))
        table.add_row(*cells)
    rprint(table)


@app.command()
def recommend(
    mode: str = typer.Option("hybrid", help="hybrid ou mvp"),
    n: int = typer.Option(0, help="taille du top-N (0 = valeur de config)"),
):
    """Produit les recommandations."""
    from movreco.llm import rerank
    from movreco.model import preference
    from movreco.recommend.pipeline import recommend as run_reco

    cfg = _cfg()
    P = paths(cfg)
    if n:
        cfg["recommend"]["top_n"] = n

    items = pd.read_parquet(P["items"])
    emb = _load_aligned_emb(P, items)
    rated = pd.read_parquet(P["rated"])
    structured = pd.read_parquet(P["structured"]) if P["structured"].exists() else None
    if mode == "hybrid" and len(rated) < cfg.get("model", {}).get("min_train", 20):
        rprint(
            "[yellow]Echantillon trop petit pour le modele hybride, repli sur le mode mvp.[/yellow]"
        )
        mode = "mvp"
    model = preference.load(P["model"]) if (mode == "hybrid" and P["model"].exists()) else None
    if mode == "hybrid" and model is None:
        rprint("[yellow]Aucun modele entraine, repli sur le mode mvp.[/yellow]")
        mode = "mvp"

    P["faiss"].parent.mkdir(parents=True, exist_ok=True)
    result = run_reco(
        items,
        emb,
        rated["qid"].tolist(),
        rated["rating"].values.astype(float),
        mode=mode,
        structured=structured,
        model=model,
        cfg=cfg,
        index_path=P["faiss"],
    )

    expl = None
    if cfg.get("llm", {}).get("enabled") and not result.empty:
        liked_order = rated.sort_values("rating", ascending=False)["qid"]
        label_by_qid = dict(zip(items["qid"], items["label"]))
        liked = [label_by_qid.get(q) for q in liked_order if label_by_qid.get(q)]
        order = rerank.rerank_and_explain(liked, result["label"].tolist(), cfg)
        if order:
            n_pos = len(result)
            ranked: list[int] = []
            reasons: dict[int, str] = {}
            for o in order:
                i = o.get("index")
                if isinstance(i, int) and 0 <= i < n_pos and i not in ranked:
                    reasons[i] = o.get("raison", "")
                    ranked.append(i)
            # permutation complète : positions classées par le LLM puis le reste dans l'ordre du pipeline
            perm = ranked + [i for i in range(n_pos) if i not in ranked]
            if ranked:
                result = result.iloc[perm].reset_index(drop=True)
                # la raison est associée à la position FINALE des seuls items classés par le LLM
                expl = {final: reasons[src] for final, src in enumerate(perm) if src in reasons}

    if result.empty:
        rprint("[yellow]Aucune recommandation (verifie que l'ingestion et les embeddings sont faits).[/yellow]")
    else:
        _print_reco(result, expl)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Adresse d'écoute"),
    port: int = typer.Option(8000, help="Port d'écoute"),
    reload: bool = typer.Option(False, "--reload", help="Rechargement auto (développement)"),
):
    """Lance l'API FastAPI (recommandations en service)."""
    import uvicorn

    rprint(f"[green]API movreco sur[/green] http://{host}:{port}  (docs : http://{host}:{port}/docs)")
    uvicorn.run("movreco.api.app:app", host=host, port=port, reload=reload)


@app.command()
def evaluate():
    """Affiche la MAE leave-one-out du modèle de préférence."""
    from movreco.features.combine import feature_matrix
    from movreco.model import evaluate as ev
    from movreco.model import preference

    cfg = _cfg()
    P = paths(cfg)
    items = pd.read_parquet(P["items"])
    emb = _load_aligned_emb(P, items)
    structured = pd.read_parquet(P["structured"])
    rated = pd.read_parquet(P["rated"])

    qids = rated["qid"].tolist()
    X = feature_matrix(qids, items, emb, structured)
    y = rated["rating"].values.astype(float)
    train_fn = lambda a, b: preference.train(a, b, cfg)

    mae = ev.loo_mae(X, y, train_fn)
    rprint(f"[green]MAE leave-one-out : {mae:.3f}[/green]")

    # NDCG@k sur split temporel : dates des films notes (jointure qid -> date).
    date_by_qid = dict(zip(items["qid"], items["date"]))
    dates = [date_by_qid.get(q) for q in qids]
    ec = cfg.get("evaluate", {})
    ndcg = ev.temporal_ndcg(
        X, y, dates, train_fn,
        k=ec.get("ndcg_k", 10),
        holdout_frac=ec.get("holdout_frac", 0.3),
    )
    rprint(f"[green]{ev.format_metric('NDCG@k (split temporel)', ndcg)}[/green]")


if __name__ == "__main__":
    app()
