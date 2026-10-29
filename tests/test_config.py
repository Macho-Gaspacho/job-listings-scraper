from pathlib import Path
from config import load_config


def test_load_config(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("roles:\n  - pm\nplaces:\n  - Milan\npause_seconds: 1\ncompanies: []\nboards: []\n")
    settings = load_config(config)
    assert settings.roles == ["pm"]
    assert settings.places == ["Milan"]
