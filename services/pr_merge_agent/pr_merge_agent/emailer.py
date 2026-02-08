from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable


class Emailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        email_from: str,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from = email_from

    def send_html(self, *, to_emails: Iterable[str], subject: str, html: str, text: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["From"] = self._from
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(self._host, self._port, timeout=20) as server:
            server.ehlo()
            if self._use_tls:
                server.starttls()
                server.ehlo()
            if self._username:
                server.login(self._username, self._password)
            server.sendmail(self._from, list(to_emails), msg.as_string())
