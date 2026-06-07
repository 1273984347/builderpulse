"""NotionPage — property serialization for the Notion API.

Implements:
- Plain dataclass that holds the fields a BuilderPulse digest page needs
- :meth:`NotionPage.to_notion_properties` converts it to the JSON shape
  expected by ``POST /v1/pages`` (title, multi_select tags, optional URL,
  optional published date, plus caller-supplied ``extra`` properties).
- Skips optional properties when their value is ``None`` so the resulting
  payload doesn't carry empty keys.

Reference: docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md §3.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NotionPage:
    """A page to be created in a Notion database.

    Attributes
    ----------
    title
        Page title (becomes the ``Name`` title property in the DB).
    tags
        Tags to attach (rendered as ``multi_select`` entries).
    url
        Optional URL property (e.g. source link).
    published_at
        Optional ISO-8601 date string (rendered as a ``date`` property).
    extra
        Optional caller-supplied property overrides / additions — useful
        for custom DB schemas where extra fields need to be set.
    """

    title: str
    tags: list[str] = field(default_factory=list)
    url: str | None = None
    published_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_notion_properties(self) -> dict[str, Any]:
        """Convert to the Notion API ``properties`` JSON shape.

        Always emits the ``Name`` title property. ``Tags``, ``URL``, and
        ``Published`` are only emitted when their values are set. Any keys
        in :attr:`extra` are merged last and override generated fields
        with the same name.

        Returns
        -------
        dict
            JSON-serialisable properties dict suitable for the body of
            ``POST /v1/pages``.
        """
        props: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": self.title}}]},
        }
        if self.tags:
            props["Tags"] = {"multi_select": [{"name": t} for t in self.tags]}
        if self.url:
            props["URL"] = {"url": self.url}
        if self.published_at:
            props["Published"] = {"date": {"start": self.published_at}}
        # Allow callers to override / extend with custom DB properties
        for k, v in self.extra.items():
            props[k] = v
        return props
