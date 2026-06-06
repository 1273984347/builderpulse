"""Delivery channel abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
import logging

logger = logging.getLogger("builderpulse.deliver")


class DeliveryChannel(ABC):
    @abstractmethod
    def send(
        self, content: str, title: str = "", content_type: str = "text"
    ) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def max_length(self) -> int:
        return 4096

    def send_with_retry(self, content: str, title: str = "", retries: int = 3) -> bool:
        for attempt in range(retries):
            try:
                return self.send(content, title)
            except Exception as e:
                if attempt == retries - 1:
                    logger.error(
                        f"Delivery to {self.name} failed after {retries} attempts: {e}"
                    )
                    return False
                time.sleep(2**attempt)
        return False

    def chunk_content(self, content: str) -> list[str]:
        if len(content) <= self.max_length:
            return [content]
        paragraphs = content.split("\n\n")
        chunks, current = [], ""
        for p in paragraphs:
            # P1 fix: truncate oversized paragraphs
            if len(p) > self.max_length:
                if current:
                    chunks.append(current)
                    current = ""
                for i in range(0, len(p), self.max_length):
                    chunks.append(p[i : i + self.max_length])
                continue
            if len(current) + len(p) + 2 > self.max_length:
                if current:
                    chunks.append(current)
                current = p
            else:
                current += f"\n\n{p}" if current else p
        if current:
            chunks.append(current)
        return chunks or [content[: self.max_length]]
