"""Stderr fallback delivery channel."""

from __future__ import annotations

import sys

from .base import DeliveryChannel


class StderrChannel(DeliveryChannel):
    @property
    def name(self) -> str:
        return "stderr"

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        if title:
            print(f"[{title}]", file=sys.stderr)
        print(content, file=sys.stderr)
        return True
