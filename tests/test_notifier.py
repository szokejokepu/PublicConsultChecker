"""Tests for notifier.sender — email building and sending logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import smtplib

import pytest

from notifier.sender import (
    ConsultationAlert,
    NotifierConfig,
    build_message,
    send_digest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _alert(**kwargs) -> ConsultationAlert:
    defaults = dict(
        article_id=1,
        title="Consultare publică privind proiectul de buget",
        url="https://example.com/1",
        date="2026-04-02",
        classifier_score=0.92,
        extracted_date="2026-04-15",
        extracted_time="14:00",
        extracted_place="Sala Mare",
        extracted_subject="Buget local 2026",
    )
    defaults.update(kwargs)
    return ConsultationAlert(**defaults)


def _config(**kwargs) -> NotifierConfig:
    cfg = NotifierConfig.__new__(NotifierConfig)
    cfg.smtp_host = kwargs.get("smtp_host", "smtp.example.com")
    cfg.smtp_port = kwargs.get("smtp_port", 587)
    cfg.smtp_user = kwargs.get("smtp_user", "user@example.com")
    cfg.smtp_password = kwargs.get("smtp_password", "secret")
    cfg.from_addr = kwargs.get("from_addr", "user@example.com")
    cfg.to_addr = kwargs.get("to_addr", "recipient@example.com")
    return cfg


# ---------------------------------------------------------------------------
# NotifierConfig
# ---------------------------------------------------------------------------


class TestNotifierConfig:
    def test_validate_passes_with_all_vars(self):
        cfg = _config()
        cfg.validate()  # should not raise

    def test_validate_raises_if_user_missing(self):
        cfg = _config(smtp_user="")
        with pytest.raises(ValueError, match="NOTIFIER_SMTP_USER"):
            cfg.validate()

    def test_validate_raises_if_password_missing(self):
        cfg = _config(smtp_password="")
        with pytest.raises(ValueError, match="NOTIFIER_SMTP_PASSWORD"):
            cfg.validate()

    def test_validate_raises_if_to_missing(self):
        cfg = _config(to_addr="")
        with pytest.raises(ValueError, match="NOTIFIER_TO"):
            cfg.validate()

    def test_validate_lists_all_missing(self):
        cfg = _config(smtp_user="", smtp_password="", to_addr="")
        with pytest.raises(ValueError) as exc_info:
            cfg.validate()
        msg = str(exc_info.value)
        assert "NOTIFIER_SMTP_USER" in msg
        assert "NOTIFIER_SMTP_PASSWORD" in msg
        assert "NOTIFIER_TO" in msg

    def test_from_addr_defaults_to_smtp_user(self, monkeypatch):
        monkeypatch.setenv("NOTIFIER_SMTP_USER", "me@example.com")
        monkeypatch.delenv("NOTIFIER_FROM", raising=False)
        monkeypatch.delenv("NOTIFIER_SMTP_HOST", raising=False)
        monkeypatch.delenv("NOTIFIER_SMTP_PORT", raising=False)
        monkeypatch.delenv("NOTIFIER_SMTP_PASSWORD", raising=False)
        monkeypatch.delenv("NOTIFIER_TO", raising=False)
        cfg = NotifierConfig()
        assert cfg.from_addr == "me@example.com"


# ---------------------------------------------------------------------------
# build_message
# ---------------------------------------------------------------------------


class TestBuildMessage:
    def test_subject_single_alert(self):
        msg = build_message([_alert()], "from@ex.com", "to@ex.com")
        assert msg["Subject"] == "[RAG] 1 new public consultation detected"

    def test_subject_plural(self):
        msg = build_message([_alert(), _alert(article_id=2)], "from@ex.com", "to@ex.com")
        assert msg["Subject"] == "[RAG] 2 new public consultations detected"

    def test_from_and_to_headers(self):
        msg = build_message([_alert()], "from@ex.com", "to@ex.com")
        assert msg["From"] == "from@ex.com"
        assert msg["To"] == "to@ex.com"

    def test_has_plain_and_html_parts(self):
        msg = build_message([_alert()], "f@ex.com", "t@ex.com")
        content_types = [p.get_content_type() for p in msg.get_payload()]
        assert "text/plain" in content_types
        assert "text/html" in content_types

    def test_plain_contains_title(self):
        a = _alert(title="My Consultation Title")
        msg = build_message([a], "f@ex.com", "t@ex.com")
        plain = next(p for p in msg.get_payload() if p.get_content_type() == "text/plain")
        assert "My Consultation Title" in plain.get_payload(decode=True).decode()

    def test_plain_contains_url(self):
        a = _alert(url="https://example.com/article/99")
        msg = build_message([a], "f@ex.com", "t@ex.com")
        plain = next(p for p in msg.get_payload() if p.get_content_type() == "text/plain")
        assert "https://example.com/article/99" in plain.get_payload(decode=True).decode()

    def test_html_contains_url_as_link(self):
        a = _alert(url="https://example.com/article/99")
        msg = build_message([a], "f@ex.com", "t@ex.com")
        html = next(p for p in msg.get_payload() if p.get_content_type() == "text/html")
        assert "https://example.com/article/99" in html.get_payload(decode=True).decode()

    def test_none_title_shows_fallback(self):
        a = _alert(title=None)
        msg = build_message([a], "f@ex.com", "t@ex.com")
        plain = next(p for p in msg.get_payload() if p.get_content_type() == "text/plain")
        assert "(no title)" in plain.get_payload(decode=True).decode()

    def test_none_score_shows_dash_in_html(self):
        a = _alert(classifier_score=None)
        msg = build_message([a], "f@ex.com", "t@ex.com")
        html = next(p for p in msg.get_payload() if p.get_content_type() == "text/html")
        assert "—" in html.get_payload(decode=True).decode("utf-8")

    def test_custom_sent_at(self):
        msg = build_message([_alert()], "f@ex.com", "t@ex.com", sent_at="2026-04-02 08:00 UTC")
        plain = next(p for p in msg.get_payload() if p.get_content_type() == "text/plain")
        assert "2026-04-02 08:00 UTC" in plain.get_payload(decode=True).decode()


# ---------------------------------------------------------------------------
# send_digest
# ---------------------------------------------------------------------------


class TestSendDigest:
    def _send(self, alerts, cfg=None):
        """Call send_digest with a fully mocked SMTP session."""
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_server) as mock_smtp:
            send_digest(alerts, cfg or _config())
            return mock_smtp, mock_server

    def test_connects_to_correct_host_and_port(self):
        cfg = _config(smtp_host="smtp.myhost.com", smtp_port=465)
        mock_smtp, _ = self._send([_alert()], cfg)
        mock_smtp.assert_called_once_with("smtp.myhost.com", 465)

    def test_starts_tls(self):
        _, server = self._send([_alert()])
        server.starttls.assert_called_once()

    def test_logs_in_with_credentials(self):
        cfg = _config(smtp_user="u@ex.com", smtp_password="pass123")
        _, server = self._send([_alert()], cfg)
        server.login.assert_called_once_with("u@ex.com", "pass123")

    def test_sends_to_correct_recipient(self):
        cfg = _config(from_addr="from@ex.com", to_addr="to@ex.com")
        _, server = self._send([_alert()], cfg)
        args = server.sendmail.call_args[0]
        assert args[0] == "from@ex.com"
        assert args[1] == "to@ex.com"

    def test_message_string_sent(self):
        _, server = self._send([_alert()])
        assert server.sendmail.call_count == 1
        message_str = server.sendmail.call_args[0][2]
        assert isinstance(message_str, str)
        assert "Content-Type: multipart/alternative" in message_str

    def test_raises_on_invalid_config(self):
        cfg = _config(smtp_user="", smtp_password="", to_addr="")
        with pytest.raises(ValueError):
            send_digest([_alert()], cfg)

    def test_smtp_exception_propagates(self):
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        mock_server.sendmail.side_effect = smtplib.SMTPException("delivery failed")

        with patch("smtplib.SMTP", return_value=mock_server):
            with pytest.raises(smtplib.SMTPException, match="delivery failed"):
                send_digest([_alert()], _config())
