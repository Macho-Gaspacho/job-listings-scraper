from listings import clean_text, dedupe, identity_keys, title_is_relevant, apply_new_flags


def test_clean_text():
    assert clean_text("  hello\xa0world  ") == "hello world"
    assert clean_text(None) == ""


def test_identity_keys():
    row = {"Company": "Acme", "Title": "PM"}
    assert identity_keys(row) == ("acme", "pm")


def test_dedupe():
    rows = [
        {"Company": "A", "Title": "PM"},
        {"Company": "A", "Title": "PM"},
        {"Company": "B", "Title": "PO"},
    ]
    assert len(dedupe(rows)) == 2


def test_title_is_relevant():
    assert title_is_relevant("Senior Product Manager", ["product manager"])
    assert not title_is_relevant("Engineer", ["product manager"])


def test_apply_new_flags():
    rows = [{"Company": "A", "Title": "PM"}]
    seen = {("a", "pm")}
    flagged = apply_new_flags(rows, seen)
    assert flagged[0]["Status"] == "Seen"
