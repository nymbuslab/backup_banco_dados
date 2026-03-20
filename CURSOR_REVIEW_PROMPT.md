# PROMPT PARA O CURSOR — REVISÃO DO PROJETO GR7 BACKUP MANAGER

## Contexto do Projeto

Este é um aplicativo desktop Windows em Python para sincronização automática de backups com o Google Drive.

**Stack:**
- Interface: CustomTkinter (CTk)
- API: Google Drive v3 (google-api-python-client)
- Empacotamento: PyInstaller (--onefile --windowed)
- Python 3.10+

**Estrutura de arquivos:**
```
app_paths.py       — resolução de caminhos (.py vs .exe PyInstaller)
autostart.py       — registro no Windows (HKCU Run) para iniciar com o sistema
backup_manager.py  — lógica de sync: modo Rotação (sliding window) e modo Espelho (mirror)
config_manager.py  — leitura/escrita do backup_config.json + migração de formato antigo
drive_service.py   — toda comunicação com a API do Google Drive (auth, upload, delete)
scheduler.py       — loop de agendamento em thread daemon (modo contínuo ou intervalo)
main.py            — UI completa: lista de perfis, formulário modal, log, histórico
```

---

## O que já está funcionando e NÃO pode ser quebrado

> Trate estas funcionalidades como intocáveis em termos de comportamento externo.
> Você pode refatorar internamente, mas o resultado final deve ser idêntico.

1. **Autenticação OAuth2 com Google Drive** — fluxo de token, refresh automático, persistência em `token.pkl`
2. **Modo Rotação** — sliding window: mantém exatamente N backups no Drive, remove apenas o mais antigo ao fazer upload do novo
3. **Validação inteligente de contagem** — só alerta erro se o backup mais antigo já tem mais de (N-1) dias (respeita o período de acumulação inicial)
4. **Modo Espelho** — envia arquivos locais que não existem no Drive, nunca remove nada, suporta subpastas recursivas (toggle por perfil)
5. **Estrutura de pastas no Drive**: `Pasta Pai → Cliente → Nome do Perfil → arquivos`
6. **Sistema de perfis múltiplos** — cada perfil tem modo, pasta, extensões, configurações independentes; todos rodam em sequência no mesmo ciclo de sync
7. **Migração automática de config** — se `backup_config.json` estiver no formato antigo (sem `profiles[]`), converte automaticamente preservando dados
8. **Scheduler** — modo contínuo (5 min) e modo agendado (intervalos configuráveis); estado `sync_active` salvo e restaurado ao reiniciar
9. **Resolução de caminhos** — `app_paths.py` e `_resolve_icon()` devem continuar funcionando tanto em `.py` quanto em `.exe` (PyInstaller `sys._MEIPASS`)
10. **Autostart Windows** — `autostart.py` escreve no registro com o caminho correto entre aspas e flag `--minimized`
11. **Upload com progresso e retry** — log mostra `[KB / total] % @ KB/s` e tenta até 3x com backoff em falhas de rede
12. **Thread safety** — `self._sync_lock` previne syncs paralelos; `self.after(0, ...)` para atualizações de UI a partir de threads

---

## O que quero que o Cursor revise e sugira melhorias

### 1. Qualidade e robustez do código

- Identifique **race conditions** ou problemas de thread safety que possam ter passado despercebidos
- Verifique se há **memory leaks** potenciais (especialmente no loop do scheduler e no histórico de UI)
- Revise o tratamento de **exceções** — há lugares onde erros silenciosos podem esconder problemas reais?
- O `_sync_lock` cobre todos os caminhos de sync (manual, agendado, tray menu)?

### 2. drive_service.py — API do Google Drive

- O **retry com backoff** está implementado corretamente para todos os tipos de erro de rede?
- A **autenticação** está lidando corretamente com tokens expirados durante um upload longo?
- Há risco de **quota exceeded** (429) que não está sendo tratado?
- O **upload resumable** está configurado para retomar de onde parou em caso de falha, ou recomeça do zero?

### 3. backup_manager.py — Lógica de negócio

- No modo Espelho recursivo, se uma subpasta falhar ao ser criada no Drive, o que acontece com as demais? A lógica atual é a mais adequada?
- O `_validate_count` usa `date.today()` — isso é correto para servidores em fusos horários diferentes do Brasil?
- Há algum edge case no `_extract_sort_key` que possa fazer a ordenação dar errado?

### 4. config_manager.py — Persistência

- A operação de `save()` é atômica? Se o processo morrer no meio de uma escrita, o JSON fica corrompido?
- O `_migrate()` pode ser chamado múltiplas vezes sem efeito colateral?

### 5. main.py — Interface

- O `ProfileForm` (CTkToplevel modal) está sendo destruído corretamente em todos os caminhos (salvar, cancelar, fechar com X)?
- Há algum problema com o `grab_set()` se a janela principal estiver minimizada ou na bandeja?
- O histórico acumula widgets sem limite no `hist_box` — isso pode causar lentidão com muitos registros?
- O `_tick_scheduler_status` usa `self.after(10_000, ...)` em loop — isso pode acumular callbacks se a janela for recriada?

### 6. scheduler.py

- O `_stop_evt.wait(timeout=15)` é a melhor abordagem? Há risco de o scheduler não parar rapidamente o suficiente?
- Se `_do_sync()` lançar uma exceção não capturada, o loop para? Está protegido adequadamente?

### 7. Melhorias de UX sugeridas (implemente apenas se não quebrar nada)

- Mostrar no card do perfil na lista a data/hora do **último sync bem-sucedido** daquele perfil
- Indicador visual (spinner ou cor) no card do perfil **enquanto está sendo sincronizado**
- Confirmação antes de **excluir um perfil** que já tem histórico de uploads
- Botão **"Sync manual deste perfil"** no card, para forçar apenas um perfil sem rodar todos

---

## Regras para as sugestões

1. **Não refatore o que funciona sem motivo claro** — cada mudança deve ter justificativa explícita
2. **Mantenha compatibilidade com Python 3.10+** — não use features do 3.12+
3. **Não troque bibliotecas** — CustomTkinter, google-api-python-client e pystray são fixos
4. **Preserve o formato do backup_config.json** — qualquer mudança de schema precisa incluir migração
5. **Teste mental obrigatório** antes de sugerir qualquer mudança no scheduler ou drive_service: simule o comportamento com sync ativo, Drive desconectado, e reconexão automática
6. Para cada problema encontrado, mostre: **onde está**, **qual o risco**, **como corrigir**

---

## Formato esperado da revisão

Para cada arquivo, estruture assim:

```
### arquivo.py

PROBLEMAS CRÍTICOS (podem causar bugs ou perda de dados):
- [descrição + linha + correção sugerida]

MELHORIAS DE ROBUSTEZ (não quebram nada, tornam mais sólido):
- [descrição + linha + correção sugerida]

MELHORIAS DE UX (apenas se explicitamente pedido acima):
- [descrição + implementação]

SEM PROBLEMAS IDENTIFICADOS: [se for o caso]
```

Comece pela leitura completa de todos os arquivos antes de fazer qualquer sugestão.
