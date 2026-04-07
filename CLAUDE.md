# GR7 Backup Manager — Contexto para Claude Code

## O que é este projeto

Aplicativo desktop Windows em Python para sincronização automática de backups locais com o Google Drive. Desenvolvido para uso em múltiplos clientes, distribuído como `.exe` gerado pelo PyInstaller.

**Stack:** Python 3.10+ · CustomTkinter · Google Drive API v3 · PyInstaller · pystray · Pillow

---

## Estrutura de arquivos

```
├── main.py              # UI completa (CustomTkinter) — 1229 linhas
├── backup_manager.py    # Lógica de sync: Rotação e Espelho — 341 linhas
├── drive_service.py     # Comunicação com Google Drive API — 355 linhas
├── scheduler.py         # Loop de agendamento em thread daemon — 142 linhas
├── config_manager.py    # Leitura/escrita do backup_config.json — 190 linhas
├── app_paths.py         # Resolução de caminhos (.py vs .exe) — 33 linhas
├── autostart.py         # Registro no Windows (HKCU Run) — 100 linhas
├── assets/
│   ├── gr7backup.ico    # Ícone com múltiplos tamanhos (16–256px)
│   └── gr7backup_icon.png
├── requirements.txt
└── build.bat            # Build com venv isolado; uso: build.bat [win11|win7]
```

---

## Arquivos gerados em runtime (não committar)

```
credentials.json          # OAuth2 do Google Cloud Console (usuário fornece)
token.pkl                 # Token de sessão OAuth (gerado automaticamente)
backup_config.json        # Configurações e histórico de backups
backup_config.json.bak    # Backup automático antes de cada save
backup_config.json.corrupt-YYYYMMDD-HHMMSS  # Quarentena se JSON corrompido
```

---

## Arquitetura de classes

### `main.py`

**`ProfileForm(ctk.CTkToplevel)`** — modal de criação/edição de perfil
- `_build()` — constrói o formulário com scroll
- `_load()` — preenche campos com dados do perfil existente
- `_on_modo_change(value)` — mostra/esconde campos conforme Rotação ou Espelho
- `_save()` — valida e chama `on_save(profile)`

**`BackupApp(ctk.CTk)`** — janela principal

*Variáveis de estado críticas:*
```python
self._app_alive           # False após destroy() — guards para _safe_after()
self._sync_lock           # threading.Lock() — previne syncs paralelos
self._sync_cancel_evt     # threading.Event() — cancela upload em andamento
self._running_profile_id  # str | None — qual perfil está sincronizando agora
self._card_refs           # dict[pid → {card, lbl_detail, base_detail}]
self._drive_connected     # bool
self._tray_icon           # pystray.Icon | None
self._sched_after_id      # ID do after() do tick scheduler
self._modal_count         # contador de ProfileForms abertos
```

*Métodos principais:*
```python
_safe_after(ms, fn, *args)          # wrapper thread-safe para self.after()
_render_profiles()                   # reconstrói TODA a lista (só em CRUD)
_render_profile_card(p, last_ok)     # cria um card e registra em _card_refs
_update_running_card(pid, prev_pid)  # atualiza SÓ a borda/texto do card ativo
_do_background_sync()                # roda todos os perfis ativos (scheduler)
_do_profile_sync(profile_id)         # roda só um perfil (botão ▶ do card)
log(msg, level)                      # INFO | OK | WARN | ERROR | PROGRESS
refresh_history(entries)             # atualiza painel de histórico
_persist_globals()                   # salva configurações globais no JSON
_load_all()                          # carrega config e restaura estado
```

### `backup_manager.py` — `BackupManager`

```python
run_sync(profile, history, cancel_evt)      # entry point — roteia pelo modo
_sync_rotacao(cfg, history, cancel_evt)     # sliding window — N mais recentes
_sync_espelho(cfg, history, cancel_evt)     # mirror — nunca remove do Drive
_espelho_dir(...)                           # recursão por subpastas
```

### `drive_service.py` — `DriveService`

```python
authenticate() -> bool                                 # OAuth2 + salva token.pkl
is_authenticated() -> bool                             # verifica + refresh automático
get_or_create_folder(name, parent_id) -> str | None   # cria se não existe
list_files_in_folder(folder_id) -> list[dict]          # com paginação completa
find_files_in_folder_by_names(folder_id, names)        # busca em lote (chunks de 20)
upload_file(local_path, folder_id, cancel_evt) -> bool # resumable + retry + progresso
delete_file(file_id, file_name) -> bool
disconnect()                                           # remove token.pkl
```

### `scheduler.py` — `SyncScheduler`

```python
start()                    # liga master (sync imediato + loop)
stop()                     # desliga master + seta cancel_evt
set_use_interval(bool)     # True=agendado, False=contínuo (5 min)
set_interval(label)        # "30 min" | "1 hora" | "2 horas" | ...
is_active() -> bool
get_status() -> dict       # active, last_run, next_run, interval_secs
```

### `config_manager.py` — `ConfigManager`

```python
save(data)                 # escrita atômica: tempfile → fsync → os.replace()
load() -> dict             # tenta .json → .bak → quarentena → empty
save_profile(profile)      # upsert por id
delete_profile(profile_id)
new_profile() -> dict      # perfil vazio com defaults
get_profiles() -> list
_migrate(raw) -> dict      # converte formato antigo (sem profiles[]) automaticamente
```

---

## Schema do `backup_config.json`

