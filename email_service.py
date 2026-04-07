"""
EmailService
────────────
Envia e-mails de alerta via SMTP.

Suporta:
  - TLS/STARTTLS  (porta 587, padrão Gmail/Outlook)
  - SSL direto    (porta 465)

Cooldown interno: evita spam repetindo o mesmo alerta antes de COOLDOWN_HOURS horas.
"""

import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable

import keyring

from config_manager import KEYRING_SERVICE, KEYRING_SMTP_PASSWORD

COOLDOWN_HOURS = 12   # intervalo mínimo entre alertas do mesmo tipo por perfil


class EmailService:
    def __init__(self, config: dict, log_fn: Callable):
        self.cfg  = config
        self.log  = log_fn
        # {chave → datetime} — controla cooldown por tipo de alerta e perfil
        self._last_sent: dict[str, datetime] = {}

    def update_config(self, config: dict):
        self.cfg = config

    def _get_password(self) -> str:
        inline_password = self.cfg.get("smtp_password", "")
        if inline_password:
            return inline_password
        try:
            return keyring.get_password(KEYRING_SERVICE, KEYRING_SMTP_PASSWORD) or ""
        except Exception:
            return ""

    def is_configured(self) -> bool:
        return bool(
            self.cfg.get("smtp_host") and
            self.cfg.get("smtp_user") and
            self._get_password() and
            self.cfg.get("to_addr")
        )

    # ── Cooldown ─────────────────────────────────────────────────────────────
    def _cooldown_ok(self, key: str) -> bool:
        last = self._last_sent.get(key)
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() / 3600 >= COOLDOWN_HOURS

    def _mark_sent(self, key: str):
        self._last_sent[key] = datetime.now()

    # ── Envio raw ─────────────────────────────────────────────────────────────
    def send(self, subject: str, body: str) -> bool:
        """Envia e-mail SMTP. Não aplica cooldown — use os métodos de alerta."""
        if not self.is_configured():
            self.log("E-mail não configurado — alerta não enviado.", "WARN")
            return False
        try:
            host    = self.cfg["smtp_host"]
            port    = int(self.cfg.get("smtp_port", 587))
            user    = self.cfg["smtp_user"]
            pwd     = self._get_password()
            to_addr = self.cfg["to_addr"]
            use_tls = self.cfg.get("use_tls", True)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = user
            msg["To"]      = to_addr
            msg.attach(MIMEText(body, "plain", "utf-8"))

            ctx = ssl.create_default_context()
            if use_tls:
                with smtplib.SMTP(host, port, timeout=15) as srv:
                    srv.ehlo()
                    srv.starttls(context=ctx)
                    srv.login(user, pwd)
                    srv.sendmail(user, to_addr, msg.as_string())
            else:
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as srv:
                    srv.login(user, pwd)
                    srv.sendmail(user, to_addr, msg.as_string())

            self.log(f"E-mail de alerta enviado para {to_addr}", "OK")
            return True
        except Exception as e:
            self.log(f"Falha ao enviar e-mail de alerta: {e}", "WARN")
            return False

    # ── Alertas específicos ───────────────────────────────────────────────────
    def alert_sem_backup(self, profile: dict, newest_file: str, days_old: int):
        """
        Rotação: backup mais recente está há N dias sem atualizar.
        Cooldown: 12 h por perfil.
        """
        pid = profile.get("id", "")
        key = f"{pid}:sem_backup"
        if not self._cooldown_ok(key):
            return

        nome    = profile.get("nome", "?")
        cliente = profile.get("cliente", "?")
        pasta   = profile.get("backup_dir", "?")
        horas   = days_old * 24
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        subject = f"⚠ GR7 Backup — [{cliente}] sem novos backups há {days_old} dia(s)"
        body = (
            f"Olá,\n\n"
            f"CLIENTE : {cliente}\n"
            f"PERFIL  : {nome}\n\n"
            f"Não foi recebido nenhum novo arquivo de backup há mais de "
            f"{horas} horas ({days_old} dia(s)).\n\n"
            f"  Último backup detectado : {newest_file}\n"
            f"  Pasta monitorada        : {pasta}\n"
            f"  Verificado em           : {now_str}\n\n"
            f"Por favor, verifique se o sistema que gera os backups está funcionando "
            f"corretamente e se os arquivos estão sendo gerados na pasta configurada.\n\n"
            f"---\nGR7 Backup Manager"
        )
        if self.send(subject, body):
            self._mark_sent(key)

    def alert_erro_upload(self, profile: dict, filename: str):
        """
        Falha ao enviar um arquivo para o Drive.
        Cooldown: 12 h por (perfil + arquivo).
        """
        pid = profile.get("id", "")
        key = f"{pid}:erro_upload:{filename}"
        if not self._cooldown_ok(key):
            return

        nome    = profile.get("nome", "?")
        cliente = profile.get("cliente", "?")
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        subject = f"❌ GR7 Backup — [{cliente}] falha no envio de arquivo"
        body = (
            f"Olá,\n\n"
            f"CLIENTE : {cliente}\n"
            f"PERFIL  : {nome}\n\n"
            f"Ocorreu uma falha ao enviar o arquivo de backup para o Google Drive.\n\n"
            f"  Arquivo : {filename}\n"
            f"  Horário : {now_str}\n\n"
            f"Por favor, verifique a conexão com o Google Drive e abra o programa "
            f"GR7 Backup Manager para mais detalhes no log.\n\n"
            f"---\nGR7 Backup Manager"
        )
        if self.send(subject, body):
            self._mark_sent(key)

    def alert_erro_sync(self, profile: dict, detalhe: str):
        """
        Erro geral que interrompeu a sincronização de um perfil.
        Cooldown: 12 h por perfil.
        """
        pid = profile.get("id", "")
        key = f"{pid}:erro_sync"
        if not self._cooldown_ok(key):
            return

        nome    = profile.get("nome", "?")
        cliente = profile.get("cliente", "?")
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        subject = f"❌ GR7 Backup — [{cliente}] erro na sincronização"
        body = (
            f"Olá,\n\n"
            f"CLIENTE : {cliente}\n"
            f"PERFIL  : {nome}\n\n"
            f"Ocorreu um erro durante a sincronização que pode ter impedido o "
            f"funcionamento correto do backup.\n\n"
            f"  Detalhe : {detalhe}\n"
            f"  Horário : {now_str}\n\n"
            f"Por favor, verifique o programa GR7 Backup Manager e o log de eventos.\n\n"
            f"---\nGR7 Backup Manager"
        )
        if self.send(subject, body):
            self._mark_sent(key)
