"""Tests for delivery channels."""
from builderpulse.deliver import get_channel, list_channels
from builderpulse.deliver.base import DeliveryChannel


def test_list_channels():
    channels = list_channels()
    assert "telegram" in channels
    assert "stderr" in channels
    assert len(channels) >= 7


def test_get_channel():
    ch = get_channel("stderr")
    assert ch.name == "stderr"


def test_get_channel_unknown():
    import pytest
    with pytest.raises(ValueError):
        get_channel("nonexistent")


def test_chunk_content():
    ch = get_channel("stderr")
    # Create content with paragraph breaks longer than max_length
    long_content = "\n\n".join(["x" * 2000] * 6)
    chunks = ch.chunk_content(long_content)
    assert len(chunks) > 1
    assert all(len(c) <= ch.max_length for c in chunks)


def test_stderr_send(capsys):
    ch = get_channel("stderr")
    result = ch.send("Hello stderr", title="Test")
    assert result is True
    captured = capsys.readouterr()
    assert "Hello stderr" in captured.err


def test_send_with_retry_fail():
    class FailChannel(DeliveryChannel):
        @property
        def name(self):
            return "fail"

        def send(self, content, title="", content_type="text"):
            raise RuntimeError("always fails")

    ch = FailChannel()
    result = ch.send_with_retry("test", retries=2)
    assert result is False
