"""City and country names resolve without using the network."""

from pathlib import Path

import pytest
import yaml

from places import resolve_place
from regions import INDEED_COUNTRIES, OTHER_COUNTRIES


_CASES = [
    ("Milano, Italia", "ok", "Milan", "italy", "Milan, Italy", ""),
    ("Milan, Italy", "ok", "Milan", "italy", "Milan, Italy", ""),
    ("milano,italia", "ok", "Milan", "italy", "Milan, Italy", ""),
    ("Милан, Италия", "ok", "Milan", "italy", "Milan, Italy", ""),
    ("Милано", "confirm", "Milan", "italy", "Milan, Italy", ""),
    ("Milano", "confirm", "Milan", "italy", "Milan, Italy", ""),
    ("Milan", "confirm", "Milan", "italy", "Milan, Italy", ""),
    ("Bergamo", "confirm", "Bergamo", "italy", "Bergamo, Italy", ""),
    ("Amsterdam", "confirm", "Amsterdam", "netherlands", "Amsterdam, Netherlands", ""),
    ("Amsterdam, Nederland", "ok", "Amsterdam", "netherlands", "Amsterdam, Netherlands", ""),
    ("Амстердам", "confirm", "Amsterdam", "netherlands", "Amsterdam, Netherlands", ""),
    ("Den Haag, Netherlands", "ok", "The Hague", "netherlands", "The Hague, Netherlands", ""),
    ("Berlin, Germany", "ok", "Berlin", "germany", "Berlin, Germany", ""),
    ("Берлин, Германия", "ok", "Berlin", "germany", "Berlin, Germany", ""),
    ("München, Deutschland", "ok", "Munich", "germany", "Munich, Germany", ""),
    ("Munchen", "confirm", "Munich", "germany", "Munich, Germany", ""),
    ("Frankfurt", "confirm", "Frankfurt", "germany", "Frankfurt, Germany", ""),
    ("Франкфурт", "confirm", "Frankfurt", "germany", "Frankfurt, Germany", ""),
    ("London", "confirm", "London", "uk", "London, United Kingdom", ""),
    ("Paris, France", "ok", "Paris", "france", "Paris, France", ""),
    ("Warszawa, Polska", "ok", "Warsaw", "poland", "Warsaw, Poland", ""),
    ("Zürich, Schweiz", "ok", "Zürich", "switzerland", "Zürich, Switzerland", ""),
    ("Cambridge", "choose", "", "", "", ""),
    ("Valencia", "choose", "", "", "", ""),
    ("Italia", "country_only", "", "italy", "Italy", ""),
    ("Италия", "country_only", "", "italy", "Italy", ""),
    ("Germany", "country_only", "", "germany", "Germany", ""),
    ("Remote", "remote", "", "", "", ""),
    ("удалённо", "remote", "", "", "", ""),
    ("", "empty", "", "", "", ""),
    ("Lecco, Italy", "ok", "Lecco", "italy", "Lecco, Italy", ""),
    ("Smalltownxyz, Italy", "ok", "Smalltownxyz", "italy", "Smalltownxyz, Italy", ""),
    ("Smalltownxyz", "unknown", "", "", "", "city"),
    ("Milano, Atlantis", "unknown", "", "", "", "country"),
]


@pytest.mark.parametrize(("typed", "status", "city", "country", "label", "detail"), _CASES)
def test_resolve_place(typed, status, city, country, label, detail):
    result = resolve_place(typed)
    assert result.status == status
    assert result.city == city
    assert result.country == country
    assert result.label == label
    if status == "unknown":
        assert result.detail == detail
    if typed == "Cambridge":
        labels = [choice[2] for choice in result.choices]
        assert "United Kingdom" in labels[0]
        assert "Canada" in labels[1]
        assert "United States" in labels[2]
    if typed == "Valencia":
        labels = [choice[2] for choice in result.choices]
        assert any("Venezuela" in item for item in labels)
        assert any("Spain" in item for item in labels)


def test_every_region_country_has_an_iso2():
    path = Path(__file__).resolve().parents[1] / "geodata" / "countries.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for code in INDEED_COUNTRIES | OTHER_COUNTRIES:
        assert code in data
        iso = data[code]["iso2"]
        assert isinstance(iso, str)
        assert len(iso) == 2
        assert iso == iso.upper()


def test_missing_city_file_names_the_build_script(monkeypatch):
    import places

    monkeypatch.setattr(places, "_DATA", Path("/no/such/cities.tsv.gz"))
    places._indexes.cache_clear()
    try:
        with pytest.raises(FileNotFoundError) as caught:
            resolve_place("Milan")
        message = str(caught.value)
        assert "cities.tsv.gz" in message
        assert "tools/build_places.py" in message
    finally:
        places._indexes.cache_clear()
