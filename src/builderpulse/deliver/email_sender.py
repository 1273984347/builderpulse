"""Email delivery channel."""

from __future__ import annotations

from .base import DeliveryChannel


class EmailChannel(DeliveryChannel):
    # Plugin Protocol: required class attribute (Task 23).
    name = "email"

    def __init__(
        self,
        provider: str = "smtp",
        smtp_host: str = "",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_pass: str = "",
        to: str = "",
        **kwargs,
    ):
        self.provider = provider
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self.to = to

    def send(self, content: str, title: str = "", content_type: str = "text") -> bool:
        if self.provider == "smtp":
            return self._send_smtp(content, title)
        raise ValueError(f"Unknown email provider: {self.provider}")

    def _send_smtp(self, content: str, title: str) -> bool:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(content, "plain")
        msg["Subject"] = title or "BuilderPulse Digest"
        msg["From"] = self.smtp_user
        msg["To"] = self.to

        # P1 fix: SMTP_SSL for port 465, SMTP+STARTTLS for port 587
        if self.smtp_port == 465:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as s:
                s.login(self.smtp_user, self.smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as s:
                s.starttls()
                s.login(self.smtp_user, self.smtp_pass)
                s.send_message(msg)
        return True
