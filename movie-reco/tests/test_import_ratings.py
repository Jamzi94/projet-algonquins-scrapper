"""Tests de l'importeur de notes (Letterboxd / IMDb / CSV générique)."""
import pandas as pd

from movreco.ingest.import_ratings import import_ratings, load_ratings


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_letterboxd(tmp_path):
    src = _write(
        tmp_path / "letterboxd.csv",
        "Date,Name,Year,Letterboxd URI,Rating\n"
        "2023-01-01,Inception,2010,https://x,4.5\n"
        "2023-02-01,Drive,2011,https://y,4.0\n",
    )
    df = load_ratings(src)
    assert list(df.columns) == ["title", "year", "rating"]
    assert df.loc[0, "title"] == "Inception"
    assert int(df.loc[0, "year"]) == 2010
    assert df.loc[0, "rating"] == 4.5


def test_imdb(tmp_path):
    src = _write(
        tmp_path / "imdb.csv",
        "Const,Your Rating,Date Rated,Title,Year,Genres\n"
        "tt1375666,9,2020-01-01,Inception,2010,Action\n"
        "tt0468569,10,2020-01-02,The Dark Knight,2008,Action\n",
    )
    df = load_ratings(src)
    # "Your Rating" (IMDb) prioritaire sur un éventuel "Rating".
    assert df.loc[1, "title"] == "The Dark Knight"
    assert int(df.loc[1, "year"]) == 2008
    assert df.loc[1, "rating"] == 10.0


def test_generique_et_lignes_invalides(tmp_path):
    src = _write(
        tmp_path / "g.csv",
        "title,year,rating\nParasite,2019,9\nBad,2000,N/A\n",
    )
    df = load_ratings(src)
    assert len(df) == 1  # la ligne au rating non numérique est écartée
    assert df.loc[0, "title"] == "Parasite"
    assert df.attrs.get("n_dropped") == 1


def test_sans_year(tmp_path):
    src = _write(tmp_path / "noyear.csv", "Name,Rating\nInception,4.0\n")
    df = load_ratings(src)
    assert pd.isna(df.loc[0, "year"])
    assert df.loc[0, "rating"] == 4.0


def test_format_non_reconnu(tmp_path):
    src = _write(tmp_path / "bad.csv", "foo,bar\n1,2\n")
    try:
        load_ratings(src)
        assert False, "devrait lever ValueError"
    except ValueError as exc:
        assert "Format non reconnu" in str(exc)


def test_import_ecrit_le_fichier(tmp_path):
    src = _write(tmp_path / "lb.csv", "Name,Year,Rating\nInception,2010,4.5\n")
    out = tmp_path / "input" / "ratings.csv"
    df = import_ratings(src, out)
    assert out.exists()
    reread = pd.read_csv(out)
    assert list(reread.columns) == ["title", "year", "rating"]
    assert len(df) == 1
