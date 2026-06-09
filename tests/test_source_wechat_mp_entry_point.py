"""Self-test for WeChatMPSource entry-point contract (v2.1.0 Batch 2, Task 21).

Verifies the module loads, satisfies SourcePlugin protocol, and exposes the
required class-level metadata. This is the same kind of "smoke" test used
for every other plugin (see e.g. test_source_xiaohongshu_entry_point.py).
"""

from __future__ import annotations


def test_wechat_mp_entry_point_self_check():
    """Self-test: module loads and satisfies SourcePlugin protocol."""
    from builderpulse.plugins.registry import SourcePlugin
    from builderpulse.sources.wechat_mp import WeChatMPSource

    src = WeChatMPSource()
    # Protocol compliance (runtime_checkable)
    assert isinstance(src, SourcePlugin)
    # Required class attributes
    assert WeChatMPSource.name == "wechat_mp"
    assert WeChatMPSource.__experimental__ is True
    # Required public methods
    assert hasattr(WeChatMPSource, "fetch")
    assert hasattr(WeChatMPSource, "health_check")
    # fetch() with no mp_names should not crash and should return []
    assert src.fetch() == []
    # health_check() with no mp_names should be False (cheap probe)
    assert src.health_check() is False


def test_wechat_mp_is_re_exported_from_sources_package():
    """The class must be importable from the sources package (entry-point contract)."""
    from builderpulse.sources import WeChatMPSource as PkgCls
    from builderpulse.sources.wechat_mp import WeChatMPSource as DirectCls

    assert PkgCls is DirectCls
