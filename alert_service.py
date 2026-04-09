from __future__ import annotations

import socket
from datetime import datetime, timedelta
from typing import Callable

from email_service import EmailService

ADMIN_ALERT_COOLDOWN_HOURS = 12


class AlertService:
    def __init__(self, config_mgr, email_svc: EmailService, log_fn: Callable):
        self.config_mgr = config_mgr
        self.email_svc = email_svc
        self.log = log_fn

    def notify_admin_event(self, event: dict):
        if not isinstance(event, dict):
            return
        event_code = str(event.get("event_code") or "").strip()
        if not event_code:
            return

        data = self.config_mgr.load()
        if not data.get("admin_alerts_enabled", False):
            return
        if not self.email_svc.is_configured():
            self.log("E-mail administrativo não configurado — alerta não enviado.", "WARN")
            return

        installation_label = self._installation_label(data)
        details = str(event.get("message") or "").strip()
        state_key = f"admin:{data.get('installation_id', '')}:{event_code}"
        alert_state = data.get("alert_state", {})
        current_state = alert_state.get(state_key, {})

        if not self._cooldown_ok(current_state, details):
            return

        subject, body = self._compose_admin_email(event, installation_label, details)
        if self.email_svc.send(subject, body):
            self.config_mgr.update(lambda cfg: cfg.setdefault("alert_state", {}).__setitem__(
                state_key,
                {
                    "last_sent_at": datetime.now().isoformat(timespec="seconds"),
                    "last_message": details,
                },
            ))

    @staticmethod
    def _cooldown_ok(state: dict, details: str) -> bool:
        last_sent = str(state.get("last_sent_at", "") or "").strip()
        last_message = str(state.get("last_message", "") or "").strip()
        if not last_sent:
            return True
        try:
            sent_at = datetime.fromisoformat(last_sent)
        except ValueError:
            return True
        if details and details != last_message:
            return True
        return datetime.now() - sent_at >= timedelta(hours=ADMIN_ALERT_COOLDOWN_HOURS)

    @staticmethod
    def _installation_label(data: dict) -> str:
        label = str(data.get("installation_label", "") or "").strip()
        if label:
            return label
        try:
            return socket.gethostname().strip()
        except Exception:
            return "Instalação não identificada"

    @staticmethod
    def _compose_admin_email(event: dict, installation_label: str, details: str) -> tuple[str, str]:
        event_code = str(event.get("event_code") or "").strip()
        title = str(event.get("title") or "Alerta administrativo").strip()
        hostname = str(event.get("hostname") or socket.gethostname()).strip()
        occurred_at = str(event.get("occurred_at") or datetime.now().strftime("%d/%m/%Y %H:%M")).strip()
        action = str(event.get("action") or "Verifique o aplicativo e tome a ação necessária.").strip()

        subject = f"⚠ GR7 Backup — [{installation_label}] {title}"
        body = (
            f"Olá,\n\n"
            f"INSTALAÇÃO : {installation_label}\n"
            f"HOST       : {hostname}\n"
            f"EVENTO     : {title}\n"
            f"CÓDIGO     : {event_code}\n"
            f"HORÁRIO    : {occurred_at}\n\n"
            f"DETALHE:\n"
            f"{details or 'Sem detalhe adicional.'}\n\n"
            f"AÇÃO RECOMENDADA:\n"
            f"{action}\n\n"
            f"---\nGR7 Backup Manager"
        )
        return subject, body
