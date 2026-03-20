# GDrive Backup Manager

Aplicativo desktop para sincronizar backups locais com o Google Drive.

---

## ✅ Pré-requisitos

- Python 3.10+
- Conta Google com o Drive API habilitado

---

## 🔑 Configurar credenciais do Google Drive (1x apenas)

1. Acesse: https://console.cloud.google.com/
2. Crie um projeto novo (ex: "BackupManager")
3. No menu lateral → **APIs e Serviços** → **Biblioteca**
4. Pesquise **Google Drive API** → Ativar
5. Vá em **APIs e Serviços** → **Credenciais**
6. Clique em **Criar Credenciais** → **ID do cliente OAuth 2.0**
7. Tipo de aplicativo: **Aplicativo de computador**
8. Baixe o JSON gerado
9. Renomeie para `credentials.json`
10. Coloque na mesma pasta que `main.py` (ou do `.exe` gerado)

---

## 🚀 Executar em desenvolvimento

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar
python main.py
```

---

## 📦 Gerar executável (.exe) no Windows

```bash
# Opção 1: script automático
build.bat

# Opção 2: manual
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "GDriveBackup" main.py
```

O `.exe` será gerado em `dist/GDriveBackup.exe`.

> ⚠️ Coloque `credentials.json` na mesma pasta do `.exe`.

---

## 📁 Estrutura de pastas no Drive

```
Google Drive/
└── BACKUP CLIENTES/          ← Pasta Pai
    └── Empresa ABC/          ← Cliente
        ├── BACKUP 20260315 2200.sql
        ├── BACKUP 20260316 2200.sql
        └── BACKUP 20260317 2200.sql   ← máx. N backups mantidos
```

---

## 🔁 Lógica de sincronização

1. Escaneia a pasta local pelos arquivos com a extensão configurada (`.sql`, `.bak`, etc.)
2. Ordena por data extraída do nome (`YYYYMMDD HHMM`)
3. Seleciona os **N mais recentes**
4. Se houver menos de N → exibe **erro** no log
5. Envia para o Drive os que ainda não foram enviados
6. Remove do Drive os arquivos mais antigos que excedam o limite N
7. Registra o histórico de cada operação

---

## 📋 Formato esperado dos arquivos de backup

O sistema extrai a data do nome do arquivo automaticamente:

```
BACKUP 20260317 2200.sql   ✔ Detectado: 20260317 2200
BACKUP_20260317_2200.bak   ✔ Detectado: 20260317 2200
relatorio20260317.sql      ✔ Detectado: 20260317
qualquer_nome.sql          ✔ Ordenado alfabeticamente como fallback
```

---

## 📁 Arquivos gerados

| Arquivo              | Descrição                          |
|---------------------|------------------------------------|
| `credentials.json`  | Credenciais OAuth2 (você fornece)  |
| `token.pkl`         | Token de sessão (gerado automaticamente) |
| `backup_config.json`| Configurações salvas               |
