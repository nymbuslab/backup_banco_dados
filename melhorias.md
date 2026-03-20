# Melhorias — GR7 Backup Manager

Este arquivo serve como checklist de evolução do projeto para evitar retrabalho e perda de contexto.

## Regras do Processo

- Cada item deve virar 1 PR/commit (ou 1 lote pequeno), com validação ao final.
- Não subir dados sensíveis: `credentials.json`, `token.pkl`, `backup_config.json` (já ignorados no `.gitignore`).
- Não quebrar comportamento existente (principalmente: OAuth, modos Rotação/Espelho, estrutura de pastas no Drive, scheduler, tray).
- Sempre validar no final de cada mudança:
  - `python -m py_compile main.py backup_manager.py drive_service.py scheduler.py config_manager.py`
  - Smoke test: abrir UI, conectar Drive, rodar “Sync agora”, cancelar no meio.

## Status

Legenda:
- [ ] pendente
- [x] feito
- [~] em andamento

## 1) Estabilidade / Dados (Alta prioridade)

- [x] Cancelamento real do upload ao parar sincronização (UI → scheduler → backup_manager → drive_service)
- [x] Escrita atômica do `backup_config.json` (temp + replace)
- [x] `ConfigManager.load()` resiliente a JSON corrompido: fallback para `.bak` (se existir) e quarentena do arquivo corrompido
- [x] `ConfigManager._migrate()` sempre mesclar com defaults (garantir chaves globais mesmo em configs parciais)

## 2) Google Drive / API (Alta prioridade)

- [x] Retry inteligente por status HTTP (`HttpError`):
  - 401: refresh + rebuild service
  - 403/429: backoff exponencial (e `Retry-After` quando existir)
  - 5xx: retry com backoff
- [x] Escape seguro de nomes em query (`get_or_create_folder`): tratar apóstrofos em `name='...'`
- [ ] Otimização de listagem em pastas grandes:
  - [x] Rotação: evitar listar “tudo” quando possível (consultar por nomes esperados / limitar janela)
  - [x] Espelho recursivo: cache por pasta durante o ciclo

## 3) Scheduler / Execução (Média prioridade)

- [x] Garantir que “Sync agora” do tray respeita `sync_active` e `cancel_evt` (não iniciar corrida paralela)
- [x] Tornar o loop mais responsivo (reduzir `wait(timeout=15)` ou calcular timeout pelo `next_run`)
- [x] Evitar múltiplos `after()` duplicados no `_tick_scheduler_status` (guardar `after_id` e cancelar ao destruir)

## 4) UI / UX (Média prioridade)

- [x] Progresso no log em “uma linha” (sem spam) de forma consistente (suporte a `PROGRESS` na UI)
- [x] Mostrar “último sync OK” no card do perfil (baseado no `history`)
- [x] Indicador visual do perfil “em execução” durante o loop de sync
- [x] “Sync manual deste perfil” no card (respeitando `_sync_lock` e cancelamento)
- [x] Ao excluir perfil, alertar se existe histórico associado

## 5) Autostart / Tray (Média prioridade)

- [x] Em desenvolvimento, resolver `pythonw.exe` de forma robusta (não depender do PATH)
- [x] Se existir modal aberto (ProfileForm), bloquear minimizar para bandeja para evitar `grab_set()` travado

## 6) Build / Compatibilidade (Decisão necessária)

Windows 7:
- [ ] Decidir: manter suporte real ao Windows 7 ou focar Windows 10/11.
  - Se Win7 for obrigatório: rebaixar código para Python 3.8 (remover `str | None`, `list[...]`, etc.)
  - Se Win7 não for obrigatório: remover modo “Win7/Python 3.8” do `build.bat` e alinhar README

## 7) Documentação mínima (Baixa prioridade)

- [ ] Alinhar README com nome real do executável e comando de build atual
- [ ] Adicionar seção “Arquivos que NÃO devem ir para o GitHub” (sem incluir conteúdo sensível)
