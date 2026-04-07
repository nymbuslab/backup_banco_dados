# AJUSTES.md — Plano de Correções GR7 Backup Manager

Gerado em: 07/04/2026
Baseado em análise completa de: `main.py`, `backup_manager.py`, `drive_service.py`,
`scheduler.py`, `config_manager.py`, `app_paths.py`, `autostart.py`, `email_service.py`

---

## FASE 1 — CRÍTICO (bugs, crashes, segurança)

### F1-01 · [SEGURANÇA] Token OAuth salvo com `pickle` — risco de execução arbitrária de código
**Arquivo:** `drive_service.py` — métodos de save/load do token
**Problema:** `pickle.load()` executa código arbitrário ao desserializar. Um `token.pkl` substituído por um atacante com acesso à pasta do `.exe` resulta em execução de código no contexto do usuário na próxima abertura do app.
**Correção:** Substituir `pickle` por `google.oauth2.credentials.Credentials.to_json()` e `from_authorized_user_info()`. Serializa apenas os campos necessários em JSON puro, sem risco de desserialização.

---

### F1-02 · [SEGURANÇA] Senha SMTP armazenada em plaintext no `backup_config.json`
**Arquivo:** `config_manager.py` (`email_config`) / `email_service.py`
**Problema:** O campo `smtp_password` é gravado como string plana no JSON ao lado do `.exe`. Em ambientes compartilhados ou com backup do diretório, a credencial fica exposta.
**Correção:** Usar `keyring` com backend Windows Credential Manager (DPAPI). Salvar apenas um identificador no JSON; ler/gravar a senha via `keyring.get_password` / `keyring.set_password`.

---

### F1-03 · [CRASH] Race condition em `_sync_profile_now` — acquire/release sem propósito
**Arquivo:** `main.py` — `_sync_profile_now`
**Problema:** O lock é adquirido, verificado e **imediatamente liberado** antes de lançar a thread. Entre o `release()` e o `acquire()` real dentro de `_do_profile_sync`, duas threads podem passar pela verificação ao mesmo tempo se o usuário clicar duas vezes no botão ▶ rapidamente.
**Correção:** Remover as 3 linhas de acquire/release de `_sync_profile_now`. A proteção real já existe no `acquire(blocking=False)` no início de `_do_profile_sync`.

---

### F1-04 · [BUG] Scheduler iniciado antes de verificar autenticação no startup
**Arquivo:** `main.py` — `__init__` / `_load_all`
**Problema:** A sequência é `_build_ui()` → `_load_all()` (restaura scheduler) → `_check_drive_connection()`. O scheduler pode disparar o primeiro ciclo de sync antes de `_drive_connected` ser atualizado, gerando "tentando reconectar..." mesmo com token válido — experiência confusa para o usuário.
**Correção:** Mover `_check_drive_connection()` para antes de `_load_all()`, ou chamar dentro de `_load_all()` antes de restaurar `sync_active`.

---

### F1-05 · [BUG] Race condition na escrita de `_running_profile_id` sem lock
**Arquivo:** `main.py` — `_do_background_sync` / `_do_profile_sync`
**Problema:** `_running_profile_id` é escrita diretamente pela thread do scheduler sem proteção. A main thread lê essa variável durante `_render_profiles()` (callbacks de CRUD). Sem lock, a leitura pode ver um valor inconsistente.
**Correção:** Proteger leituras e escritas de `_running_profile_id` com `_sync_lock` ou um `threading.Lock()` dedicado.

---

### F1-06 · [BUG] Sliding window pode deletar arquivo errado se nome não contém data
**Arquivo:** `backup_manager.py` — `_sync_rotacao` (bloco sliding window)
**Problema:** A ordenação usa `_extract_sort_key` que retorna o próprio nome do arquivo como fallback quando não encontra uma data no padrão `YYYYMMDD`. Dois arquivos sem data serão ordenados alfabeticamente e o "mais antigo" pode não ser o arquivo mais antigo de fato.
**Correção:** Incluir `createdTime` no `fields` da chamada `list_files_in_folder` e usá-lo como critério de ordenação quando `_extract_sort_key` não encontrar data no nome.

---

### F1-07 · [BUG] `_persist_globals` + `_do_profile_sync` podem sobrescrever dados um do outro
**Arquivo:** `main.py` — `_persist_globals` / `_do_profile_sync`; `config_manager.py`
**Problema:** Ambos usam o padrão `load() → modify → save()` sem lock global. Se executados concorrentemente (usuário clica "Salvar Config" durante sync), um save pode sobrescrever o do outro — histórico pode ser perdido.
**Correção:** Adicionar um `threading.Lock()` no `ConfigManager` que serialize todos os ciclos read-modify-write.

---

## FASE 2 — IMPORTANTE (lógica, comportamento inesperado)

### F2-01 · [LOGICA] Alerta de backup atrasado ausente no modo espelho
**Arquivo:** `backup_manager.py` — `_sync_espelho`
**Problema:** `_check_backup_age` só é chamada no modo rotação. Perfis em modo espelho nunca disparam o alerta de "sem novos backups", mesmo que a pasta local esteja parada há dias.
**Correção:** Coletar os arquivos locais no início de `_sync_espelho` (com `_scan_local` ou equivalente) e chamar `_check_backup_age` antes de iniciar o espelhamento.

---

