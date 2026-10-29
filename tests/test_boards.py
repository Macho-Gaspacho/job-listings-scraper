from boards import parse_weworkremotely, parse_remoteok


def test_parse_weworkremotely_empty():
    assert parse_weworkremotely("<html></html>", "product manager", "Remote") == []


def test_parse_remoteok_empty():
    assert parse_remoteok("<html></html>", "product manager", "Remote") == []
