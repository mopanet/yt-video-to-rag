import pytest

from video_to_rag.urls import InvalidUrl, UnsupportedUrl, video_id


def test_watch_url_with_extra_params_yields_only_the_video():
    url = "https://www.youtube.com/watch?v=abc123DEF45&t=90s&list=PL123"
    assert video_id(url) == "abc123DEF45"


def test_short_link():
    assert video_id("https://youtu.be/abc123DEF45") == "abc123DEF45"


def test_short_link_with_timestamp():
    assert video_id("https://youtu.be/abc123DEF45?t=42&si=xyz") == "abc123DEF45"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/shorts/abc123DEF45",
        "https://www.youtube.com/live/abc123DEF45?feature=share",
        "https://m.youtube.com/watch?v=abc123DEF45",
        "https://youtube.com/watch?feature=share&v=abc123DEF45",
        "http://www.youtube.com/watch?v=abc123DEF45",
        "www.youtube.com/watch?v=abc123DEF45",
        "  https://youtu.be/abc123DEF45  ",
    ],
)
def test_other_video_forms(url):
    assert video_id(url) == "abc123DEF45"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@hubermanlab",
        "https://www.youtube.com/@hubermanlab/videos",
        "https://www.youtube.com/channel/UC2D2CMWXMOVWx7giW1n3LIg",
        "https://www.youtube.com/c/HubermanLab",
        "https://www.youtube.com/user/somebody",
        "https://www.youtube.com/playlist?list=PL123",
        "https://www.youtube.com/watch?list=PL123",
    ],
)
def test_channel_and_playlist_urls_not_supported_yet(url):
    with pytest.raises(UnsupportedUrl, match="channel ingest is not available yet"):
        video_id(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video",
        "https://example.com/watch?v=abc123DEF45",
        "https://youtube.com.evil.example/watch?v=abc123DEF45",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch?v=abc123DEF45%0A",
        "https://youtu.be/",
        "not a url",
        "",
    ],
)
def test_not_a_youtube_video_url(url):
    with pytest.raises(InvalidUrl, match="YouTube video URL"):
        video_id(url)
