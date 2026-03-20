import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
from datetime import datetime

from config_manager import ConfigManager
from drive_service   import DriveService
from backup_manager  import BackupManager
from scheduler       import SyncScheduler
import autostart

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

APP_NAME      = "GR7 Backup Manager"
DEFAULT_PASTA = "GR7 BACKUP MANAGER"

BG_DARK        = "#0D1117"
BG_CARD        = "#161B22"
BG_INPUT       = "#1C2128"
BORDER         = "#30363D"
ACCENT         = "#238636"
ACCENT_HOV     = "#2EA043"
ACCENT_RED     = "#B91C1C"
ACCENT_RED_HOV = "#991B1B"
TEXT_PRI       = "#E6EDF3"
TEXT_SEC       = "#8B949E"
TEXT_GRN       = "#3FB950"
TEXT_RED       = "#F85149"
TEXT_YEL       = "#D29922"
FONT_MONO      = ("Consolas", 11)
FONT_HEAD      = ("Segoe UI", 20, "bold")
FONT_SUB       = ("Segoe UI", 12, "bold")
FONT_BODY      = ("Segoe UI", 11)
FONT_SMALL     = ("Segoe UI", 10)


def _resolve_icon() -> str | None:
    """
    Localiza gr7backup.ico em todas as localizações possíveis:

    .exe (PyInstaller --onefile):
        sys._MEIPASS/assets/gr7backup.ico   ← --add-data "assets\\gr7backup.ico;assets"
        sys._MEIPASS/gr7backup.ico           ← --add-data "assets\\gr7backup.ico;."
        <pasta do .exe>/assets/gr7backup.ico ← copiado manualmente
        <pasta do .exe>/gr7backup.ico        ← copiado manualmente raiz

    .py (desenvolvimento):
        <pasta do main.py>/assets/gr7backup.ico
        <pasta do main.py>/gr7backup.ico
    """
    candidates = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        for base in [meipass, exe_dir]:
            if base:
                candidates.append(os.path.join(base, "assets", "gr7backup.ico"))
                candidates.append(os.path.join(base, "gr7backup.ico"))
    else:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates.append(os.path.join(base, "assets", "gr7backup.ico"))
        candidates.append(os.path.join(base, "gr7backup.ico"))

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class BackupApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1120x740")
        self.minsize(960, 600)
        self.configure(fg_color=BG_DARK)

        # ── Ícone ────────────────────────────────────────────────────────────
        ico = _resolve_icon()
        if ico:
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

        # ── Serviços ─────────────────────────────────────────────────────────
        self.config_mgr = ConfigManager()
        self.drive_svc  = DriveService(self.log)
        self.backup_mgr = BackupManager(self.drive_svc, self.log, self.refresh_history)
        self.scheduler  = SyncScheduler(self._do_background_sync, self.log)

        self._sync_lock       = threading.Lock()
        self._sync_cancel_evt = threading.Event()
        self._tray_icon       = None
        self._drive_connected = False
        # Guarda os valores salvos para detectar mudanças não salvas
        self._saved_snapshot  = {}
        self._progress_active = False
        self._progress_start  = None

        self._build_ui()
        self._load_config()
        self._check_drive_connection()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick_scheduler_status()

    # ═══════════════════════════════════════════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_statusbar()

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=64)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20)

        ctk.CTkLabel(inner, text="☁", font=("Segoe UI", 26),
                     text_color=ACCENT).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(inner, text=APP_NAME,
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(side="left")

        ctk.CTkButton(inner, text="⬇ Bandeja", width=90, height=28,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_color=BORDER, border_width=1,
                      font=FONT_SMALL, text_color=TEXT_SEC,
                      command=self._minimize_to_tray).pack(side="right", padx=(6, 0))

        self.conn_badge = ctk.CTkLabel(inner, text="● Desconectado",
                                       font=FONT_SMALL, text_color=TEXT_RED)
        self.conn_badge.pack(side="right", padx=10)

        self.btn_connect = ctk.CTkButton(
            inner, text="Conectar Drive", width=150, height=32,
            fg_color=BG_INPUT, hover_color=BORDER,
            border_color=BORDER, border_width=1,
            font=FONT_SMALL, text_color=TEXT_SEC,
            command=self._toggle_drive_connection)
        self.btn_connect.pack(side="right")

        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x")

    # ── Body ──────────────────────────────────────────────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16)
        body.columnconfigure(0, weight=2, minsize=360)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)
        self._build_config_panel(body)
        self._build_log_panel(body)

    # ── Config panel ──────────────────────────────────────────────────────────
    def _build_config_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=12)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)

        ctk.CTkLabel(card, text="Configuração", font=FONT_SUB,
                     text_color=TEXT_PRI).grid(row=0, column=0,
                                               sticky="w", padx=20, pady=(14, 6))
        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=1, column=0, sticky="ew", padx=20)

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                        scrollbar_button_color=BORDER,
                                        scrollbar_button_hover_color=TEXT_SEC)
        scroll.grid(row=2, column=0, sticky="nsew", padx=2, pady=4)
        scroll.columnconfigure(0, weight=1)

        f = ctk.CTkFrame(scroll, fg_color="transparent")
        f.pack(fill="x", padx=18, pady=(2, 8))
        f.columnconfigure(0, weight=1)

        def lbl(text, row):
            ctk.CTkLabel(f, text=text, font=FONT_SMALL,
                         text_color=TEXT_SEC).grid(row=row, column=0,
                                                   sticky="w", pady=(10, 2))

        def ent(row, placeholder):
            e = ctk.CTkEntry(f, placeholder_text=placeholder,
                             fg_color=BG_INPUT, border_color=BORDER,
                             text_color=TEXT_PRI, height=36, font=FONT_BODY)
            e.grid(row=row, column=0, sticky="ew")
            return e

        lbl("Pasta Pai no Drive", 0)
        self.ent_folder_pai = ent(1, f"ex: {DEFAULT_PASTA}")
        self.ent_folder_pai.insert(0, DEFAULT_PASTA)

        lbl("Cliente (pasta filho)", 2)
        self.ent_cliente = ent(3, "ex: Empresa ABC")

        lbl("Pasta de Backup Local", 4)
        br = ctk.CTkFrame(f, fg_color="transparent")
        br.grid(row=5, column=0, sticky="ew")
        br.columnconfigure(0, weight=1)
        self.ent_backup_dir = ctk.CTkEntry(br, placeholder_text="Selecione a pasta...",
                                           fg_color=BG_INPUT, border_color=BORDER,
                                           text_color=TEXT_PRI, height=36, font=FONT_BODY)
        self.ent_backup_dir.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(br, text="📂", width=36, height=36,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      command=self._browse_folder).grid(row=0, column=1)

        lbl("Backups armazenados (máx.)", 6)
        self.var_qtd = tk.IntVar(value=3)
        self.spin_qtd = ctk.CTkSegmentedButton(
            f, values=["1", "2", "3", "5", "7", "10"],
            variable=tk.StringVar(value="3"),
            fg_color=BG_INPUT, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOV,
            unselected_color=BG_INPUT, unselected_hover_color=BORDER,
            text_color=TEXT_PRI, font=FONT_SMALL,
            command=lambda v: self.var_qtd.set(int(v)))
        self.spin_qtd.grid(row=7, column=0, sticky="w")

        lbl("Extensão dos arquivos de backup", 8)
        self.ent_ext = ctk.CTkEntry(f,
                                    placeholder_text=".sql  (vírgula para múltiplas: .sql,.bak)",
                                    fg_color=BG_INPUT, border_color=BORDER,
                                    text_color=TEXT_PRI, height=36, font=FONT_BODY)
        self.ent_ext.grid(row=9, column=0, sticky="ew", pady=(0, 2))

        # ── Agendamento ─────────────────────────────────────────────────────
        ctk.CTkFrame(f, fg_color=BORDER, height=1).grid(
            row=10, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(f, text="Sincronização Automática", font=FONT_SUB,
                     text_color=TEXT_PRI).grid(row=11, column=0, sticky="w", pady=(10, 6))

        auto_row = ctk.CTkFrame(f, fg_color="transparent")
        auto_row.grid(row=12, column=0, sticky="ew")
        auto_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(auto_row, text="Usar intervalo de agendamento",
                     font=FONT_BODY, text_color=TEXT_PRI).grid(row=0, column=0, sticky="w")
        self.var_auto = tk.BooleanVar(value=False)
        self.sw_auto  = ctk.CTkSwitch(auto_row, text="", variable=self.var_auto,
                                       onvalue=True, offvalue=False,
                                       progress_color=ACCENT,
                                       command=self._on_interval_toggle)
        self.sw_auto.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(f, text="Desativado: verifica a cada 5 min (modo contínuo)",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=13, column=0, sticky="w", pady=(2, 0))

        lbl("Intervalo de agendamento", 14)
        self.var_interval = tk.StringVar(value="1 hora")
        self.cmb_interval = ctk.CTkOptionMenu(
            f, values=list(SyncScheduler.INTERVALS.keys()),
            variable=self.var_interval,
            fg_color=BG_INPUT, button_color=BORDER,
            button_hover_color=TEXT_SEC, text_color=TEXT_PRI,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER,
            dropdown_text_color=TEXT_PRI, font=FONT_BODY, height=36,
            command=self._on_interval_change)
        self.cmb_interval.grid(row=15, column=0, sticky="ew")

        self.lbl_next = ctk.CTkLabel(f, text="Próximo sync: —",
                                      font=FONT_SMALL, text_color=TEXT_SEC)
        self.lbl_next.grid(row=16, column=0, sticky="w", pady=(6, 0))
        self.lbl_last = ctk.CTkLabel(f, text="Último sync:  —",
                                      font=FONT_SMALL, text_color=TEXT_SEC)
        self.lbl_last.grid(row=17, column=0, sticky="w", pady=(2, 0))

        # ── Sistema ─────────────────────────────────────────────────────────
        ctk.CTkFrame(f, fg_color=BORDER, height=1).grid(
            row=18, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkLabel(f, text="Sistema", font=FONT_SUB,
                     text_color=TEXT_PRI).grid(row=19, column=0, sticky="w", pady=(10, 6))

        boot_row = ctk.CTkFrame(f, fg_color="transparent")
        boot_row.grid(row=20, column=0, sticky="ew")
        boot_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(boot_row, text="Iniciar com o Windows",
                     font=FONT_BODY, text_color=TEXT_PRI).grid(row=0, column=0, sticky="w")
        self.var_boot = tk.BooleanVar(value=autostart.is_enabled())
        self.sw_boot  = ctk.CTkSwitch(boot_row, text="", variable=self.var_boot,
                                       onvalue=True, offvalue=False,
                                       progress_color=ACCENT,
                                       command=self._toggle_autostart)
        self.sw_boot.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(f, text="O app inicia minimizado na bandeja do sistema.",
                     font=FONT_SMALL, text_color=TEXT_SEC,
                     wraplength=280, justify="left"
                     ).grid(row=21, column=0, sticky="w", pady=(2, 8))

        # ── Botões fixos ─────────────────────────────────────────────────────
        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=3, column=0, sticky="ew", padx=20)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=20, pady=12)
        btn_row.columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_row, text="💾  Salvar Config",
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SEC, font=FONT_BODY, height=40,
                      command=self._save_config
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_sync = ctk.CTkButton(btn_row, text="▶  Sincronizar",
                                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                                      text_color="white",
                                      font=("Segoe UI", 11, "bold"),
                                      height=40, command=self._on_sync_button)
        self.btn_sync.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    # ── Log + History panel ───────────────────────────────────────────────────
    def _build_log_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.grid(row=0, column=1, sticky="nsew", pady=12)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=3)
        card.rowconfigure(4, weight=2)

        hist_hdr = ctk.CTkFrame(card, fg_color="transparent")
        hist_hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 0))
        ctk.CTkLabel(hist_hdr, text="Histórico de Backups",
                     font=FONT_SUB, text_color=TEXT_PRI).pack(side="left")
        self.lbl_hist_count = ctk.CTkLabel(hist_hdr, text="0 registros",
                                            font=FONT_SMALL, text_color=TEXT_SEC)
        self.lbl_hist_count.pack(side="right")

        self.hist_box = ctk.CTkScrollableFrame(card, fg_color=BG_INPUT,
                                               scrollbar_button_color=BORDER,
                                               scrollbar_button_hover_color=TEXT_SEC,
                                               corner_radius=6)
        self.hist_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(6, 0))
        self.hist_box.columnconfigure(0, weight=1)

        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=2, column=0, sticky="ew", padx=20, pady=(8, 0))

        log_hdr = ctk.CTkFrame(card, fg_color="transparent")
        log_hdr.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 4))
        ctk.CTkLabel(log_hdr, text="Log de Execução",
                     font=FONT_SUB, text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(log_hdr, text="Limpar", width=60, height=24,
                      fg_color="transparent", hover_color=BORDER,
                      text_color=TEXT_SEC, font=FONT_SMALL,
                      command=self._clear_log).pack(side="right")

        self.log_text = ctk.CTkTextbox(card, fg_color=BG_INPUT,
                                       text_color=TEXT_PRI, font=FONT_MONO,
                                       corner_radius=6, wrap="word",
                                       state="disabled")
        self.log_text.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 14))
        self.log_text._textbox.tag_configure("INFO",  foreground=TEXT_SEC)
        self.log_text._textbox.tag_configure("OK",    foreground=TEXT_GRN)
        self.log_text._textbox.tag_configure("WARN",  foreground=TEXT_YEL)
        self.log_text._textbox.tag_configure("ERROR", foreground=TEXT_RED)
        self.log_text._textbox.tag_configure("PROGRESS", foreground=TEXT_SEC)

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.lbl_status = ctk.CTkLabel(bar, text="Pronto.",
                                       font=FONT_SMALL, text_color=TEXT_SEC)
        self.lbl_status.pack(side="left", padx=14)
        self.lbl_sched_status = ctk.CTkLabel(bar, text="",
                                              font=FONT_SMALL, text_color=TEXT_GRN)
        self.lbl_sched_status.pack(side="right", padx=14)
        self.progress = ctk.CTkProgressBar(bar, width=160, height=6,
                                            fg_color=BORDER, progress_color=ACCENT)
        self.progress.pack(side="right", padx=(0, 10))
        self.progress.set(0)

    # ═══════════════════════════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════════════════════════
    def log(self, msg: str, level: str = "INFO"):
        def _do():
            ts   = datetime.now().strftime("%H:%M:%S")
            icon = {"INFO": "ℹ", "OK": "✔", "WARN": "⚠", "ERROR": "✖", "PROGRESS": "↑"}.get(level, "·")
            line = f"[{ts}] {icon} {msg}\n"
            self.log_text.configure(state="normal")
            if level == "PROGRESS":
                if self._progress_active and self._progress_start is not None:
                    self.log_text._textbox.delete(self._progress_start, "end-1c")
                self._progress_start = self.log_text._textbox.index("end-1c")
                self._progress_active = True
                self.log_text._textbox.insert("end", line, level)
            else:
                self._progress_active = False
                self._progress_start  = None
                self.log_text._textbox.insert("end", line, level)
            self.log_text._textbox.see("end")
            self.log_text.configure(state="disabled")
            self.lbl_status.configure(text=msg[:90])
        self.after(0, _do)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")
        self._progress_active = False
        self._progress_start  = None

    # ═══════════════════════════════════════════════════════════════════════════
    #  HISTORY
    # ═══════════════════════════════════════════════════════════════════════════
    def refresh_history(self, entries: list):
        def _do():
            for w in self.hist_box.winfo_children():
                w.destroy()
            self.lbl_hist_count.configure(text=f"{len(entries)} registros")
            if not entries:
                ctk.CTkLabel(self.hist_box, text="Nenhum backup registrado ainda.",
                             font=FONT_SMALL, text_color=TEXT_SEC).pack(pady=20)
                return
            for e in reversed(entries):
                sc  = TEXT_GRN if e.get("status") == "OK" else TEXT_RED
                row = ctk.CTkFrame(self.hist_box, fg_color=BG_CARD, corner_radius=6,
                                   border_width=1, border_color=BORDER)
                row.pack(fill="x", pady=2, padx=4)
                row.columnconfigure(1, weight=1)
                ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                             text_color=sc, width=20
                             ).grid(row=0, column=0, padx=(10, 0), pady=7)
                ctk.CTkLabel(row, text=e.get("filename", "—"),
                             font=FONT_MONO, text_color=TEXT_PRI, anchor="w"
                             ).grid(row=0, column=1, sticky="ew", padx=8)
                ctk.CTkLabel(row, text=e.get("datetime", ""),
                             font=FONT_SMALL, text_color=TEXT_SEC
                             ).grid(row=0, column=2, padx=(0, 10))
        self.after(0, _do)

    # ═══════════════════════════════════════════════════════════════════════════
    #  DRIVE CONNECTION
    # ═══════════════════════════════════════════════════════════════════════════
    def _toggle_drive_connection(self):
        if self._drive_connected:
            self._disconnect_drive()
        else:
            self._connect_drive()

    def _connect_drive(self):
        self.log("Iniciando autenticação com o Google Drive...", "INFO")
        self.btn_connect.configure(state="disabled", text="Aguarde...")
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        ok = self.drive_svc.authenticate()
        if ok:
            self._drive_connected = True
            self.after(0, self._on_drive_connected)
            self.log("Google Drive conectado com sucesso!", "OK")
        else:
            self._drive_connected = False
            self.after(0, lambda: (
                self.conn_badge.configure(text="● Desconectado", text_color=TEXT_RED),
                self.btn_connect.configure(state="normal", text="Conectar Drive",
                                           fg_color=BG_INPUT, hover_color=BORDER,
                                           text_color=TEXT_SEC)
            ))
            self.log("Falha na autenticação com o Google Drive.", "ERROR")

    def _on_drive_connected(self):
        self.conn_badge.configure(text="● Conectado", text_color=TEXT_GRN)
        self.btn_connect.configure(
            state="normal", text="Desconectar Drive",
            fg_color=ACCENT_RED, hover_color=ACCENT_RED_HOV, text_color="white")

    def _disconnect_drive(self):
        if messagebox.askyesno("Desconectar Drive",
                               "Deseja desconectar o Google Drive?\n\n"
                               "O token de sessão será removido.\n"
                               "A sincronização será parada."):
            if self.scheduler.is_active():
                self._sync_cancel_evt.set()
                self.scheduler.stop()
                self._update_sync_button(active=False)

            self.drive_svc.disconnect()
            self._drive_connected = False
            self.conn_badge.configure(text="● Desconectado", text_color=TEXT_RED)
            self.btn_connect.configure(
                state="normal", text="Conectar Drive",
                fg_color=BG_INPUT, hover_color=BORDER, text_color=TEXT_SEC)
            self.log("Google Drive desconectado.", "WARN")

    def _check_drive_connection(self):
        if self.drive_svc.is_authenticated():
            self._drive_connected = True
            self._on_drive_connected()
            self.log("Sessão do Google Drive restaurada.", "OK")

    # ═══════════════════════════════════════════════════════════════════════════
    #  SYNC BUTTON  (master toggle: ▶ Sincronizar  ↔  ■ Parar Sincronização)
    #  NÃO controla o agendador — só liga/desliga o processo de sync.
    # ═══════════════════════════════════════════════════════════════════════════
    def _on_sync_button(self):
        if self.scheduler.is_active():
            # ── Parar ───────────────────────────────────────────────────────
            self._sync_cancel_evt.set()
            self.scheduler.stop()
            self._update_sync_button(active=False)
            self.log("Sincronização parada.", "WARN")
            self._save_config_silent()
        else:
            # ── Iniciar ─────────────────────────────────────────────────────
            if not self._drive_connected:
                messagebox.showwarning("Drive não conectado",
                                       "Conecte-se ao Google Drive antes de sincronizar.")
                return

            # Verifica se há alterações não salvas
            if self._has_unsaved_changes():
                resp = messagebox.askyesno(
                    "Configuração não salva",
                    "Você possui alterações não salvas.\n\n"
                    "Deseja salvar antes de sincronizar?")
                if resp:
                    if not self._save_config():   # save retorna False se campos inválidos
                        return
                else:
                    return   # usuário cancelou

            cfg = self._read_fields()
            if not cfg:
                return

            self._sync_cancel_evt.clear()
            self.scheduler.start()
            self._update_sync_button(active=True)
            modo = "agendado (" + self.var_interval.get() + ")" if self.var_auto.get() else "contínuo (5 min)"
            self.log(f"Sincronização iniciada — modo {modo}.", "OK")
            self._save_config_silent()

    def _update_sync_button(self, active: bool):
        if active:
            self.btn_sync.configure(
                text="■  Parar Sincronização",
                fg_color=ACCENT_RED, hover_color=ACCENT_RED_HOV)
        else:
            self.btn_sync.configure(
                text="▶  Sincronizar",
                fg_color=ACCENT, hover_color=ACCENT_HOV)

    # ═══════════════════════════════════════════════════════════════════════════
    #  SCHEDULER  — controla apenas a frequência, não o master on/off
    # ═══════════════════════════════════════════════════════════════════════════
    def _on_interval_toggle(self):
        use = self.var_auto.get()
        self.scheduler.set_use_interval(use)
        if use:
            self.log(f"Modo agendado ativado — intervalo: {self.var_interval.get()}.", "INFO")
        else:
            self.log("Modo contínuo ativado — verificação a cada 5 min.", "INFO")
        self._save_config_silent()

    def _on_interval_change(self, value: str):
        self.scheduler.set_interval(value)
        self.log(f"Intervalo alterado para: {value}", "INFO")
        self._save_config_silent()

    def _do_background_sync(self):
        """Chamado pelo scheduler automaticamente."""
        if not self._sync_lock.acquire(blocking=False):
            return
        try:
            if self._sync_cancel_evt.is_set():
                return
            cfg = self._read_fields_silent()
            if not cfg:
                self.log("Configuração incompleta — sync cancelado.", "WARN")
                return

            if not self.drive_svc.is_authenticated():
                self.log("Drive desconectado — tentando reconectar...", "WARN")
                if not self.drive_svc.authenticate():
                    self.log("Reconexão automática falhou.", "ERROR")
                    return
                self._drive_connected = True
                self.after(0, self._on_drive_connected)

            self.after(0, lambda: self.progress.start())
            data    = self.config_mgr.load()
            history = data.get("history", [])
            self.backup_mgr.run_sync(cfg, history, cancel_evt=self._sync_cancel_evt)
            self.config_mgr.save({**cfg, "history": history})
            self.refresh_history(history)
        finally:
            self._sync_lock.release()
            self.after(0, lambda: (self.progress.stop(), self.progress.set(0)))

    def _tick_scheduler_status(self):
        status = self.scheduler.get_status()

        def _do():
            self.lbl_next.configure(text=f"Próximo sync: {status['next_run']}")
            self.lbl_last.configure(text=f"Último sync:  {status['last_run']}")
            if status["active"]:
                self.lbl_sched_status.configure(
                    text=f"● Sync ativo — próximo: {status['next_run']}",
                    text_color=TEXT_GRN)
            else:
                self.lbl_sched_status.configure(text="● Sync parado", text_color=TEXT_SEC)

        self.after(0, _do)
        self.after(10_000, self._tick_scheduler_status)

    # ═══════════════════════════════════════════════════════════════════════════
    #  AUTOSTART
    # ═══════════════════════════════════════════════════════════════════════════
    def _toggle_autostart(self):
        if self.var_boot.get():
            ok = autostart.enable()
            if ok:
                cmd = autostart.get_registered_cmd()
                self.log("Inicialização automática ativada.", "OK")
                self.log(f"Registrado: {cmd}", "INFO")
                self.log("O app iniciará minimizado na bandeja ao ligar o Windows.", "INFO")
            else:
                self.log("Não foi possível ativar a inicialização automática.", "ERROR")
                self.var_boot.set(False)
        else:
            autostart.disable()
            self.log("Inicialização automática desativada.", "INFO")

    # ═══════════════════════════════════════════════════════════════════════════
    #  SYSTEM TRAY
    # ═══════════════════════════════════════════════════════════════════════════
    def _minimize_to_tray(self):
        self.withdraw()
        self._start_tray_icon()

    def _start_tray_icon(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            # Tenta carregar o .ico real; fallback para nuvem desenhada
            ico_path = _resolve_icon()
            if ico_path:
                try:
                    img = Image.open(ico_path)
                    # pystray precisa de RGBA
                    img = img.convert("RGBA")
                except Exception:
                    ico_path = None

            if not ico_path:
                img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([4, 20, 36, 52],  fill="#238636")
                draw.ellipse([20, 12, 52, 44], fill="#238636")
                draw.ellipse([28, 20, 60, 52], fill="#238636")
                draw.rectangle([8, 36, 56, 56], fill="#238636")

            menu = pystray.Menu(
                pystray.MenuItem("Abrir",      lambda: self.after(0, self._show_window), default=True),
                pystray.MenuItem("Sync agora", lambda: threading.Thread(
                    target=self._do_background_sync, daemon=True).start()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Encerrar",   lambda: self.after(0, self._quit_app)),
            )
            self._tray_icon = pystray.Icon(APP_NAME, img, APP_NAME, menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()

        except ImportError:
            self.iconify()

    def _show_window(self):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        """X sempre pergunta antes de fechar — sem minimizar para bandeja."""
        if messagebox.askyesno(
                "Encerrar",
                f"Deseja encerrar o {APP_NAME}?\n\n"
                "A sincronização automática será interrompida."):
            self._quit_app()

    def _quit_app(self):
        self.scheduler.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        self.destroy()

    # ═══════════════════════════════════════════════════════════════════════════
    #  CONFIG  (save / load / snapshot para detecção de mudanças)
    # ═══════════════════════════════════════════════════════════════════════════
    def _get_ui_snapshot(self) -> dict:
        """Captura os valores atuais dos campos para comparação."""
        return {
            "folder_pai": self.ent_folder_pai.get().strip(),
            "cliente":    self.ent_cliente.get().strip(),
            "backup_dir": self.ent_backup_dir.get().strip(),
            "extensoes":  self.ent_ext.get().strip(),
            "qtd_backups": str(self.var_qtd.get()),
        }

    def _has_unsaved_changes(self) -> bool:
        return self._get_ui_snapshot() != self._saved_snapshot

    def _save_config(self) -> bool:
        """Salva com validação. Retorna True se salvou, False se campos inválidos."""
        cfg = self._read_fields()
        if not cfg:
            return False
        self._persist_config(cfg)
        self._saved_snapshot = self._get_ui_snapshot()
        self.log("Configuração salva.", "OK")
        return True

    def _save_config_silent(self):
        cfg = self._read_fields_silent()
        if cfg:
            self._persist_config(cfg)

    def _persist_config(self, cfg: dict):
        history = self.config_mgr.load().get("history", [])
        cfg["auto_sync"]      = self.var_auto.get()
        cfg["sync_interval"]  = self.var_interval.get()
        cfg["sync_active"]    = self.scheduler.is_active()
        self.config_mgr.save({**cfg, "history": history})

    def _load_config(self):
        cfg = self.config_mgr.load()
        if not cfg:
            self._saved_snapshot = self._get_ui_snapshot()
            return

        def fill(entry, key, default=""):
            v = cfg.get(key, default)
            if v:
                entry.delete(0, "end")
                entry.insert(0, v)

        fill(self.ent_folder_pai, "folder_pai", DEFAULT_PASTA)
        fill(self.ent_cliente,    "cliente")
        fill(self.ent_backup_dir, "backup_dir")
        fill(self.ent_ext,        "extensoes")

        qtd = str(cfg.get("qtd_backups", 3))
        if qtd not in ["1", "2", "3", "5", "7", "10"]:
            qtd = "3"
        self.spin_qtd.set(qtd)
        self.var_qtd.set(int(qtd))

        interval = cfg.get("sync_interval", "1 hora")
        if interval in SyncScheduler.INTERVALS:
            self.var_interval.set(interval)
            self.cmb_interval.set(interval)
            self.scheduler.set_interval(interval)

        use_interval = cfg.get("auto_sync", False)
        self.var_auto.set(use_interval)
        self.scheduler.set_use_interval(use_interval)

        # Restaura o sync ativo se estava rodando antes
        if cfg.get("sync_active", False):
            self.scheduler.start()
            self._update_sync_button(active=True)
            self.log("Sincronização restaurada automaticamente.", "OK")

        self._saved_snapshot = self._get_ui_snapshot()
        self.refresh_history(cfg.get("history", []))
        self.log("Configuração carregada.", "OK")

    def _browse_folder(self):
        path = filedialog.askdirectory(title="Selecione a pasta de backup")
        if path:
            self.ent_backup_dir.delete(0, "end")
            self.ent_backup_dir.insert(0, path)

    def _read_fields(self) -> dict | None:
        folder_pai = self.ent_folder_pai.get().strip()
        cliente    = self.ent_cliente.get().strip()
        backup_dir = self.ent_backup_dir.get().strip()
        extensoes  = self.ent_ext.get().strip() or ".sql"
        qtd        = self.var_qtd.get()

        errors = []
        if not folder_pai:  errors.append("Pasta Pai no Drive")
        if not cliente:     errors.append("Cliente")
        if not backup_dir:  errors.append("Pasta de Backup Local")

        if errors:
            messagebox.showerror("Campos obrigatórios",
                                 "Preencha os campos:\n• " + "\n• ".join(errors))
            return None

        if not os.path.isdir(backup_dir):
            messagebox.showerror("Pasta inválida",
                                 f"A pasta de backup não existe:\n{backup_dir}")
            return None

        return dict(folder_pai=folder_pai, cliente=cliente,
                    backup_dir=backup_dir, extensoes=extensoes, qtd_backups=qtd)

    def _read_fields_silent(self) -> dict | None:
        cfg = self.config_mgr.load()
        if not cfg:
            return None
        fp = cfg.get("folder_pai", "").strip()
        cl = cfg.get("cliente",    "").strip()
        bd = cfg.get("backup_dir", "").strip()
        ex = cfg.get("extensoes",  ".sql").strip()
        qt = int(cfg.get("qtd_backups", 3))
        if not fp or not cl or not bd or not os.path.isdir(bd):
            return None
        return dict(folder_pai=fp, cliente=cl, backup_dir=bd,
                    extensoes=ex, qtd_backups=qt)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = BackupApp()

    if "--minimized" in sys.argv:
        app.withdraw()
        app._start_tray_icon()

    app.mainloop()
