# 🏥 Senai Tech — Secretária Virtual Anna

Sistema web completo para o consultório de cardiologia **Senai Tech**.  
Interface conversacional estilo **WhatsApp** integrada ao **Azure AI Projects** e painel administrativo exclusivo para os médicos **Dr. Clark** e **Dr. Jorge**.

---

## ⚙️ Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Back-end | Python + Flask |
| Banco de Dados | SQLite |
| Agente de IA | Azure AI Projects (azure-ai-projects) |
| Autenticação Azure | DefaultAzureCredential (azure-identity) |
| Front-end | HTML5, CSS3, JavaScript puro |
| Ícones | Font Awesome 6 |
| Fontes | Google Fonts (Inter) |

---

## 📁 Estrutura do Projeto

```text
Secretaria-agente/
├── app.py                  # Servidor Flask (rotas e API REST)
├── database.py             # Camada SQLite (agendamento, cancelamento, consultas)
├── chatbot_anna.py         # Integração com o Agente Azure AI
├── requirements.txt        # Dependências Python
├── .env.example            # Modelo de variáveis de ambiente (copie para .env)
├── .gitignore              # Arquivos ignorados pelo Git
├── templates/
│   ├── index.html          # Chat estilo WhatsApp (Secretária Anna)
│   └── admin.html          # Portal e Dashboard dos Médicos
└── static/
    ├── css/
    │   ├── chat.css        # Estilo do chat WhatsApp
    │   └── admin.css       # Estilo do painel médico
    └── js/
        ├── chat.js         # Lógica do chat no navegador
        └── admin.js        # Dashboard médico reativo
```

> ⚠️ Os arquivos `.env` e `clinica.db` **nunca são enviados ao GitHub** (estão no `.gitignore`). Eles contêm credenciais e dados de pacientes.

---

## 🚀 Como Executar Localmente

### 1. Clone o repositório
```bash
git clone https://github.com/EnzoCoppini/Secretaria-agente.git
cd Secretaria-agente
```

### 2. Crie e ative um ambiente virtual
```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências
```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

Copie o arquivo de exemplo e preencha com suas credenciais do Azure AI:
```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```env
AZURE_AI_ENDPOINT=https://SEU-RECURSO.services.ai.azure.com/api/projects/SEU-PROJETO
AZURE_AI_AGENT_NAME=nome-do-seu-agente
AZURE_AI_API_KEY=SUA_CHAVE_AZURE_AQUI
```

> As credenciais do Azure estão em: **Azure Portal → Azure AI Projects → Keys and Endpoint**

### 5. Inicie o servidor
```bash
python app.py
```

### 6. Acesse no Navegador
| Página | URL |
|--------|-----|
| Chat da Paciente (Secretária Anna) | http://127.0.0.1:5000/ |
| Portal dos Médicos | http://127.0.0.1:5000/admin |

---

## 🔐 Credenciais do Painel Médico

| Médico | Senha |
|--------|-------|
| Dr. Clark | `1234` |
| Dr. Jorge | `1234` |

---

## 🤖 Sobre o Agente de IA (Azure AI)

O chat é alimentado por um **Agente criado no Azure AI Studio**, configurado como a secretária **Anna** do consultório Senai Tech.  
O agente gerencia as conversações em linguagem natural e o backend Python sincroniza automaticamente os agendamentos e cancelamentos com o banco de dados SQLite.

### Como funciona a sincronização:
1. O paciente conversa livremente com Anna no chat.
2. A Anna (Agente Azure) coleta nome, CPF, data de nascimento, médico, data e horário.
3. Quando a Anna confirma o agendamento, o backend Python detecta a confirmação e salva no SQLite.
4. O agendamento aparece imediatamente no **Painel dos Médicos** (`/admin`).
5. Se o paciente solicitar cancelamento e a Anna confirmar, o status é atualizado automaticamente no banco.

---

## 📋 Banco de Dados

O banco `clinica.db` é criado automaticamente na primeira execução com a tabela:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INTEGER | Protocolo único da consulta |
| `nome_paciente` | TEXT | Nome completo do paciente |
| `cpf` | TEXT | CPF do paciente |
| `data_nascimento` | TEXT | Data de nascimento |
| `medico` | TEXT | Dr. Clark ou Dr. Jorge |
| `data` | TEXT | Data da consulta (YYYY-MM-DD) |
| `horario` | TEXT | Horário (HH:MM) |
| `status` | TEXT | Agendada / Realizada / Cancelada |
| `criado_em` | TIMESTAMP | Data/hora do registro |

---

## 📄 Licença

Projeto educacional desenvolvido para o consultório de cardiologia **Senai Tech**.
