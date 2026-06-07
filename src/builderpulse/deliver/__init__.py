"""Delivery channel registry."""

from __future__ import annotations

from .base import DeliveryChannel
from .telegram import TelegramChannel
from .email_sender import EmailChannel
from .lark import LarkChannel
from .dingtalk import DingTalkChannel
from .discord import DiscordChannel
from .wecom import WeComChannel
from .wechat import WeChatChannel
from .stderr_fallback import StderrChannel
from .webhook import WebhookChannel

_CHANNELS = {
    "telegram": TelegramChannel,
    "email": EmailChannel,
    "lark": LarkChannel,
    "dingtalk": DingTalkChannel,
    "discord": DiscordChannel,
    "wecom": WeComChannel,
    "wechat": WeChatChannel,
    "webhook": WebhookChannel,
    "stderr": StderrChannel,
}


def get_channel(name: str, **kwargs) -> DeliveryChannel:
    cls = _CHANNELS.get(name)
    if not cls:
        raise ValueError(
            f"Unknown channel: {name}. Available: {list(_CHANNELS.keys())}"
        )
    return cls(**kwargs)


def list_channels() -> list[str]:
    return list(_CHANNELS.keys())