### F2-02 · [BUG] `EmailConfigForm._test` — dois `messagebox` sequenciais causam UX confusa
**Arquivo:** `main.py` — `EmailConfigForm._test`
**Problema:** O primeiro `messagebox.showinfo("Enviando…")` é modal e bloqueia o event loop. O usuário deve fechá-lo manualmente para o segundo (com o resultado) aparecer. A sensação é de que o programa travou.
**Correção:** Remover o primeiro messagebox. Trocar por um `CTkLabel` de status na própria janela que muda para "Enviando…" e depois para "Enviado ✔" ou "Falhou ✖".

---

### F2-03 · [LOGICA] `_running` em `scheduler.py` lido/escrito fora do lock
**Arquivo:** `scheduler.py` — `start()` / `stop()`
**Problema:** `self._running` é lido em `start()` e escrito em `stop()` fora do `_lock`. Em condição de corrida, `start()` pode ver `_running=True` stale e não iniciar nova thread, ou iniciar thread duplicada.
**Correção:** Mover toda leitura e escrita de `_running` para dentro do bloco `with self._lock`.

---

### F2-04 · [LOGICA] `_migrate` em `config_manager.py` não protege contra `email_config: null`
**Arquivo:** `config_manager.py` — `_migrate`
**Problema:** `defaults.update(raw)` pode sobrescrever `email_config` com `null` se o arquivo JSON tiver esse campo com valor nulo. O `EmailService` receberia `None` como config e crasharia em `is_configured()` com `AttributeError`.
**Correção:** Após o `update`, garantir: `if not isinstance(data.get("email_config"), dict): data["email_config"] = defaults_email_config`.

---

### F2-05 · [LOGICA] `autostart.disable()` loga erro quando autostart nunca foi ativado
**Arquivo:** `autostart.py` — `disable()`
**Problema:** Ao tentar desativar o autostart que nunca foi ativado, `winreg.DeleteValue` lança `FileNotFoundError`, que é capturado e logado como "Erro ao desativar". Isso pode assustar o usuário ou confundir durante debug.
**Correção:** Capturar `FileNotFoundError` separadamente e ignorar silenciosamente (ou logar em nível DEBUG).

---

## FASE 3 — MELHORIA (qualidade, robustez, UX)

### F3-01 · [UI] Flash da janela ao iniciar minimizado (`--minimized`)
**Arquivo:** `main.py` — bloco `if __name__ == "__main__"`
**Problema:** `BackupApp()` cria e renderiza a janela no `__init__`. O `withdraw()` é chamado depois, causando um flash visível da janela em monitores lentos ou HDD.
**Correção:** Detectar `"--minimized" in sys.argv` antes de instanciar o app e chamar `self.withdraw()` no início do `__init__`, antes de `_build_ui()`.

---

### F3-02 · [PERF] `get_profiles()` lê o disco a cada chamada
**Arquivo:** `config_manager.py` — `get_profiles()`
**Problema:** Faz I/O de disco em cada chamada. É invocado em `_edit_profile`, `_toggle_profile`, `_sync_profile_now` e outras. Em máquinas com HDD, pode causar latência perceptível na UI.
**Correção:** Manter um cache em memória no `ConfigManager` que é invalidado apenas após `save()`. Baixo risco de introduzir bugs e elimina I/O desnecessário.

---

### F3-03 · [PERF] `refresh_history` recria ~800 widgets a cada sync
**Arquivo:** `main.py` — `refresh_history`
**Problema:** Com 200 entradas no histórico, destrói e recria ~800 widgets a cada chamada. Chamado ao final de cada sync. Em máquinas lentas pode travar a UI por centenas de milissegundos.
**Correção:** Implementar renderização incremental: ao invés de destruir tudo, comparar com estado anterior e só adicionar/remover as entradas que mudaram. Ou limitar a exibição a 50 entradas mais recentes com scroll paginado.

---

### F3-04 · [PERF] `_espelho_dir` cria pastas no Drive antes de verificar se há arquivos
**Arquivo:** `backup_manager.py` — `_espelho_dir` (modo recursivo)
**Problema:** Em modo recursivo, `get_or_create_folder` é chamado para cada subdiretório local antes de verificar se há arquivos nele. Subpastas vazias geram chamadas de API desnecessárias.
**Correção:** Verificar primeiro se há arquivos locais (ou subpastas com arquivos) antes de criar a pasta correspondente no Drive.

---

### F3-05 · [LOGICA] `_extract_date` pode extrair datas de sequências numéricas não-calendário
**Arquivo:** `backup_manager.py` — `_extract_date`
**Problema:** O regex `(\d{4})(\d{2})(\d{2})` combina com qualquer 8 dígitos. Arquivos com IDs numéricos (ex: `backup_v12345678.sql`) podem ter datas extraídas incorretamente, afetando alertas de idade.
**Correção:** Exigir que os 8 dígitos sejam precedidos por um separador não-numérico ou início de string, e validar o range da data extraída (mês 1–12, dia 1–31) antes de retornar.

---

## Resumo

| Fase | Itens | Prioridade |
|------|-------|------------|
| FASE 1 — Crítico | 7 | Resolver antes do próximo release |
| FASE 2 — Importante | 5 | Resolver no release seguinte |
| FASE 3 — Melhoria | 5 | Backlog de qualidade |

**Começar por:** F1-01 (pickle→JSON), F1-03 (race condition botão), F1-07 (lock ConfigManager), F2-04 (email_config null crash).
