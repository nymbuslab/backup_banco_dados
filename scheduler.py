"""
SyncScheduler
─────────────
Dois modos de operação, controlados pelo botão master (sync ativo/inativo):

  MODO CONTÍNUO (agendador desativado):
    Roda o sync a cada CONTINUOUS_INTERVAL segundos (padrão: 5 min).
    Simula verificação constante sem sobrecarregar a API.

  MODO AGENDADO (agendador ativado):
    Roda o sync no intervalo configurado pelo usuário (30min, 1h, 2h...).

O botão Sincronizar controla se o processo está ativo (start/stop).
O switch de agendamento só controla a frequência.
"""

import threading
from datetime import datetime, timedelta
from typing import Callable

CONTINUOUS_INTERVAL = 5 * 60   # 5 minutos no modo contínuo


class SyncScheduler:
    INTERVALS = {
        "30 min":   30 * 60,
        "1 hora":   1  * 3600,
        "2 horas":  2  * 3600,
        "4 horas":  4  * 3600,
        "6 horas":  6  * 3600,
        "12 horas": 12 * 3600,
        "24 horas": 24 * 3600,
    }

    def __init__(self, sync_fn: Callable, log_fn: Callable, cancel_evt=None):
        self._sync          = sync_fn
        self._log           = log_fn
        self._cancel_evt    = cancel_evt
        self._active        = False     # master: sync ligado/desligado
        self._use_interval  = False     # se True usa _interval; se False usa CONTINUOUS
        self._interval      = 3600
        self._running       = False
        self._thread        = None
        self._stop_evt      = threading.Event()
        self._last_run      = None
        self._next_run      = None
        self._lock          = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────
    def start(self):
        """Liga o processo de sync (botão master)."""
        if self._cancel_evt is not None:
            try:
                self._cancel_evt.clear()
            except Exception:
                pass
        with self._lock:
            self._active   = True
            self._next_run = datetime.now()   # primeira execução imediata
        if not self._running:
            self._start_thread()

    def stop(self):
        """Desliga o processo de sync completamente."""
        if self._cancel_evt is not None:
            try:
                self._cancel_evt.set()
            except Exception:
                pass
        with self._lock:
            self._active = False
        self._stop_evt.set()
        self._running = False

    def set_use_interval(self, enabled: bool):
        """
        True  → modo agendado (usa _interval configurado)
        False → modo contínuo (usa CONTINUOUS_INTERVAL)
        """
        with self._lock:
            self._use_interval = enabled
            # Recalcula próximo run imediatamente se estiver ativo
            if self._active and self._last_run:
                secs = self._interval if enabled else CONTINUOUS_INTERVAL
                self._next_run = self._last_run + timedelta(seconds=secs)

    def set_interval(self, label: str):
        """Define o intervalo pelo label (ex: '1 hora')."""
        seconds = self.INTERVALS.get(label)
        if seconds:
            with self._lock:
                self._interval = seconds
                if self._active and self._use_interval and self._last_run:
                    self._next_run = self._last_run + timedelta(seconds=seconds)

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def get_status(self) -> dict:
        with self._lock:
            secs  = self._interval if self._use_interval else CONTINUOUS_INTERVAL
            return {
                "active":        self._active,
                "use_interval":  self._use_interval,
                "interval_secs": secs,
                "last_run":      self._last_run.strftime("%d/%m/%Y %H:%M:%S") if self._last_run else "—",
                "next_run":      self._next_run.strftime("%d/%m/%Y %H:%M:%S") if self._next_run and self._active else "—",
            }

    # ── Internals ─────────────────────────────────────────────────────────────
    def _start_thread(self):
        self._stop_evt.clear()
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop_evt.is_set():
            with self._lock:
                active   = self._active
                next_run = self._next_run

            if active and next_run and datetime.now() >= next_run:
                self._do_sync()

            timeout = 1.0
            if active and next_run:
                delta = (next_run - datetime.now()).total_seconds()
                timeout = min(1.0, max(0.2, delta))
            self._stop_evt.wait(timeout=timeout)

    def _do_sync(self):
        with self._lock:
            self._last_run = datetime.now()
            secs           = self._interval if self._use_interval else CONTINUOUS_INTERVAL
            self._next_run = self._last_run + timedelta(seconds=secs)

        try:
            self._sync()
        except Exception as e:
            self._log(f"Erro no sync: {e}", "ERROR")
