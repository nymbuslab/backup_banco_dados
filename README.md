# GR7 Backup Manager (GDrive Backup Manager)

Aplicativo desktop Windows para sincronizar backups locais com o Google Drive.

## ✅ Pré-requisitos

- Windows 10/11
- Python 3.10+ (funciona com Python 3.14)
- Conta Google com a Drive API habilitada

## 🔑 Configurar credenciais do Google Drive (1x apenas)

1. Acesse: https://console.cloud.google.com/
2. Crie um projeto (ex: "GR7BackupManager")
3. **APIs e Serviços** → **Biblioteca** → ative **Google Drive API**
4. **APIs e Serviços** → **Credenciais** → **Criar credenciais** → **ID do cliente OAuth 2.0**
5. Tipo: **Aplicativo de computador**
6. Baixe o JSON, renomeie para `credentials.json`
7. Coloque o `credentials.json` na mesma pasta do `main.py` (desenvolvimento) ou ao lado do `GR7BackupManager.exe` (executável)

## 🚀 Executar em desenvolvimento

```bash
pip install -r requirements.txt
python main.py
```

## 📦 Gerar executável (.exe) no Windows

O build cria um executável **sem console** e com ícone embutido.

### Opção 1 (recomendado): build.bat

PowerShell:

```powershell
.\build.bat win11
```

Sem pausa no final:

```powershell
$env:NO_PAUSE=1; .\build.bat win11
```

Saída:
- `dist\GR7BackupManager.exe`

### Opção 2: manual (PyInstaller)

```powershell
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --name "GR7BackupManager" `
  --icon "assets\gr7backup.ico" `
  --add-data "assets\gr7backup.ico;assets" `
  --add-data "assets\gr7backup.ico;." `
  --hidden-import=pystray._win32 `
  --hidden-import=PIL `
  --collect-data=customtkinter `
  main.py
```

### Sobre o ícone do EXE

- O ícone do executável fica embutido via `--icon`.
- O arquivo `assets\gr7backup.ico` precisa ter múltiplos tamanhos (16/32/48/…); caso contrário o Windows pode mostrar um ícone genérico.

## 🧩 Perfis e modos de sincronização

O app suporta múltiplos perfis. Cada perfil tem:
- pasta local (`backup_dir`)
- pasta pai e cliente no Drive (`folder_pai` / `cliente`)
- modo: **Rotação** ou **Espelho**

### Rotação (sliding window)

- Mantém exatamente **N backups mais recentes** no Drive (por perfil).
- Sobe arquivos que ainda não existem e remove o mais antigo quando excede N.

### Espelho (mirror)

- Sobe arquivos que ainda não existem no Drive.
- Não remove nada.

## 📁 Estrutura de pastas no Drive

Estrutura padrão criada pelo app:

```
Google Drive/
└── <Pasta Pai>/
    └── <Cliente>/
        └── <Nome do Perfil>/
            ├── BACKUP 20260315 2200.sql
            ├── BACKUP 20260316 2200.sql
            └── BACKUP 20260317 2200.sql
```

## 🛑 Cancelamento e progresso

- O botão **Parar Sincronização** cancela o upload em andamento (o cancelamento acontece no próximo “chunk” do upload resumable).
- O log de progresso é atualizado em **uma linha** (sem spam).

## 📋 Formato esperado dos arquivos de backup

O app tenta extrair a data do nome do arquivo:

```
BACKUP 20260317 2200.sql   ✔ Detectado: 20260317 2200
BACKUP_20260317_2200.bak   ✔ Detectado: 20260317 2200
relatorio20260317.sql      ✔ Detectado: 20260317
qualquer_nome.sql          ✔ Fallback: ordenação por nome
```

## 📁 Arquivos gerados (não subir no GitHub)

| Arquivo                         | Descrição |
|---------------------------------|----------|
| `credentials.json`              | Credenciais OAuth2 (você fornece) |
| `token.pkl`                     | Token de sessão (gerado automaticamente) |
| `backup_config.json`            | Configurações e histórico |
| `backup_config.json.bak`        | Backup automático do JSON |
| `backup_config.json.corrupt-*`  | Quarentena quando o JSON está corrompido |

Esses arquivos já estão ignorados no `.gitignore` do projeto.
