"""Tests for delivery channels — construction, properties, send, error handling."""

from __future__ import annotations

import httpx
import pytest

from builderpulse.deliver.telegram import TelegramChannel
from builderpulse.deliver.email_sender import EmailChannel
from builderpulse.deliver.lark import LarkChannel
from builderpulse.deliver.dingtalk import DingTalkChannel
from builderpulse.deliver.discord import DiscordChannel
from builderpulse.deliver.wecom import WeComChannel
from builderpulse.deliver.wechat import WeChatChannel


# ── Telegram ────────────────────────────────────────────────────────────


class TestTelegramChannel:
    def test_construction(self):
        ch = TelegramChannel(bot_token="tok", chat_id="123")
        assert ch.bot_token == "tok"
        assert ch.chat_id == "123"

    def test_name(self):
        ch = TelegramChannel(bot_token="tok", chat_id="123")
        assert ch.name == "telegram"

    def test_max_length_default(self):
        ch = TelegramChannel(bot_token="tok", chat_id="123")
        assert ch.max_length == 4096

    def test_send_success(self, monkeypatch):
        ch = TelegramChannel(bot_token="tok", chat_id="123")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert "api.telegram.org" in url
            assert json["chat_id"] == "123"
            assert json["text"] == "hello"
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_retry_without_parse_mode(self, monkeypatch):
        """First call returns non-200, retry without parse_mode succeeds."""
        ch = TelegramChannel(bot_token="tok", chat_id="123")
        call_count = {"n": 0}

        class FailResponse:
            status_code = 400

            def raise_for_status(self):
                pass

        class OkResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return FailResponse()
            return OkResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True
        assert call_count["n"] == 2

    def test_send_missing_token(self):
        ch = TelegramChannel(bot_token="", chat_id="123")
        with pytest.raises(ValueError, match="bot_token and chat_id"):
            ch.send("hello")

    def test_send_missing_chat_id(self):
        ch = TelegramChannel(bot_token="tok", chat_id="")
        with pytest.raises(ValueError, match="bot_token and chat_id"):
            ch.send("hello")

    def test_send_network_error(self, monkeypatch):
        ch = TelegramChannel(bot_token="tok", chat_id="123")

        def fake_post(url, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr("httpx.post", fake_post)
        with pytest.raises(httpx.ConnectError):
            ch.send("hello")


# ── Email ───────────────────────────────────────────────────────────────


class TestEmailChannel:
    def test_construction(self):
        ch = EmailChannel(smtp_host="smtp.example.com", smtp_user="u", smtp_pass="p", to="r")
        assert ch.smtp_host == "smtp.example.com"
        assert ch.smtp_port == 587

    def test_name(self):
        ch = EmailChannel()
        assert ch.name == "email"

    def test_max_length_default(self):
        ch = EmailChannel()
        assert ch.max_length == 4096

    def test_send_smtp_port_587(self, monkeypatch):
        ch = EmailChannel(smtp_host="smtp.ex.com", smtp_port=587, smtp_user="u", smtp_pass="p", to="r")

        class FakeSMTP:
            def starttls(self): pass
            def login(self, u, p): pass
            def send_message(self, msg): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("smtplib.SMTP", lambda h, p: FakeSMTP())
        assert ch.send("hello", "Test") is True

    def test_send_smtp_port_465(self, monkeypatch):
        ch = EmailChannel(smtp_host="smtp.ex.com", smtp_port=465, smtp_user="u", smtp_pass="p", to="r")

        class FakeSMTPSSL:
            def login(self, u, p): pass
            def send_message(self, msg): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("smtplib.SMTP_SSL", lambda h, p: FakeSMTPSSL())
        assert ch.send("hello", "Test") is True

    def test_send_unknown_provider(self):
        ch = EmailChannel(provider="ses")
        with pytest.raises(ValueError, match="Unknown email provider"):
            ch.send("hello")


# ── Lark ────────────────────────────────────────────────────────────────


class TestLarkChannel:
    def test_construction(self):
        ch = LarkChannel(webhook_url="https://hook.lark.example")
        assert ch.webhook_url == "https://hook.lark.example"

    def test_name(self):
        ch = LarkChannel(webhook_url="x")
        assert ch.name == "lark"

    def test_max_length_default(self):
        ch = LarkChannel(webhook_url="x")
        assert ch.max_length == 4096

    def test_send_success(self, monkeypatch):
        ch = LarkChannel(webhook_url="https://hook.lark.example")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert json["msg_type"] == "text"
            assert json["content"]["text"] == "hello"
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_missing_url(self):
        ch = LarkChannel(webhook_url="")
        with pytest.raises(ValueError, match="webhook_url"):
            ch.send("hello")

    def test_send_non_200(self, monkeypatch):
        ch = LarkChannel(webhook_url="https://hook.lark.example")

        class FakeResponse:
            status_code = 500

            def raise_for_status(self):
                raise httpx.HTTPStatusError("error", request=None, response=None)

        monkeypatch.setattr("httpx.post", lambda *a, **kw: FakeResponse())
        with pytest.raises(httpx.HTTPStatusError):
            ch.send("hello")


# ── DingTalk ────────────────────────────────────────────────────────────


class TestDingTalkChannel:
    def test_construction(self):
        ch = DingTalkChannel(webhook_url="https://oapi.dingtalk.com/robot/send")
        assert ch.webhook_url == "https://oapi.dingtalk.com/robot/send"

    def test_name(self):
        ch = DingTalkChannel(webhook_url="x")
        assert ch.name == "dingtalk"

    def test_max_length_default(self):
        ch = DingTalkChannel(webhook_url="x")
        assert ch.max_length == 4096

    def test_send_success(self, monkeypatch):
        ch = DingTalkChannel(webhook_url="https://hook.ding.example")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert json["msg_type"] == "text"
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_missing_url(self):
        ch = DingTalkChannel(webhook_url="")
        with pytest.raises(ValueError, match="webhook_url"):
            ch.send("hello")

    def test_send_network_error(self, monkeypatch):
        ch = DingTalkChannel(webhook_url="https://hook.ding.example")

        def fake_post(url, json, timeout):
            raise httpx.ConnectError("timeout")

        monkeypatch.setattr("httpx.post", fake_post)
        with pytest.raises(httpx.ConnectError):
            ch.send("hello")


# ── Discord ─────────────────────────────────────────────────────────────


class TestDiscordChannel:
    def test_construction(self):
        ch = DiscordChannel(webhook_url="https://discord.com/api/webhooks/xxx")
        assert ch.webhook_url == "https://discord.com/api/webhooks/xxx"

    def test_name(self):
        ch = DiscordChannel(webhook_url="x")
        assert ch.name == "discord"

    def test_max_length(self):
        ch = DiscordChannel(webhook_url="x")
        assert ch.max_length == 2000  # Discord-specific limit

    def test_send_success(self, monkeypatch):
        ch = DiscordChannel(webhook_url="https://discord.com/api/webhooks/xxx")

        class FakeResponse:
            status_code = 204

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert "content" in json
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_missing_url(self):
        ch = DiscordChannel(webhook_url="")
        with pytest.raises(ValueError, match="webhook_url"):
            ch.send("hello")

    def test_send_truncates_content(self, monkeypatch):
        ch = DiscordChannel(webhook_url="https://discord.com/api/webhooks/xxx")
        captured = {}

        class FakeResponse:
            status_code = 204

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            captured["content"] = json["content"]
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        long_text = "x" * 3000
        ch.send(long_text)
        assert len(captured["content"]) == 2000


# ── WeCom ───────────────────────────────────────────────────────────────


class TestWeComChannel:
    def test_construction(self):
        ch = WeComChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send")
        assert ch.webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

    def test_name(self):
        ch = WeComChannel(webhook_url="x")
        assert ch.name == "wecom"

    def test_max_length_default(self):
        ch = WeComChannel(webhook_url="x")
        assert ch.max_length == 4096

    def test_send_success(self, monkeypatch):
        ch = WeComChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert json["msgtype"] == "text"
            assert "content" in json["text"]
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_missing_url(self):
        ch = WeComChannel(webhook_url="")
        with pytest.raises(ValueError, match="webhook_url"):
            ch.send("hello")

    def test_send_non_200(self, monkeypatch):
        ch = WeComChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send")

        class FakeResponse:
            status_code = 403

            def raise_for_status(self):
                raise httpx.HTTPStatusError("forbidden", request=None, response=None)

        monkeypatch.setattr("httpx.post", lambda *a, **kw: FakeResponse())
        with pytest.raises(httpx.HTTPStatusError):
            ch.send("hello")


# ── WeChat ──────────────────────────────────────────────────────────────


class TestWeChatChannel:
    def test_construction(self):
        ch = WeChatChannel(webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send")
        assert ch.webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

    def test_name(self):
        ch = WeChatChannel(webhook_url="x")
        assert ch.name == "wechat"

    def test_max_length_default(self):
        ch = WeChatChannel(webhook_url="x")
        assert ch.max_length == 4096

    def test_send_success(self, monkeypatch):
        ch = WeChatChannel(webhook_url="https://hook.wechat.example")

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        def fake_post(url, json, timeout):
            assert json["msg_type"] == "text"
            assert json["content"]["text"] == "hello"
            return FakeResponse()

        monkeypatch.setattr("httpx.post", fake_post)
        assert ch.send("hello") is True

    def test_send_missing_url(self):
        ch = WeChatChannel(webhook_url="")
        with pytest.raises(ValueError, match="webhook_url"):
            ch.send("hello")

    def test_send_network_error(self, monkeypatch):
        ch = WeChatChannel(webhook_url="https://hook.wechat.example")

        def fake_post(url, json, timeout):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr("httpx.post", fake_post)
        with pytest.raises(httpx.ConnectError):
            ch.send("hello")
