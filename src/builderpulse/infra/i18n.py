"""Simple i18n support for BuilderPulse."""
from __future__ import annotations
import os

_MESSAGES = {
    "en": {
        "download_start": "Downloading {url}...",
        "download_done": "Download complete: {path}",
        "transcribe_start": "Transcribing with {engine}...",
        "transcribe_done": "Transcription complete ({count} words)",
        "deliver_start": "Delivering to {channel}...",
        "deliver_done": "Delivered to {channel}",
        "error": "Error: {message}",
        "no_engine": "No transcription engine installed",
        "config_saved": "Configuration saved",
        "digest_empty": "No new content found",
    },
    "zh": {
        "download_start": "正在下载 {url}...",
        "download_done": "下载完成: {path}",
        "transcribe_start": "正在使用 {engine} 转录...",
        "transcribe_done": "转录完成（{count} 字）",
        "deliver_start": "正在投递到 {channel}...",
        "deliver_done": "已投递到 {channel}",
        "error": "错误: {message}",
        "no_engine": "未安装转录引擎",
        "config_saved": "配置已保存",
        "digest_empty": "未发现新内容",
    },
}

_current_lang = None

def get_language() -> str:
    global _current_lang
    if _current_lang is None:
        _current_lang = os.environ.get("BUILDERPULSE_LANGUAGE", "en").lower()
    return _current_lang

def set_language(lang: str) -> None:
    global _current_lang
    _current_lang = lang.lower()

def t(key: str, default: str | None = None, **kwargs) -> str:
    """Translate a message key."""
    lang = get_language()
    msg = _MESSAGES.get(lang, _MESSAGES["en"]).get(key)
    if msg is None:
        msg = _MESSAGES["en"].get(key, default or key)
    if kwargs:
        msg = msg.format(**kwargs)
    return msg
