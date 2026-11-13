import logging

from video_to_rag.redact import RedactFilter, redact


def test_user_and_password_masked():
    message = "Unable to connect to proxy http://alice:s3cret@proxy.example:8080 (refused)"
    assert redact(message) == "Unable to connect to proxy http://***@proxy.example:8080 (refused)"


def test_user_only_masked():
    assert redact("socks5://TOKEN123@10.0.0.1:1080") == "socks5://***@10.0.0.1:1080"


def test_password_containing_at_sign_masked():
    masked = redact("via http://alice:p@ss@proxy.example:8080/path")
    assert masked == "via http://***@proxy.example:8080/path"


def test_urls_without_credentials_untouched():
    message = "fetching https://www.youtube.com/watch?v=abc123DEF45 via http://proxy.example:8080"
    assert redact(message) == message


def test_at_sign_outside_userinfo_untouched():
    message = "see https://www.youtube.com/@hubermanlab or mail me@example.com"
    assert redact(message) == message


def test_several_urls_in_one_message():
    message = (
        "tried http://a:b@one.example:1 then https://c:d@two.example:2 and http://three.example"
    )
    assert redact(message) == (
        "tried http://***@one.example:1 then https://***@two.example:2 and http://three.example"
    )


def test_log_filter_masks_message_and_args(caplog):
    logger = logging.getLogger("video_to_rag.test_redact")
    logger.addFilter(RedactFilter())
    with caplog.at_level(logging.WARNING, logger=logger.name):
        logger.warning("proxy %s failed", "http://alice:s3cret@proxy.example:8080")
    assert caplog.messages == ["proxy http://***@proxy.example:8080 failed"]
    assert "s3cret" not in caplog.text
