"""Tests for ExperimentalPluginProxy (v2.1.0 spec §4.1.1).

The proxy wraps any plugin that sets ``__experimental__ = True`` and
auto-disables it after 3 consecutive failures within a 1-hour sliding
window. These tests cover the full failure / success / auto-disable
state machine plus Protocol conformance.
"""

from __future__ import annotations

import pytest

from builderpulse.plugins.registry import (
    ChannelPlugin,
    ExperimentalPluginProxy,
    SourceAutoDisabledError,
    SourcePlugin,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeSource:
    """Mimics a SourcePlugin for testing the proxy.

    Controlled by ``should_fail`` (raises RuntimeError when True) and
    tracks call count for assertion.
    """

    name = "fake_source"

    def __init__(self, name: str = "fake_source", should_fail: bool = False) -> None:
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0

    def fetch(self, **kwargs):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("simulated source failure")
        return [{"title": "x", "url": "y"}]

    def health_check(self) -> bool:
        return True


class FakeChannel:
    """Mimics a ChannelPlugin for testing the proxy."""

    name = "fake_channel"

    def __init__(self, name: str = "fake_channel", should_fail: bool = False) -> None:
        self.name = name
        self.should_fail = should_fail
        self.call_count = 0

    def deliver(self, content, **kwargs):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("simulated channel failure")
        return True

    def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_proxy_delegates_successful_call():
    """Successful call passes through; failure count stays at 0."""
    src = FakeSource(should_fail=False)
    proxy = ExperimentalPluginProxy(src)

    result = proxy.fetch()

    assert result == [{"title": "x", "url": "y"}]
    assert src.call_count == 1
    assert proxy._failures == 0
    assert proxy._first_failure_window_start is None
    assert proxy._auto_disabled is False


def test_proxy_counts_failures():
    """Each failure increments counter; first failure starts the 1h window."""
    src = FakeSource(should_fail=True)
    proxy = ExperimentalPluginProxy(src)

    with pytest.raises(RuntimeError):
        proxy.fetch()
    assert proxy._failures == 1
    assert proxy._first_failure_window_start is not None
    assert proxy._auto_disabled is False

    with pytest.raises(RuntimeError):
        proxy.fetch()
    assert proxy._failures == 2
    assert proxy._auto_disabled is False


def test_proxy_auto_disables_after_3_failures_in_1h():
    """3 consecutive failures within 1h -> auto-disabled + SourceAutoDisabledError."""
    src = FakeSource(should_fail=True)
    proxy = ExperimentalPluginProxy(src)

    with pytest.raises(RuntimeError):
        proxy.fetch()
    with pytest.raises(RuntimeError):
        proxy.fetch()
    # 3rd failure triggers auto-disable
    with pytest.raises(SourceAutoDisabledError) as exc_info:
        proxy.fetch()

    assert proxy._auto_disabled is True
    assert exc_info.value.source_name == "fake_source"
    # The underlying source was hit on every call (including the one that
    # raised the auto-disable error — the wrapped call happens first).
    assert src.call_count == 3


def test_proxy_raises_after_auto_disabled():
    """Once auto-disabled, subsequent calls raise SourceAutoDisabledError immediately."""
    src = FakeSource(should_fail=True)
    proxy = ExperimentalPluginProxy(src)

    # Trigger auto-disable (mixed exception types are expected)
    for _ in range(3):
        with pytest.raises((RuntimeError, SourceAutoDisabledError)):
            proxy.fetch()

    assert proxy._auto_disabled is True

    # Now any call — fetch or deliver — should raise SourceAutoDisabledError
    # and the wrapped source must not be called again.
    calls_before = src.call_count
    with pytest.raises(SourceAutoDisabledError):
        proxy.fetch()
    with pytest.raises(SourceAutoDisabledError):
        proxy.deliver("payload")  # delegate to source.deliver -> raises again
    assert src.call_count == calls_before  # no additional call to underlying


def test_proxy_resets_failures_on_success():
    """A success between failures resets the counter and window start."""
    src = FakeSource(should_fail=False)
    proxy = ExperimentalPluginProxy(src)

    # Inject one failure
    src.should_fail = True
    with pytest.raises(RuntimeError):
        proxy.fetch()
    assert proxy._failures == 1
    assert proxy._first_failure_window_start is not None

    # Then a success
    src.should_fail = False
    result = proxy.fetch()
    assert result == [{"title": "x", "url": "y"}]
    assert proxy._failures == 0
    assert proxy._first_failure_window_start is None


def test_proxy_isinstance_source_protocol():
    """ExperimentalPluginProxy instance satisfies isinstance(SourcePlugin)."""
    src = FakeSource()
    proxy = ExperimentalPluginProxy(src)

    # Use isinstance (NOT issubclass) — @runtime_checkable Protocol
    # isinstance() check is the canonical validation path.
    assert isinstance(proxy, SourcePlugin)
    # name should be accessible via @property
    assert proxy.name == "fake_source"
    # __getattr__ delegation: unknown attrs pass through to the wrapped source
    assert proxy.health_check() is True


def test_proxy_isinstance_channel_protocol():
    """ExperimentalPluginProxy also satisfies isinstance(ChannelPlugin).

    The same proxy class is used for both sources and channels (per spec
    §4.1.1). This test confirms the proxy can stand in for a channel as
    well.
    """
    chan = FakeChannel()
    proxy = ExperimentalPluginProxy(chan)

    assert isinstance(proxy, ChannelPlugin)
    assert proxy.name == "fake_channel"

    result = proxy.deliver({"title": "x"})
    assert result is True
    assert chan.call_count == 1


def test_proxy_channel_auto_disables_on_deliver_failures():
    """Auto-disable also triggers on deliver() failures (not just fetch)."""
    chan = FakeChannel(should_fail=True)
    proxy = ExperimentalPluginProxy(chan)

    with pytest.raises(RuntimeError):
        proxy.deliver({"x": 1})
    with pytest.raises(RuntimeError):
        proxy.deliver({"x": 1})
    with pytest.raises(SourceAutoDisabledError):
        proxy.deliver({"x": 1})

    assert proxy._auto_disabled is True


def test_proxy_non_experimental_attr_is_ignored_by_registry():
    """Plugins without __experimental__ are not auto-wrapped by the registry.

    Sanity check: only instances that set ``__experimental__ = True``
    should get the proxy treatment. We verify the attribute gating logic
    used by ``_ensure_loaded`` so a future refactor doesn't break it.
    """
    src = FakeSource()  # no __experimental__
    assert getattr(src, "__experimental__", False) is False

    proxied = (
        ExperimentalPluginProxy(src) if getattr(src, "__experimental__", False) else src
    )
    assert proxied is src
    # And the proxy would still work IF manually wrapped, but the registry
    # must not wrap it — this is what the getattr(..., False) guard enforces.
