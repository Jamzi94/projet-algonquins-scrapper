from movreco.ingest.matching import normalize_title


def test_normalize_strips_accents_and_punct():
    assert normalize_title("L'Étrange Noël  !!") == "l etrange noel"


def test_normalize_case_insensitive():
    assert normalize_title("Inception") == normalize_title("INCEPTION")
