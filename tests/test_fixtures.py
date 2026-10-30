import pytest
from helpers import FIXTURES, load_fixture

INFO_KEYS = {"id", "title", "channel", "channel_id", "upload_date", "duration", "language"}


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("info_*.json")), ids=lambda p: p.name)
def test_info_fixture_loads(path):
    info = load_fixture(path.name)
    assert info.keys() >= INFO_KEYS
    assert isinstance(info["subtitles"], dict)
    assert isinstance(info["automatic_captions"], dict)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json3")), ids=lambda p: p.name)
def test_json3_fixture_loads(path):
    events = load_fixture(path.name)["events"]
    assert events
    assert all("tStartMs" in e for e in events)
