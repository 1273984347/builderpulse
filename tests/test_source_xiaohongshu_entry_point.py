"""Self-test for XiaohongshuSource entry-point contract (v2.1.0 Batch 2, Task 20).

Verifies the module loads, satisfies SourcePlugin protocol, and exposes the
required class-level metadata. This is the same kind of "smoke" test used
for every other plugin (see e.g. test_source_bilibili_entry_point.py).
"""

from __future__ import annotations


def test_xiaohongshu_entry_point_self_check():
    """Self-test: module loads and satisfies SourcePlugin protocol."""
    from builderpulse.plugins.registry import SourcePlugin
    from builderpulse.sources.xiaohongshu import XiaohongshuSource

    src = XiaohongshuSource()
    # Protocol compliance (runtime_checkable)
    assert isinstance(src, SourcePlugin)
    # Required class attributes
    assert XiaohongshuSource.name == "xiaohongshu"
    assert XiaohongshuSource.__experimental__ is True
    # Required public methods
    assert hasattr(XiaohongshuSource, "fetch")
    assert hasattr(XiaohongshuSource, "health_check")
    # fetch() with no user_ids should not crash and should return []
    assert src.fetch() == []
    # health_check() with no user_ids should be False (cheap probe)
    assert src.health_check() is False


def test_xiaohongshu_is_re_exported_from_sources_package():
    """The class must be importable from the sources package (entry-point contract)."""
    from builderpulse.sources import XiaohongshuSource as PkgCls
    from builderpulse.sources.xiaohongshu import XiaohongshuSource as DirectCls

    assert PkgCls is DirectCls