```json
{
  "profiles": [
    {
      "id": "prof_abc123",
      "nome": "Banco TESTE",
      "modo": "rotacao",
      "folder_pai": "GR7 BACKUP MANAGER",
      "cliente": "EMPRESA ABC",
      "backup_dir": "D:/GR7/Backup",
      "extensoes": ".sql",
      "qtd_backups": 3,
      "recursivo": false,
      "ativo": true
    }
  ],
  "sync_active": false,
  "auto_sync": false,
  "sync_interval": "1 hora",
  "history": [
    {
      "filename": "Backup 20260318 2200.sql",
      "perfil": "Banco TESTE",
      "datetime": "18/03/2026 22:00",
      "status": "OK"
    }
  ]
}
```

**Campos por modo:**
- `rotacao`: usa `extensoes`, `qtd_backups`
- `espelho`: usa `extensoes` (vazio = todos), `recursivo`

**Estrutura no Drive:** `folder_pai / cliente / nome-do-perfil / arquivos`

---

## Regras de thread safety — CRÍTICO

Toda chamada de UI a partir de uma thread de background **deve** usar `_safe_after()`:

```python
# ✖ ERRADO — pode causar "main thread is not in main loop"
self.after(0, self._on_drive_connected)

# ✔ CORRETO
self._safe_after(0, self._on_drive_connected)
```

`_safe_after()` verifica `self._app_alive` e captura `TclError`/`RuntimeError`.

Threads que tocam em UI: `_do_background_sync`, `_do_profile_sync`, `_do_connect`, `_tick_scheduler_status`, callbacks do pystray.

---

## Regras de atualização da lista de perfis

```
Situação                          → Método correto
──────────────────────────────────────────────────────────────
CRUD (criar/editar/excluir)       → _render_profiles()  (reconstrói tudo)
Indicador de sync (borda/texto)   → _update_running_card(pid, prev_pid)
```

**Nunca** chamar `_render_profiles()` no loop de sync — causa piscar a tela inteira.

---

## Comportamentos que NÃO podem mudar

1. **Rotação sliding window** — remove APENAS o mais antigo ao fazer upload do novo; nunca remove em lote
2. **Validação de contagem** — só alerta erro se o backup mais antigo tem mais de (N-1) dias
3. **Espelho** — nunca remove arquivos do Drive, só adiciona
4. **Migração automática** — `backup_config.json` antigo (sem `profiles[]`) é convertido silenciosamente
5. **Cancelamento cooperativo** — `cancel_evt` verificado em cada chunk de upload e em cada arquivo
6. **Escrita atômica do JSON** — tempfile + fsync + os.replace(); nunca escrever direto no arquivo
7. **Resolução de ícone** — `_resolve_icon()` busca em `sys._MEIPASS/assets/`, `sys._MEIPASS/`, `exe_dir/assets/`, `exe_dir/` nessa ordem
8. **Autostart** — registra com aspas no caminho e flag `--minimized`

---

## Próximos itens pendentes

### Sistema de atualização automática (não implementado)
- Verificar `version.json` num servidor/GitHub na inicialização (thread background)
- Baixar `.exe` novo → `GR7BackupManager_new.exe`
- Criar `updater.bat` → aguarda processo fechar → renomeia → reinicia
- UI: banner discreto no topo ou popup com notas da versão
- Arquivos necessários: `version.py` (constante `APP_VERSION`), `updater.py`

### Provider pattern para múltiplas nuvens (arquitetura futura)
- Interface `CloudProvider` com: `authenticate`, `get_or_create_folder`, `list_files_in_folder`, `upload_file`, `delete_file`, `disconnect`
- `drive_service.py` vira `providers/google_drive.py`
- Campo `"provider"` no perfil seleciona a implementação

### Credenciais embutidas (sem credentials.json manual)
- `InstalledAppFlow.from_client_config(EMBEDDED_DICT, SCOPES)` em vez de `from_client_secrets_file`
- Distribui as credenciais dentro do `.exe` (ofuscadas)
- Limite: 100 usuários sem verificação OAuth do Google

---

## Build

```bat
# Windows 10/11 (Python atual)
build.bat

# Windows 7 (Python 3.8)
build.bat win7

# Sem pausa no final (CI/automação)
set NO_PAUSE=1 && build.bat
```

Saída: `dist\GR7BackupManager.exe`

O `credentials.json` deve estar na mesma pasta do `.exe` gerado.

---

## Paleta de cores (CustomTkinter dark theme)

```python
BG_DARK        = "#0D1117"   # fundo da janela
BG_CARD        = "#161B22"   # cards e painéis
BG_INPUT       = "#1C2128"   # campos de entrada
BORDER         = "#30363D"   # bordas
ACCENT         = "#238636"   # verde (sync ativo, rotação, OK)
ACCENT_RED     = "#B91C1C"   # vermelho (parar, desconectar, erro)
ACCENT_BLUE    = "#1F6FEB"   # azul (espelho, perfil rodando)
TEXT_GRN       = "#3FB950"   # texto verde (log OK)
TEXT_RED       = "#F85149"   # texto vermelho (log ERROR)
TEXT_YEL       = "#D29922"   # texto amarelo (log WARN)
TEXT_SEC       = "#8B949E"   # texto secundário
```

Fontes: `FONT_HEAD` (20 bold), `FONT_SUB` (12 bold), `FONT_BODY` (11), `FONT_SMALL` (10), `FONT_TINY` (9), `FONT_MONO` (Consolas 11).
