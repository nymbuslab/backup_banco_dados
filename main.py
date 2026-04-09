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
from email_service   import EmailService
from alert_service   import AlertService
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
ACCENT_BLUE    = "#1F6FEB"
ACCENT_BLUE_HOV= "#388BFD"
TEXT_PRI       = "#E6EDF3"
TEXT_SEC       = "#8B949E"
TEXT_GRN       = "#3FB950"
TEXT_RED       = "#F85149"
TEXT_YEL       = "#D29922"
TEXT_BLUE      = "#58A6FF"
FONT_MONO      = ("Consolas", 11)
FONT_HEAD      = ("Segoe UI", 20, "bold")
FONT_SUB       = ("Segoe UI", 12, "bold")
FONT_BODY      = ("Segoe UI", 11)
FONT_SMALL     = ("Segoe UI", 10)
FONT_TINY      = ("Segoe UI", 9)


def _resolve_icon() -> str | None:
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
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Profile Form (modal window)
# ─────────────────────────────────────────────────────────────────────────────
class ProfileForm(ctk.CTkToplevel):
    """Janela modal para criar/editar um perfil."""

    def __init__(self, parent, profile: dict, on_save):
        super().__init__(parent)
        self.profile  = dict(profile)   # cópia
        self.on_save  = on_save
        self._result  = None

        self.title("Editar Perfil" if profile.get("nome") else "Novo Perfil")
        self.geometry("520x720")
        self.minsize(500, 620)
        self.resizable(True, True)
        self.configure(fg_color=BG_DARK)
        self.grab_set()   # modal

        ico = _resolve_icon()
        if ico:
            try:
                self.iconbitmap(ico)
            except (tk.TclError, OSError):
                pass

        self._build()
        self._load()

    def _build(self):
        # Title
        ctk.CTkLabel(self, text="Configuração do Perfil",
                     font=FONT_SUB, text_color=TEXT_PRI
                     ).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=24)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=14, side="bottom")
        btn_row.columnconfigure((0, 1), weight=1)

        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=24, side="bottom")

        ctk.CTkButton(btn_row, text="Cancelar",
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SEC, height=38,
                      command=self.destroy
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(btn_row, text="💾  Salvar Perfil",
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      text_color="white", height=38,
                      command=self._save
                      ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        f = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        f.pack(fill="both", expand=True, padx=24, pady=12)
        f.columnconfigure(0, weight=1)

        def lbl(text, row):
            ctk.CTkLabel(f, text=text, font=FONT_SMALL,
                         text_color=TEXT_SEC).grid(row=row, column=0,
                                                   sticky="w", pady=(10, 2))
        def ent(row, ph):
            e = ctk.CTkEntry(f, placeholder_text=ph, fg_color=BG_INPUT,
                             border_color=BORDER, text_color=TEXT_PRI,
                             height=36, font=FONT_BODY)
            e.grid(row=row, column=0, sticky="ew")
            return e

        lbl("Nome do perfil", 0)
        self.ent_nome = ent(1, "ex: Banco de Dados TESTE")

        # Modo
        lbl("Modo de backup", 2)
        self.var_modo = tk.StringVar(value="rotacao")
        modo_row = ctk.CTkFrame(f, fg_color="transparent")
        modo_row.grid(row=3, column=0, sticky="ew")
        self.seg_modo = ctk.CTkSegmentedButton(
            modo_row,
            values=["Rotação", "Espelho"],
            variable=tk.StringVar(value="Rotação"),
            fg_color=BG_INPUT, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOV,
            unselected_color=BG_INPUT, unselected_hover_color=BORDER,
            text_color=TEXT_PRI, font=FONT_BODY,
            command=self._on_modo_change)
        self.seg_modo.pack(side="left")

        self.lbl_modo_hint = ctk.CTkLabel(modo_row,
            text="Mantém os N mais recentes",
            font=FONT_TINY, text_color=TEXT_SEC)
        self.lbl_modo_hint.pack(side="left", padx=10)

        lbl("Pasta Pai no Drive", 4)
        self.ent_folder_pai = ent(5, f"ex: {DEFAULT_PASTA}")

        lbl("Cliente (pasta filho no Drive)", 6)
        self.ent_cliente = ent(7, "ex: FISCAL")

        lbl("Pasta de Backup Local", 8)
        br = ctk.CTkFrame(f, fg_color="transparent")
        br.grid(row=9, column=0, sticky="ew")
        br.columnconfigure(0, weight=1)
        self.ent_backup_dir = ctk.CTkEntry(br, placeholder_text="Selecione a pasta...",
                                           fg_color=BG_INPUT, border_color=BORDER,
                                           text_color=TEXT_PRI, height=36, font=FONT_BODY)
        self.ent_backup_dir.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(br, text="📂", width=36, height=36,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      command=self._browse).grid(row=0, column=1)

        lbl("Extensão dos arquivos", 10)
        self.ent_ext = ctk.CTkEntry(f, fg_color=BG_INPUT, border_color=BORDER,
                                    text_color=TEXT_PRI, height=36, font=FONT_BODY,
                                    placeholder_text=".sql  (vazio = todos os arquivos)")
        self.ent_ext.grid(row=11, column=0, sticky="ew")

        # Qtd backups — só para rotação
        self.frame_qtd = ctk.CTkFrame(f, fg_color="transparent")
        self.frame_qtd.grid(row=12, column=0, sticky="ew")
        self.frame_qtd.columnconfigure(0, weight=1)
        ctk.CTkLabel(self.frame_qtd, text="Backups armazenados (máx.)",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=0, column=0, sticky="w", pady=(10, 2))
        self.var_qtd = tk.IntVar(value=3)
        self.spin_qtd = ctk.CTkSegmentedButton(
            self.frame_qtd, values=["1", "2", "3", "5", "7", "10"],
            variable=tk.StringVar(value="3"),
            fg_color=BG_INPUT, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOV,
            unselected_color=BG_INPUT, unselected_hover_color=BORDER,
            text_color=TEXT_PRI, font=FONT_SMALL,
            command=lambda v: self.var_qtd.set(int(v)))
        self.spin_qtd.grid(row=1, column=0, sticky="w")

        # Incluir subpastas — só para espelho
        self.frame_rec = ctk.CTkFrame(f, fg_color="transparent")
        self.frame_rec.grid(row=13, column=0, sticky="ew")
        self.frame_rec.columnconfigure(1, weight=1)
        ctk.CTkLabel(self.frame_rec, text="Incluir subpastas",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=0, column=0, sticky="w", pady=(10, 2))
        self.var_recursivo = tk.BooleanVar(value=False)
        ctk.CTkSwitch(self.frame_rec, text="", variable=self.var_recursivo,
                      onvalue=True, offvalue=False, width=44,
                      progress_color=ACCENT
                      ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(self.frame_rec,
                     text="Replica estrutura de pastas no Drive",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # Alertas por e-mail
        ctk.CTkFrame(f, fg_color=BORDER, height=1).grid(
            row=14, column=0, sticky="ew", pady=(12, 0))
        email_row = ctk.CTkFrame(f, fg_color="transparent")
        email_row.grid(row=15, column=0, sticky="ew", pady=(8, 0))
        email_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(email_row, text="Alertas por e-mail",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=0, column=0, sticky="w")
        self.var_email_alerta = tk.BooleanVar(value=False)
        ctk.CTkSwitch(email_row, text="", variable=self.var_email_alerta,
                      onvalue=True, offvalue=False, width=44,
                      progress_color=ACCENT
                      ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(f,
                     text="Notifica atrasos e erros deste perfil (configure o servidor em ✉ E-mail).",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=16, column=0, sticky="w", pady=(0, 4))

    def _load(self):
        p = self.profile
        if p.get("nome"):       self.ent_nome.insert(0, p["nome"])
        if p.get("folder_pai"): self.ent_folder_pai.insert(0, p["folder_pai"])
        else:                   self.ent_folder_pai.insert(0, DEFAULT_PASTA)
        if p.get("cliente"):    self.ent_cliente.insert(0, p["cliente"])
        if p.get("backup_dir"): self.ent_backup_dir.insert(0, p["backup_dir"])
        if p.get("extensoes"):  self.ent_ext.insert(0, p["extensoes"])

        modo = p.get("modo", "rotacao")
        label = "Rotação" if modo == "rotacao" else "Espelho"
        self.seg_modo.set(label)
        self._on_modo_change(label)

        qtd = str(p.get("qtd_backups", 3))
        if qtd in ["1","2","3","5","7","10"]:
            self.spin_qtd.set(qtd)
            self.var_qtd.set(int(qtd))

        self.var_recursivo.set(p.get("recursivo", False))
        self.var_email_alerta.set(p.get("email_alerta", False))

    def _on_modo_change(self, value: str):
        is_rotacao = (value == "Rotação")
        self.var_modo.set("rotacao" if is_rotacao else "espelho")
        self.lbl_modo_hint.configure(
            text="Mantém os N mais recentes" if is_rotacao else "Envia tudo, nunca remove do Drive"
        )
        # Mostra/esconde campos conforme o modo
        if is_rotacao:
            self.frame_qtd.grid()
            self.frame_rec.grid_remove()
        else:
            self.frame_qtd.grid_remove()
            self.frame_rec.grid()

    def _browse(self):
        path = filedialog.askdirectory(title="Selecione a pasta de backup")
        if path:
            self.ent_backup_dir.delete(0, "end")
            self.ent_backup_dir.insert(0, path)

    def _save(self):
        nome       = self.ent_nome.get().strip()
        folder_pai = self.ent_folder_pai.get().strip()
        cliente    = self.ent_cliente.get().strip()
        backup_dir = self.ent_backup_dir.get().strip()
        extensoes  = self.ent_ext.get().strip()
        modo       = self.var_modo.get()
        qtd        = self.var_qtd.get()

        errors = []
        if not nome:       errors.append("Nome do perfil")
        if not folder_pai: errors.append("Pasta Pai no Drive")
        if not cliente:    errors.append("Cliente")
        if not backup_dir: errors.append("Pasta de Backup Local")

        if errors:
            messagebox.showerror("Campos obrigatórios",
                                 "Preencha:\n• " + "\n• ".join(errors),
                                 parent=self)
            return

        if not os.path.isdir(backup_dir):
            messagebox.showerror("Pasta inválida",
                                 f"A pasta não existe:\n{backup_dir}", parent=self)
            return

        self.profile.update({
            "nome":         nome,
            "modo":         modo,
            "folder_pai":   folder_pai,
            "cliente":      cliente,
            "backup_dir":   backup_dir,
            "extensoes":    extensoes,
            "qtd_backups":  qtd,
            "recursivo":    self.var_recursivo.get(),
            "email_alerta": self.var_email_alerta.get(),
        })
        self.on_save(self.profile)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Email Config Form (modal)
# ─────────────────────────────────────────────────────────────────────────────
class EmailConfigForm(ctk.CTkToplevel):
    """Modal para configurar SMTP de alertas por e-mail."""

    def __init__(self, parent, config: dict, admin_config: dict, on_save):
        super().__init__(parent)
        self.config = dict(config)
        self.admin_config = dict(admin_config)
        self.on_save = on_save

        self.title("Configuração de E-mail")
        self.geometry("520x680")
        self.minsize(500, 620)
        self.resizable(True, True)
        self.configure(fg_color=BG_DARK)
        self.grab_set()

        ico = _resolve_icon()
        if ico:
            try:
                self.iconbitmap(ico)
            except (tk.TclError, OSError):
                pass

        self._build()
        self._load()

    def _build(self):
        ctk.CTkLabel(self, text="Configuração de E-mail",
                     font=FONT_SUB, text_color=TEXT_PRI
                     ).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(self,
                     text="Configure o servidor SMTP para envio de alertas automáticos.",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).pack(anchor="w", padx=24, pady=(0, 4))
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=24)

        # Botões no fundo
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=14, side="bottom")
        btn_row.columnconfigure((0, 1, 2), weight=1)
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=24, side="bottom")

        ctk.CTkButton(btn_row, text="Cancelar",
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SEC, height=38,
                      command=self.destroy
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(btn_row, text="✉  Testar",
                      fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOV,
                      text_color="white", height=38,
                      command=self._test
                      ).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(btn_row, text="💾  Salvar",
                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                      text_color="white", height=38,
                      command=self._save
                      ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        # Formulário
        f = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        f.pack(fill="both", expand=True, padx=24, pady=12)
        f.columnconfigure(0, weight=1)

        def lbl(text, row):
            ctk.CTkLabel(f, text=text, font=FONT_SMALL,
                         text_color=TEXT_SEC).grid(row=row, column=0,
                                                   sticky="w", pady=(10, 2))
        def ent(row, ph, show=""):
            e = ctk.CTkEntry(f, placeholder_text=ph, fg_color=BG_INPUT,
                             border_color=BORDER, text_color=TEXT_PRI,
                             height=36, font=FONT_BODY, show=show)
            e.grid(row=row, column=0, sticky="ew")
            return e

        lbl("Servidor SMTP", 0)
        host_row = ctk.CTkFrame(f, fg_color="transparent")
        host_row.grid(row=1, column=0, sticky="ew")
        host_row.columnconfigure(0, weight=1)
        self.ent_host = ctk.CTkEntry(host_row, placeholder_text="ex: smtp.gmail.com",
                                     fg_color=BG_INPUT, border_color=BORDER,
                                     text_color=TEXT_PRI, height=36, font=FONT_BODY)
        self.ent_host.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.ent_port = ctk.CTkEntry(host_row, placeholder_text="587",
                                     fg_color=BG_INPUT, border_color=BORDER,
                                     text_color=TEXT_PRI, height=36, font=FONT_BODY,
                                     width=70)
        self.ent_port.grid(row=0, column=1)

        lbl("Usuário (e-mail remetente)", 2)
        self.ent_user = ent(3, "ex: seuemail@gmail.com")

        lbl("Senha / App Password", 4)
        self.ent_pwd = ent(5, "••••••••••••", show="•")

        lbl("Destinatário (e-mail para alertas)", 6)
        self.ent_to = ent(7, "ex: admin@empresa.com")

        # TLS toggle
        tls_row = ctk.CTkFrame(f, fg_color="transparent")
        tls_row.grid(row=8, column=0, sticky="ew", pady=(14, 0))
        tls_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(tls_row, text="Usar TLS (STARTTLS — porta 587)",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=0, column=0, sticky="w")
        self.var_tls = tk.BooleanVar(value=True)
        ctk.CTkSwitch(tls_row, text="", variable=self.var_tls,
                      onvalue=True, offvalue=False, width=44,
                      progress_color=ACCENT
                      ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(f,
                     text="Desative para SSL direto (porta 465).",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=9, column=0, sticky="w", pady=(0, 4))

        ctk.CTkFrame(f, fg_color=BORDER, height=1).grid(
            row=10, column=0, sticky="ew", pady=(14, 0))

        lbl("Identificação da instalação", 11)
        self.ent_installation = ent(12, "ex: TESTE GR7 - MATRIZ")
        ctk.CTkLabel(f,
                     text="Usado nos e-mails de alertas administrativos para identificar o cliente/máquina.",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=13, column=0, sticky="w", pady=(0, 4))

        admin_row = ctk.CTkFrame(f, fg_color="transparent")
        admin_row.grid(row=14, column=0, sticky="ew", pady=(10, 0))
        admin_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(admin_row, text="Alertas administrativos",
                     font=FONT_SMALL, text_color=TEXT_SEC
                     ).grid(row=0, column=0, sticky="w")
        self.var_admin_alerts = tk.BooleanVar(value=False)
        ctk.CTkSwitch(admin_row, text="", variable=self.var_admin_alerts,
                      onvalue=True, offvalue=False, width=44,
                      progress_color=ACCENT
                      ).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(f,
                     text="Notifica problemas globais da instalação, como reconexão obrigatória do Google Drive.",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=15, column=0, sticky="w", pady=(0, 4))
        self.lbl_test_status = ctk.CTkLabel(f, text="",
                                            font=FONT_TINY, text_color=TEXT_SEC)
        self.lbl_test_status.grid(row=16, column=0, sticky="w", pady=(10, 0))

    def _load(self):
        c = self.config
        if c.get("smtp_host"): self.ent_host.insert(0, c["smtp_host"])
        port = c.get("smtp_port", 587)
        self.ent_port.insert(0, str(port))
        if c.get("smtp_user"):     self.ent_user.insert(0, c["smtp_user"])
        if c.get("smtp_password"): self.ent_pwd.insert(0, c["smtp_password"])
        if c.get("to_addr"):       self.ent_to.insert(0, c["to_addr"])
        self.var_tls.set(c.get("use_tls", True))
        if self.admin_config.get("installation_label"):
            self.ent_installation.insert(0, self.admin_config["installation_label"])
        self.var_admin_alerts.set(self.admin_config.get("admin_alerts_enabled", False))

    def _collect(self) -> tuple[dict, dict]:
        try:
            port = int(self.ent_port.get().strip() or "587")
        except ValueError:
            port = 587
        email_cfg = {
            "smtp_host":     self.ent_host.get().strip(),
            "smtp_port":     port,
            "smtp_user":     self.ent_user.get().strip(),
            "smtp_password": self.ent_pwd.get(),
            "to_addr":       self.ent_to.get().strip(),
            "use_tls":       self.var_tls.get(),
        }
        admin_cfg = {
            "installation_label": self.ent_installation.get().strip(),
            "admin_alerts_enabled": self.var_admin_alerts.get(),
        }
        return email_cfg, admin_cfg

    def _test(self):
        cfg, _ = self._collect()
        if not cfg["smtp_host"] or not cfg["smtp_user"] or not cfg["smtp_password"] or not cfg["to_addr"]:
            messagebox.showwarning("Campos incompletos",
                                   "Preencha todos os campos antes de testar.", parent=self)
            return
        import threading
        self.lbl_test_status.configure(text="Enviando e-mail de teste...", text_color=TEXT_SEC)

        def _do():
            svc = EmailService(cfg, lambda msg, lv: None)
            ok = svc.send(
                "✔ GR7 Backup — Teste de e-mail",
                "Este é um e-mail de teste enviado pelo GR7 Backup Manager.\n\n"
                "Se você recebeu esta mensagem, a configuração está correta.\n\n"
                "---\nGR7 Backup Manager"
            )
            def _finish():
                self.lbl_test_status.configure(
                    text="E-mail de teste enviado com sucesso!" if ok
                    else "Falha no envio. Verifique as configurações e tente novamente.",
                    text_color=TEXT_GRN if ok else TEXT_RED,
                )
            self.after(0, _finish)
        threading.Thread(target=_do, daemon=True).start()

    def _save(self):
        cfg, admin_cfg = self._collect()
        self.on_save(cfg, admin_cfg)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────────────────────────────────────────
class BackupApp(ctk.CTk):
    def __init__(self, start_minimized: bool = False):
        super().__init__()
        self._app_alive = True
        if start_minimized:
            self.withdraw()
        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(1000, 620)
        self.configure(fg_color=BG_DARK)

        ico = _resolve_icon()
        if ico:
            try:
                self.iconbitmap(ico)
            except (tk.TclError, OSError):
                pass

        self.config_mgr = ConfigManager()
        self.drive_svc  = DriveService(self.log)
        initial_cfg = self.config_mgr.load()
        email_cfg = initial_cfg.get("email_config", {})
        self.email_svc  = EmailService(email_cfg, self.log)
        self.alert_svc  = AlertService(self.config_mgr, self.email_svc, self.log)
        self.backup_mgr = BackupManager(self.drive_svc, self.log, self.refresh_history,
                                        email_svc=self.email_svc)
        self._sync_cancel_evt = threading.Event()
        self.scheduler  = SyncScheduler(
            self._do_background_sync,
            self.log,
            cancel_evt=self._sync_cancel_evt,
            error_fn=self._notify_scheduler_error,
        )

        self._app_alive       = True   # False após destroy() — protege self.after() de threads em background
        self._sync_lock       = threading.Lock()
        self._running_profile_lock = threading.Lock()
        self._card_refs: dict = {}   # pid → {card, lbl_detail, base_detail}
        self._tray_icon       = None
        self._drive_connected = False
        self._sched_after_id  = None
        self._log_progress_active = False
        self._log_progress_start  = None
        self._running_profile_id  = None
        self._modal_count         = 0
        self.conn_badge = None
        self.btn_connect = None
        self.profiles_box = None
        self.btn_sync = None
        self.var_auto = None
        self.sw_auto = None
        self.var_interval = None
        self.cmb_interval = None
        self.lbl_next = None
        self.lbl_last = None
        self.var_boot = None
        self.sw_boot = None
        self.lbl_hist_count = None
        self.hist_box = None
        self.log_text = None
        self.lbl_status = None
        self.lbl_sched_status = None
        self.lbl_admin_alerts = None
        self.progress = None

        self._build_ui()
        self._check_drive_connection()
        self._load_all()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick_scheduler_status()

    # ═══════════════════════════════════════════════════════════════════════════
    #  UI BUILD
    # ═══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16)
        body.columnconfigure(0, weight=2, minsize=380)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)
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

        ctk.CTkButton(inner, text="✉ E-mail", width=90, height=28,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_color=BORDER, border_width=1,
                      font=FONT_SMALL, text_color=TEXT_SEC,
                      command=self._open_email_config).pack(side="right", padx=(6, 0))

        self.conn_badge = ctk.CTkLabel(inner, text="● Desconectado",
                                       font=FONT_SMALL, text_color=TEXT_RED)
        self.conn_badge.pack(side="right", padx=10)

        self.btn_connect = ctk.CTkButton(
            inner, text="Conectar Drive", width=155, height=32,
            fg_color=BG_INPUT, hover_color=BORDER,
            border_color=BORDER, border_width=1,
            font=FONT_SMALL, text_color=TEXT_SEC,
            command=self._toggle_drive_connection)
        self.btn_connect.pack(side="right")
        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x")

    # ── Left panel ─────────────────────────────────────────────────────────────
    def _build_left_panel(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=12)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        # ── Profiles header
        prof_hdr = ctk.CTkFrame(card, fg_color="transparent")
        prof_hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 6))
        ctk.CTkLabel(prof_hdr, text="Perfis de Backup",
                     font=FONT_SUB, text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(prof_hdr, text="+ Novo Perfil", width=110, height=28,
                      fg_color=ACCENT_BLUE, hover_color=ACCENT_BLUE_HOV,
                      text_color="white", font=FONT_SMALL,
                      command=self._new_profile).pack(side="right")

        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=0, column=0, sticky="ew", padx=20, pady=(42, 0))

        # ── Profiles list (scrollable)
        self.profiles_box = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                                    scrollbar_button_color=BORDER,
                                                    scrollbar_button_hover_color=TEXT_SEC)
        self.profiles_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.profiles_box.columnconfigure(0, weight=1)

        # ── Separator + global settings
        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=2, column=0, sticky="ew", padx=20, pady=(4, 0))

        settings_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                                  height=200,
                                                  scrollbar_button_color=BORDER,
                                                  scrollbar_button_hover_color=TEXT_SEC)
        settings_scroll.grid(row=3, column=0, sticky="ew", padx=4)
        settings_scroll.columnconfigure(0, weight=1)
        self._build_global_settings(settings_scroll)

        # ── Bottom buttons
        ctk.CTkFrame(card, fg_color=BORDER, height=1).grid(
            row=4, column=0, sticky="ew", padx=20)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=20, pady=12)
        btn_row.columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_row, text="💾  Salvar Config",
                      fg_color=BG_INPUT, hover_color=BORDER,
                      border_width=1, border_color=BORDER,
                      text_color=TEXT_SEC, font=FONT_BODY, height=40,
                      command=self._save_globals
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_sync = ctk.CTkButton(btn_row, text="▶  Sincronizar",
                                      fg_color=ACCENT, hover_color=ACCENT_HOV,
                                      text_color="white",
                                      font=("Segoe UI", 11, "bold"),
                                      height=40, command=self._on_sync_button)
        self.btn_sync.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_global_settings(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", padx=16, pady=4)
        f.columnconfigure(0, weight=1)

        ctk.CTkLabel(f, text="Sincronização Automática",
                     font=FONT_SUB, text_color=TEXT_PRI
                     ).grid(row=0, column=0, sticky="w", pady=(8, 6))

        auto_row = ctk.CTkFrame(f, fg_color="transparent")
        auto_row.grid(row=1, column=0, sticky="ew")
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
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=2, column=0, sticky="w", pady=(2, 4))

        ctk.CTkLabel(f, text="Intervalo", font=FONT_SMALL,
                     text_color=TEXT_SEC).grid(row=3, column=0, sticky="w", pady=(4, 2))
        self.var_interval = tk.StringVar(value="1 hora")
        self.cmb_interval = ctk.CTkOptionMenu(
            f, values=list(SyncScheduler.INTERVALS.keys()),
            variable=self.var_interval, fg_color=BG_INPUT,
            button_color=BORDER, button_hover_color=TEXT_SEC,
            text_color=TEXT_PRI, dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BORDER, dropdown_text_color=TEXT_PRI,
            font=FONT_BODY, height=34, command=self._on_interval_change)
        self.cmb_interval.grid(row=4, column=0, sticky="ew")

        self.lbl_next = ctk.CTkLabel(f, text="Próximo sync: —",
                                      font=FONT_TINY, text_color=TEXT_SEC)
        self.lbl_next.grid(row=5, column=0, sticky="w", pady=(4, 0))
        self.lbl_last = ctk.CTkLabel(f, text="Último sync:  —",
                                      font=FONT_TINY, text_color=TEXT_SEC)
        self.lbl_last.grid(row=6, column=0, sticky="w", pady=(2, 0))

        ctk.CTkFrame(f, fg_color=BORDER, height=1).grid(
            row=7, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(f, text="Sistema", font=FONT_SUB,
                     text_color=TEXT_PRI).grid(row=8, column=0, sticky="w", pady=(8, 6))

        boot_row = ctk.CTkFrame(f, fg_color="transparent")
        boot_row.grid(row=9, column=0, sticky="ew")
        boot_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(boot_row, text="Iniciar com o Windows",
                     font=FONT_BODY, text_color=TEXT_PRI).grid(row=0, column=0, sticky="w")
        self.var_boot = tk.BooleanVar(value=autostart.is_enabled())
        self.sw_boot  = ctk.CTkSwitch(boot_row, text="", variable=self.var_boot,
                                       onvalue=True, offvalue=False,
                                       progress_color=ACCENT,
                                       command=self._toggle_autostart)
        self.sw_boot.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(f, text="Inicia minimizado na bandeja.",
                     font=FONT_TINY, text_color=TEXT_SEC
                     ).grid(row=10, column=0, sticky="w", pady=(2, 8))

        self.lbl_admin_alerts = ctk.CTkLabel(
            f,
            text="",
            font=FONT_TINY,
            text_color=TEXT_SEC,
            justify="left",
            wraplength=320,
        )
        self.lbl_admin_alerts.grid(row=11, column=0, sticky="w", pady=(4, 2))

    # ── Right panel (log + history) ────────────────────────────────────────────
    def _build_right_panel(self, parent):
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
                                       corner_radius=6, wrap="word", state="disabled")
        self.log_text.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 14))
        log_box = getattr(self.log_text, "_textbox")
        log_box.tag_configure("INFO",  foreground=TEXT_SEC)
        log_box.tag_configure("OK",    foreground=TEXT_GRN)
        log_box.tag_configure("WARN",  foreground=TEXT_YEL)
        log_box.tag_configure("ERROR", foreground=TEXT_RED)
        log_box.tag_configure("PROGRESS", foreground=TEXT_BLUE)

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
    #  PROFILES LIST
    # ═══════════════════════════════════════════════════════════════════════════
    def _render_profiles(self):
        self._card_refs.clear()
        for w in self.profiles_box.winfo_children():
            w.destroy()

        data     = self.config_mgr.load()
        profiles = data.get("profiles", [])
        history  = data.get("history", [])

        last_ok_by_name = {}
        for e in history:
            if e.get("status") != "OK":
                continue
            perfil = e.get("perfil")
            dt = e.get("datetime")
            if not perfil or not dt:
                continue
            last_ok_by_name[perfil] = dt

        if not profiles:
            ctk.CTkLabel(self.profiles_box,
                         text="Nenhum perfil criado.\nClique em '+ Novo Perfil' para começar.",
                         font=FONT_SMALL, text_color=TEXT_SEC,
                         justify="center").pack(pady=20)
            return

        for p in profiles:
            self._render_profile_card(p, last_ok_by_name)

    def _render_profile_card(self, p: dict, last_ok_by_name: dict):
        is_rotacao = p.get("modo", "rotacao") == "rotacao"
        ativo      = p.get("ativo", True)
        running    = (p.get("id") == self._get_running_profile_id())
        pid        = p["id"]

        card = ctk.CTkFrame(self.profiles_box, fg_color=BG_CARD, corner_radius=8,
                            border_width=1,
                            border_color=ACCENT_BLUE if running else (ACCENT if ativo else BORDER))
        card.pack(fill="x", pady=3, padx=4)
        card.columnconfigure(1, weight=1)

        # Ícone modo
        modo_color = ACCENT if is_rotacao else ACCENT_BLUE
        modo_text  = "⟳" if is_rotacao else "⬆"
        ctk.CTkLabel(card, text=modo_text, font=("Segoe UI", 16),
                     text_color=modo_color, width=32
                     ).grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=8)

        # Nome
        ctk.CTkLabel(card, text=p.get("nome", "Sem nome"),
                     font=FONT_BODY, text_color=TEXT_PRI if ativo else TEXT_SEC,
                     anchor="w").grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 0))

        # Linha de detalhe — guardamos referência para atualizar sem recriar
        modo_label = "Rotação" if is_rotacao else "Espelho"
        base_detail = f"{modo_label}  •  {p.get('folder_pai','')}/{p.get('cliente','')}"
        if is_rotacao:
            base_detail += f"  •  {p.get('qtd_backups', 3)} backups"
        last_ok = last_ok_by_name.get(p.get("nome"))
        if last_ok:
            base_detail += f"  •  Último OK: {last_ok}"

        detail_text = base_detail + ("  •  ⟳ Sincronizando…" if running else "")
        lbl_detail = ctk.CTkLabel(card, text=detail_text,
                                   font=FONT_TINY, text_color=TEXT_SEC, anchor="w")
        lbl_detail.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 8))

        # Registra referências mutáveis do card indexadas pelo profile id
        self._card_refs[pid] = {
            "card":       card,
            "lbl_detail": lbl_detail,
            "base_detail": base_detail,
            "ativo":      ativo,
        }

        # Botões
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.grid(row=0, column=2, rowspan=2, padx=(0, 8))

        var_ativo = tk.BooleanVar(value=ativo)
        ctk.CTkSwitch(btn_frame, text="", variable=var_ativo,
                      onvalue=True, offvalue=False,
                      width=44, progress_color=ACCENT,
                      command=lambda _pid=pid, v=var_ativo: self._toggle_profile(_pid, v.get())
                      ).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="▶", width=30, height=28,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      text_color=TEXT_SEC, font=FONT_BODY,
                      command=lambda _pid=pid: self._sync_profile_now(_pid)
                      ).pack(side="left", padx=2)

        ctk.CTkButton(btn_frame, text="✎", width=30, height=28,
                      fg_color=BG_INPUT, hover_color=BORDER,
                      text_color=TEXT_SEC, font=FONT_BODY,
                      command=lambda _pid=pid: self._edit_profile(_pid)
                      ).pack(side="left", padx=2)

        ctk.CTkButton(btn_frame, text="🗑", width=30, height=28,
                      fg_color=BG_INPUT, hover_color=ACCENT_RED,
                      text_color=TEXT_SEC, font=FONT_BODY,
                      command=lambda _pid=pid, pn=p.get("nome",""): self._delete_profile(_pid, pn)
                      ).pack(side="left", padx=2)

    def _update_running_card(self, pid: str | None, prev_pid: str | None = None):
        """
        Atualiza visualmente apenas o card que mudou de estado (rodando / parado).
        Não destrói nem recria nenhum widget — só altera texto e borda.
        """
        def _apply(profile_id, is_running):
            refs = self._card_refs.get(profile_id)
            if not refs:
                return
            card       = refs["card"]
            lbl_detail = refs["lbl_detail"]
            base       = refs["base_detail"]
            ativo      = refs["ativo"]
            try:
                border = ACCENT_BLUE if is_running else (ACCENT if ativo else BORDER)
                card.configure(border_color=border)
                suffix = "  •  ⟳ Sincronizando…" if is_running else ""
                lbl_detail.configure(text=base + suffix)
            except tk.TclError:
                pass   # widget pode ter sido destruído por _render_profiles

        if prev_pid and prev_pid != pid:
            _apply(prev_pid, False)
        if pid:
            _apply(pid, True)

    # ═══════════════════════════════════════════════════════════════════════════
    #  PROFILE ACTIONS
    # ═══════════════════════════════════════════════════════════════════════════
    def _new_profile(self):
        p = self.config_mgr.new_profile()
        self._open_profile_form(p)

    def _edit_profile(self, profile_id: str):
        profiles = self.config_mgr.get_profiles()
        p = next((x for x in profiles if x["id"] == profile_id), None)
        if p:
            self._open_profile_form(p)

    def _open_profile_form(self, profile: dict):
        form = ProfileForm(self, profile, self._on_profile_saved)
        self._modal_count += 1
        def _on_destroy(evt):
            if evt.widget is form:
                self._modal_count = max(self._modal_count - 1, 0)
        form.bind("<Destroy>", _on_destroy)

    def _on_profile_saved(self, profile: dict):
        self.config_mgr.save_profile(profile)
        self._render_profiles()
        self.log(f"Perfil salvo: {profile['nome']}", "OK")

    def _toggle_profile(self, profile_id: str, ativo: bool):
        profiles = self.config_mgr.get_profiles()
        for p in profiles:
            if p["id"] == profile_id:
                p["ativo"] = ativo
                self.config_mgr.save_profile(p)
                status = "ativado" if ativo else "pausado"
                self.log(f"Perfil '{p['nome']}' {status}.", "INFO")
                break
        self._render_profiles()

    def _sync_profile_now(self, profile_id: str):
        if not self._drive_connected:
            messagebox.showwarning("Drive não conectado",
                                   "Conecte-se ao Google Drive antes de sincronizar.")
            return
        threading.Thread(target=lambda: self._do_profile_sync(profile_id), daemon=True).start()

    def _do_profile_sync(self, profile_id: str):
        if not self._sync_lock.acquire(blocking=False):
            return
        try:
            self._sync_cancel_evt.clear()
            data = self.config_mgr.load()
            profiles = data.get("profiles", [])
            history  = data.get("history", [])
            profile = next((p for p in profiles if p.get("id") == profile_id), None)
            if not profile:
                self.log("Perfil não encontrado.", "ERROR")
                return

            if not self.drive_svc.is_authenticated():
                self.log("Drive desconectado — tentando reconectar...", "WARN")
                if not self.drive_svc.authenticate():
                    self.log("Reconexão automática falhou.", "ERROR")
                    drained = self._drain_drive_alerts()
                    if drained == 0:
                        self._notify_admin_event(
                            "drive_auto_reconnect_failed",
                            "Reconexão automática do Google Drive falhou",
                            f"Não foi possível reconectar o Google Drive automaticamente durante a sincronização do perfil '{profile.get('nome', '')}'.",
                            "Abra o aplicativo nessa instalação e reconecte manualmente o Google Drive.",
                        )
                    return
                self._drain_drive_alerts()
                self._drive_connected = True
                self._safe_after(0, self._on_drive_connected)

            prev_pid = self._set_running_profile_id(profile_id)
            self._safe_after(0, lambda cur=profile_id, prv=prev_pid:
                       self._update_running_card(cur, prv))
            self._safe_after(0, self.progress.start)

            try:
                self.backup_mgr.run_sync(profile, history, cancel_evt=self._sync_cancel_evt)
            except (OSError, ValueError, KeyError, TypeError) as e:
                self.log(f"Erro no perfil '{profile.get('nome','')}': {e}", "ERROR")
            self.config_mgr.update(lambda cfg: cfg.__setitem__("history", list(history)))
            self.refresh_history(history)
        finally:
            prev = self._set_running_profile_id(None)
            self._safe_after(0, lambda prv=prev: self._update_running_card(None, prv))
            self._safe_after(0, self._progress_stop_reset)
            self._sync_lock.release()

    def _progress_stop_reset(self):
        self.progress.stop()
        self.progress.set(0)

    def _safe_after(self, ms: int, fn, *args):
        """
        Wrapper thread-safe para self.after().
        Evita 'main thread is not in main loop' quando uma thread de background
        tenta atualizar a UI depois que a janela já foi destruída.
        """
        if not getattr(self, "_app_alive", False):
            return
        try:
            self.after(ms, fn, *args)
        except (tk.TclError, RuntimeError):
            pass

    def _delete_profile(self, profile_id: str, nome: str):
        data = self.config_mgr.load()
        history = data.get("history", [])
        used = sum(1 for e in history if e.get("perfil") == nome)
        extra = f"\n\nEste perfil possui {used} registro(s) no histórico." if used else ""
        if messagebox.askyesno("Excluir perfil",
                               f"Deseja excluir o perfil '{nome}'?\n\n"
                               "Os arquivos no Drive não serão afetados."
                               f"{extra}"):
            self.config_mgr.delete_profile(profile_id)
            self._render_profiles()
            self.log(f"Perfil '{nome}' excluído.", "WARN")

    # ═══════════════════════════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════════════════════════
    def log(self, msg: str, level: str = "INFO"):
        def _do():
            ts   = datetime.now().strftime("%H:%M:%S")
            icon = {"INFO": "ℹ", "OK": "✔", "WARN": "⚠", "ERROR": "✖", "PROGRESS": "↑"}.get(level, "·")
            line = f"[{ts}] {icon} {msg}\n"
            log_box = getattr(self.log_text, "_textbox")
            self.log_text.configure(state="normal")
            if level == "PROGRESS":
                if self._log_progress_active and self._log_progress_start is not None:
                    log_box.delete(self._log_progress_start, "end-1c")
                self._log_progress_start = log_box.index("end-1c")
                self._log_progress_active = True
                log_box.insert("end", line, level)
            else:
                self._log_progress_active = False
                self._log_progress_start = None
                log_box.insert("end", line, level)
            log_box.see("end")
            self.log_text.configure(state="disabled")
            self.lbl_status.configure(text=msg[:90])
        self._safe_after(0, _do)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")
        self._log_progress_active = False
        self._log_progress_start = None

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
            visible_entries = list(reversed(entries[-50:]))
            for e in visible_entries:
                sc  = TEXT_GRN if e.get("status") == "OK" else TEXT_RED
                row = ctk.CTkFrame(self.hist_box, fg_color=BG_CARD, corner_radius=6,
                                   border_width=1, border_color=BORDER)
                row.pack(fill="x", pady=2, padx=4)
                row.columnconfigure(1, weight=1)
                ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                             text_color=sc, width=20
                             ).grid(row=0, column=0, padx=(10, 0), pady=7)
                # Arquivo + perfil
                info = e.get("filename", "—")
                if e.get("perfil"):
                    info += f"  [{e['perfil']}]"
                ctk.CTkLabel(row, text=info,
                             font=FONT_MONO, text_color=TEXT_PRI, anchor="w"
                             ).grid(row=0, column=1, sticky="ew", padx=8)
                ctk.CTkLabel(row, text=e.get("datetime", ""),
                             font=FONT_SMALL, text_color=TEXT_SEC
                             ).grid(row=0, column=2, padx=(0, 10))
            if len(entries) > len(visible_entries):
                ctk.CTkLabel(self.hist_box,
                             text=f"Exibindo os {len(visible_entries)} registros mais recentes.",
                             font=FONT_TINY, text_color=TEXT_SEC
                             ).pack(pady=(6, 2))
        self._safe_after(0, _do)

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
            self._drain_drive_alerts()
            self._drive_connected = True
            self._safe_after(0, self._on_drive_connected)
            self.log("Google Drive conectado com sucesso!", "OK")
        else:
            drained = self._drain_drive_alerts()
            self._drive_connected = False
            self._safe_after(0, lambda: (
                self.conn_badge.configure(text="● Desconectado", text_color=TEXT_RED),
                self.btn_connect.configure(state="normal", text="Conectar Drive",
                                           fg_color=BG_INPUT, hover_color=BORDER,
                                           text_color=TEXT_SEC)
            ))
            self.log("Falha na autenticação com o Google Drive.", "ERROR")
            if drained == 0:
                self._notify_admin_event(
                    "drive_manual_connect_failed",
                    "Falha ao conectar o Google Drive",
                    "A tentativa manual de autenticação do Google Drive falhou.",
                    "Revise as credenciais e reconecte o Google Drive nessa instalação.",
                )

    def _on_drive_connected(self):
        self.conn_badge.configure(text="● Conectado", text_color=TEXT_GRN)
        self.btn_connect.configure(state="normal", text="Desconectar Drive",
                                   fg_color=ACCENT_RED, hover_color=ACCENT_RED_HOV,
                                   text_color="white")

    def _disconnect_drive(self):
        if messagebox.askyesno("Desconectar Drive",
                               "Deseja desconectar o Google Drive?\n\n"
                               "O token será removido e a sincronização será parada."):
            if self.scheduler.is_active():
                self.scheduler.stop()
                self._update_sync_button(False)
            self.drive_svc.disconnect()
            self._drive_connected = False
            self.conn_badge.configure(text="● Desconectado", text_color=TEXT_RED)
            self.btn_connect.configure(state="normal", text="Conectar Drive",
                                       fg_color=BG_INPUT, hover_color=BORDER,
                                       text_color=TEXT_SEC)
            self.log("Google Drive desconectado.", "WARN")

    def _check_drive_connection(self):
        if self.drive_svc.is_authenticated():
            self._drive_connected = True
            self._on_drive_connected()
            self.log("Sessão do Google Drive restaurada.", "OK")

    # ═══════════════════════════════════════════════════════════════════════════
    #  SYNC BUTTON
    # ═══════════════════════════════════════════════════════════════════════════
    def _on_sync_button(self):
        if self.scheduler.is_active():
            self.scheduler.stop()
            self._update_sync_button(False)
            self.log("Sincronização parada.", "WARN")
            self._persist_globals()
        else:
            if not self._drive_connected:
                messagebox.showwarning("Drive não conectado",
                                       "Conecte-se ao Google Drive antes de sincronizar.")
                return
            profiles = [p for p in self.config_mgr.get_profiles() if p.get("ativo", True)]
            if not profiles:
                messagebox.showwarning("Sem perfis ativos",
                                       "Crie pelo menos um perfil de backup antes de sincronizar.")
                return
            self.scheduler.start()
            self._update_sync_button(True)
            modo = f"agendado ({self.var_interval.get()})" if self.var_auto.get() else "contínuo (5 min)"
            self.log(f"Sincronização iniciada — modo {modo}. "
                     f"{len(profiles)} perfil(is) ativo(s).", "OK")
            self._persist_globals()

    def _update_sync_button(self, active: bool):
        if active:
            self.btn_sync.configure(text="■  Parar Sincronização",
                                    fg_color=ACCENT_RED, hover_color=ACCENT_RED_HOV)
        else:
            self.btn_sync.configure(text="▶  Sincronizar",
                                    fg_color=ACCENT, hover_color=ACCENT_HOV)

    # ═══════════════════════════════════════════════════════════════════════════
    #  SCHEDULER
    # ═══════════════════════════════════════════════════════════════════════════
    def _on_interval_toggle(self):
        use = self.var_auto.get()
        self.scheduler.set_use_interval(use)
        self.log(f"Modo {'agendado — ' + self.var_interval.get() if use else 'contínuo (5 min)'}.", "INFO")
        self._persist_globals()

    def _on_interval_change(self, value: str):
        self.scheduler.set_interval(value)
        self.log(f"Intervalo alterado para: {value}", "INFO")
        self._persist_globals()

    def _do_background_sync(self):
        """Chamado pelo scheduler — roda todos os perfis ativos em sequência."""
        if not self._sync_lock.acquire(blocking=False):
            return
        try:
            if self._sync_cancel_evt.is_set():
                return
            data     = self.config_mgr.load()
            profiles = [p for p in data.get("profiles", []) if p.get("ativo", True)]
            history  = data.get("history", [])

            if not profiles:
                self.log("Nenhum perfil ativo para sincronizar.", "WARN")
                return

            if not self.drive_svc.is_authenticated():
                self.log("Drive desconectado — tentando reconectar...", "WARN")
                if not self.drive_svc.authenticate():
                    self.log("Reconexão automática falhou.", "ERROR")
                    drained = self._drain_drive_alerts()
                    if drained == 0:
                        self._notify_admin_event(
                            "drive_auto_reconnect_failed",
                            "Reconexão automática do Google Drive falhou",
                            "Não foi possível reconectar o Google Drive automaticamente durante a sincronização agendada.",
                            "Abra o aplicativo nessa instalação e reconecte manualmente o Google Drive.",
                        )
                    return
                self._drain_drive_alerts()
                self._drive_connected = True
                self._safe_after(0, self._on_drive_connected)

            self._safe_after(0, self.progress.start)

            for profile in profiles:
                if self._sync_cancel_evt.is_set():
                    self.log("Sincronização cancelada.", "WARN")
                    break
                current_pid = profile.get("id")
                prev_pid = self._set_running_profile_id(current_pid)
                self._safe_after(0, lambda cur=current_pid, prv=prev_pid:
                           self._update_running_card(cur, prv))
                try:
                    self.backup_mgr.run_sync(profile, history, self._sync_cancel_evt)
                except (OSError, ValueError, KeyError, TypeError) as e:
                    self.log(f"Erro no perfil '{profile.get('nome','')}': {e}", "ERROR")

            self.config_mgr.update(lambda cfg: cfg.__setitem__("history", list(history)))
            self.refresh_history(history)

        finally:
            prev = self._set_running_profile_id(None)
            self._safe_after(0, lambda prv=prev: self._update_running_card(None, prv))
            self._sync_lock.release()
            self._safe_after(0, self._progress_stop_reset)

    def _tick_scheduler_status(self):
        status = self.scheduler.get_status()
        def _do():
            self.lbl_next.configure(text=f"Próximo sync: {status['next_run']}")
            self.lbl_last.configure(text=f"Último sync:  {status['last_run']}")
            self.lbl_sched_status.configure(
                text=f"● Sync ativo — próximo: {status['next_run']}" if status["active"] else "● Sync parado",
                text_color=TEXT_GRN if status["active"] else TEXT_SEC)
        self._safe_after(0, _do)
        if self._sched_after_id is not None:
            try:
                self.after_cancel(self._sched_after_id)
            except tk.TclError:
                pass
        self._sched_after_id = self.after(10_000, self._tick_scheduler_status)

    def _tray_sync_now(self):
        if not self.scheduler.is_active():
            self.log("Sync está parado. Inicie pela janela principal.", "WARN")
            return
        if self._sync_cancel_evt.is_set():
            self.log("Sync cancelado. Inicie novamente pela janela principal.", "WARN")
            return
        threading.Thread(target=self._do_background_sync, daemon=True).start()

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
            else:
                self.log("Não foi possível ativar a inicialização automática.", "ERROR")
                self.var_boot.set(False)
        else:
            autostart.disable()
            self.log("Inicialização automática desativada.", "INFO")

    # ═══════════════════════════════════════════════════════════════════════════
    #  TRAY
    # ═══════════════════════════════════════════════════════════════════════════
    def _minimize_to_tray(self):
        grabber = None
        try:
            grabber = self.grab_current()
        except tk.TclError:
            grabber = None
        if self._modal_count > 0 or (grabber is not None and grabber.winfo_toplevel() is not self):
            messagebox.showwarning(
                "Janela aberta",
                "Feche a janela de edição de perfil antes de minimizar para a bandeja.",
                parent=self,
            )
            return
        self.withdraw()
        self._start_tray_icon()

    def _start_tray_icon(self):
        try:
            import pystray
            from PIL import Image, ImageDraw
            ico_path = _resolve_icon()
            img = None
            if ico_path:
                try:
                    img = Image.open(ico_path).convert("RGBA")
                except OSError:
                    img = None
            if img is None:
                img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([4, 20, 36, 52],  fill="#238636")
                draw.ellipse([20, 12, 52, 44], fill="#238636")
                draw.ellipse([28, 20, 60, 52], fill="#238636")
                draw.rectangle([8, 36, 56, 56], fill="#238636")
            menu = pystray.Menu(
                pystray.MenuItem("Abrir",      lambda: self._safe_after(0, self._show_window), default=True),
                pystray.MenuItem("Sync agora", lambda: self._safe_after(0, self._tray_sync_now)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Encerrar",   lambda: self._safe_after(0, self._quit_app)),
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
        if messagebox.askyesno("Encerrar",
                               f"Deseja encerrar o {APP_NAME}?\n\n"
                               "A sincronização automática será interrompida."):
            self._quit_app()

    def _quit_app(self):
        self._app_alive = False   # sinaliza threads antes de destroy()
        self.scheduler.stop()
        if self._tray_icon:
            self._tray_icon.stop()
        if self._sched_after_id is not None:
            try:
                self.after_cancel(self._sched_after_id)
            except tk.TclError:
                pass
        self.destroy()

    def start_tray_icon(self):
        self._start_tray_icon()

    # ═══════════════════════════════════════════════════════════════════════════
    #  CONFIG
    # ═══════════════════════════════════════════════════════════════════════════
    def _save_globals(self):
        self._persist_globals()
        self.log("Configurações globais salvas.", "OK")

    def _open_email_config(self):
        data = self.config_mgr.load()
        current_cfg = data.get("email_config", {})
        admin_cfg = {
            "installation_label": data.get("installation_label", ""),
            "admin_alerts_enabled": data.get("admin_alerts_enabled", False),
        }

        def _on_save(new_cfg: dict, new_admin_cfg: dict):
            def _update(d: dict):
                d["email_config"] = new_cfg
                d["installation_label"] = new_admin_cfg.get("installation_label", "")
                d["admin_alerts_enabled"] = bool(new_admin_cfg.get("admin_alerts_enabled", False))
            self.config_mgr.update(_update)
            self.email_svc.update_config(new_cfg)
            self._refresh_admin_alert_status()
            self.log("Configuração de e-mail salva.", "OK")

        EmailConfigForm(self, current_cfg, admin_cfg, _on_save)

    def _persist_globals(self):
        def _update(data: dict):
            data["auto_sync"] = self.var_auto.get()
            data["sync_interval"] = self.var_interval.get()
            data["sync_active"] = self.scheduler.is_active()

        self.config_mgr.update(_update)

    def _load_all(self):
        data = self.config_mgr.load()

        # Sincroniza config de e-mail com o serviço em memória
        self.email_svc.update_config(data.get("email_config", {}))

        interval = data.get("sync_interval", "1 hora")
        if interval in SyncScheduler.INTERVALS:
            self.var_interval.set(interval)
            self.cmb_interval.set(interval)
            self.scheduler.set_interval(interval)

        use_interval = data.get("auto_sync", False)
        self.var_auto.set(use_interval)
        self.scheduler.set_use_interval(use_interval)

        if data.get("sync_active", False):
            self.scheduler.start()
            self._update_sync_button(True)
            self.log("Sincronização restaurada automaticamente.", "OK")

        self._render_profiles()
        self.refresh_history(data.get("history", []))
        self._refresh_admin_alert_status(data)
        self._drain_drive_alerts()
        self.log("Configuração carregada.", "OK")

    def _drain_drive_alerts(self):
        count = 0
        for event in self.drive_svc.pop_pending_alert_events():
            self.alert_svc.notify_admin_event(event)
            count += 1
        return count

    def _notify_admin_event(self, event_code: str, title: str, message: str, action: str):
        self.alert_svc.notify_admin_event({
            "event_code": event_code,
            "title": title,
            "message": message,
            "action": action,
            "occurred_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })

    def _notify_scheduler_error(self, detail: str):
        self._notify_admin_event(
            "scheduler_sync_failed",
            "Falha global na rotina de sincronização",
            detail,
            "Revise o aplicativo nessa instalação e o log para identificar a causa da interrupção do sync.",
        )

    def _refresh_admin_alert_status(self, data: dict | None = None):
        if self.lbl_admin_alerts is None:
            return
        data = data or self.config_mgr.load()
        enabled = bool(data.get("admin_alerts_enabled", False))
        installation_label = str(data.get("installation_label", "") or "").strip()
        inferred_label = ConfigManager._normalize_installation_label(
            installation_label,
            data.get("profiles", []),
        )

        if not enabled:
            self.lbl_admin_alerts.configure(
                text="Alertas administrativos desativados.",
                text_color=TEXT_SEC,
            )
            return

        if installation_label:
            self.lbl_admin_alerts.configure(
                text=f"Alertas administrativos ativos para: {installation_label}",
                text_color=TEXT_GRN,
            )
            return

        self.lbl_admin_alerts.configure(
            text=(
                "Alertas administrativos ativos sem identificação manual da instalação. "
                f"O envio usará: {inferred_label}. Revise em ✉ E-mail."
            ),
            text_color=TEXT_YEL,
        )

    def _get_running_profile_id(self) -> str | None:
        with self._running_profile_lock:
            return self._running_profile_id

    def _set_running_profile_id(self, profile_id: str | None) -> str | None:
        with self._running_profile_lock:
            prev = self._running_profile_id
            self._running_profile_id = profile_id
            return prev


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_minimized = "--minimized" in sys.argv
    app = BackupApp(start_minimized=start_minimized)
    if start_minimized:
        app.withdraw()
        app.start_tray_icon()
    app.mainloop()
