import os
import re
from datetime import datetime, date, timedelta
import database

# ============================================================================
# CARREGAMENTO DE VARIÁVEIS DE AMBIENTE (.env)
# ============================================================================
def _carregar_env():
    """Carrega o arquivo .env se existir, garantindo funcionamento com ou sem python-dotenv."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # Fallback nativo: lê o .env se as variáveis ainda não estiverem no os.environ
    caminhos_env = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.getcwd(), ".env"),
        ".env"
    ]
    for caminho in caminhos_env:
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    for linha in f:
                        linha = linha.strip()
                        if linha and not linha.startswith("#") and "=" in linha:
                            chave, valor = linha.split("=", 1)
                            chave = chave.strip()
                            valor = valor.strip().strip("'\"")
                            if chave not in os.environ or not os.environ[chave]:
                                os.environ[chave] = valor
                break
            except Exception:
                pass

_carregar_env()

# Constantes da Clínica
CLINICA_NOME = "Senai Tech - Cardiologia"
SECRETARIA_NOME = "Anna"
MEDICOS_DISPONIVEIS = ["Dr. Clark", "Dr. Jorge"]

# Mapeamento de Sessão Web -> ID de Conversação no Azure AI
sessoes_azure = {}

# Dados acumulados da consulta em progresso por sessão
dados_sessao_paciente = {}

# Instância única do cliente OpenAI conectado ao Azure AI
_openai_client = None

MESES_PT = {
    'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9,
    'outubro': 10, 'novembro': 11, 'dezembro': 12
}

PALAVRAS_INVALIDAS_NOME = {
    'anna', 'doutor', 'dr', 'dr.', 'paciente', 'consulta', 'agendamento',
    'obrigado', 'obrigada', 'perfeito', 'perfeita', 'bom dia', 'boa tarde',
    'boa noite', 'sim', 'nao', 'não', 'claro', 'ola', 'olá', 'tudo bem',
    'por favor', 'ok', 'certo', 'disposição', 'disposicao', 'dados'
}

def obter_cliente_azure():
    """Inicializa e reaproveita o cliente conectado ao agente no Azure AI Projects."""
    global _openai_client
    if _openai_client is None:
        _carregar_env()
        endpoint = os.getenv("AZURE_AI_ENDPOINT", "").strip()
        agent_name = os.getenv("AZURE_AI_AGENT_NAME", "enzo-coppini").strip()

        if not endpoint:
            raise ValueError(
                "AZURE_AI_ENDPOINT não configurado! "
                "Verifique se o arquivo .env existe e contém AZURE_AI_ENDPOINT."
            )

        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient

            credential = DefaultAzureCredential()
            project_client = AIProjectClient(
                endpoint=endpoint,
                credential=credential,
                allow_preview=True
            )
            _openai_client = project_client.get_openai_client(agent_name=agent_name)
            print(f"[Azure AI] Conectado com sucesso ao agente '{agent_name}'.")
        except Exception as e:
            print(f"[Azure AI Erro] Falha ao conectar ao Azure AI: {e}")
            raise e
    return _openai_client
    return _openai_client

def obter_ou_criar_conversacao(session_id: str) -> str:
    """Garante que a sessão web tenha uma conversa ativa no Azure AI."""
    if session_id not in sessoes_azure:
        client = obter_cliente_azure()
        conv = client.conversations.create()
        sessoes_azure[session_id] = conv.id
        dados_sessao_paciente[session_id] = {}
        print(f"[Azure AI] Nova conversa iniciada: {conv.id} para sessão: {session_id}")
    return sessoes_azure[session_id]

def resetar_historico(session_id: str):
    """Reinicia a conversa do usuário gerando um novo ID de conversa no Azure."""
    if session_id in sessoes_azure:
        del sessoes_azure[session_id]
    if session_id in dados_sessao_paciente:
        del dados_sessao_paciente[session_id]
    print(f"[Azure AI] Sessão {session_id} reiniciada.")

def limpar_resposta_agente(texto: str) -> str:
    """Remove metadados internos do Azure (ex: 'Idioma: Português | Tom: Neutro') para exibição limpa no WhatsApp."""
    if not texto:
        return ""
    texto_limpo = re.sub(r'^Idioma:\s*[^\|\n]+\|\s*Tom:\s*[^\n]+\n*', '', texto, flags=re.IGNORECASE).strip()
    return texto_limpo

def processar_mensagem_agente(session_id: str, mensagem_usuario: str) -> str:
    """
    Envia a mensagem do paciente para o Agente Azure 'enzo-coppini' (Anna),
    mantendo o histórico conversacional e sincronizando agendamentos/cancelamentos no SQLite.
    """
    try:
        client = obter_cliente_azure()
        conv_id = obter_ou_criar_conversacao(session_id)

        # 1. Envia mensagem para o agente no Azure AI
        response = client.responses.create(
            conversation=conv_id,
            input=[{"role": "user", "content": mensagem_usuario}]
        )

        texto_agente = response.output_text or ""
        resposta_formatada = limpar_resposta_agente(texto_agente)

        # 2. Sincroniza cancelamento primeiro (caso seja solicitação de cancelamento)
        msg_canc = tentar_sincronizar_cancelamento(session_id, mensagem_usuario, resposta_formatada)
        if msg_canc:
            resposta_formatada += f"\n\n{msg_canc}"
        else:
            # 3. Só tenta sincronizar novo agendamento se NÃO for cancelamento
            msg_extra = tentar_sincronizar_agendamento(session_id, mensagem_usuario, resposta_formatada)
            if msg_extra:
                resposta_formatada += f"\n\n{msg_extra}"

        return resposta_formatada

    except Exception as e:
        print(f"[Erro Azure AI]: {e}")
        return (
            "⚠️ Desculpe, tive uma instabilidade momentânea na conexão com o servidor de IA. "
            f"Detalhe: {str(e)}"
        )

# ============================================================================
# CANCELAMENTO PRECISO NO BANCO SQLITE (clinica.db)
# ============================================================================
def tentar_sincronizar_cancelamento(session_id: str, msg_usuario: str, resposta_agente: str):
    """
    Detecta se o paciente solicitou cancelamento ou se a Anna confirmou que a consulta foi cancelada,
    atualizando imediatamente o status no SQLite para 'Cancelada'.
    """
    texto_total = f"{msg_usuario}\n{resposta_agente}"

    # Indicadores de que a mensagem trata de cancelamento
    usuario_pediu = any(t in msg_usuario.lower() for t in ["cancelar", "desmarcar", "nao vou conseguir", "não vou conseguir", "não posso ir"])
    agente_cancelou = any(t in resposta_agente.lower() for t in ["foi cancelado", "foi cancelada", "cancelado com sucesso", "desmarcado", "desmarcada", "cancelamento confirmado"])

    if not (usuario_pediu or agente_cancelou):
        return None

    # 1. Extração do médico
    medico = None
    if re.search(r'\bclark\b', texto_total, re.IGNORECASE):
        medico = "Dr. Clark"
    elif re.search(r'\bjorge\b', texto_total, re.IGNORECASE):
        medico = "Dr. Jorge"

    # 2. Extração da data da consulta cancelada
    data_canc = None
    hoje = date.today()
    datas_barras = re.findall(r'\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b', texto_total)
    for d, m, a in datas_barras:
        if int(a) >= hoje.year:
            data_canc = f"{int(a)}-{int(m):02d}-{int(d):02d}"
            break

    # 3. Extração do horário da consulta cancelada
    hora_canc = None
    m_hora = re.search(r'\b(0?[9]|1[0-7]):([0-5][0-9])\b', texto_total)
    if m_hora:
        hora_canc = f"{int(m_hora.group(1)):02d}:{m_hora.group(2)}"

    # 4. Extração de CPF se informado
    cpf_canc = None
    m_cpf = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2}|\b\d{11}\b)', texto_total)
    if m_cpf:
        nums = re.sub(r'\D', '', m_cpf.group(1))
        cpf_canc = f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"

    # Tentativa A: Cancelar por médico + data + horário (mais comum nas respostas da Anna)
    if medico and data_canc and hora_canc:
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, nome_paciente FROM consultas 
                WHERE medico = ? AND data = ? AND horario = ? AND status = 'Agendada'
            ''', (medico, data_canc, hora_canc))
            row = cursor.fetchone()
            if row:
                consulta_id = row['id']
                nome = row['nome_paciente']
                database.atualizar_status_consulta(consulta_id, 'Cancelada')
                partes = data_canc.split('-')
                data_br = f"{partes[2]}/{partes[1]}/{partes[0]}"
                print(f"[SQLite] SUCESSO: Consulta #{consulta_id} de {nome} marcada como CANCELADA para {medico} em {data_canc} {hora_canc}")
                return f"✅ *[Sistema Senai Tech: Consulta #{consulta_id} de {nome} cancelada com sucesso no banco de dados. Horário das {hora_canc} em {data_br} liberado.]*"

    # Tentativa B: Cancelar por CPF
    if cpf_canc:
        consultas = database.buscar_consultas_por_cpf(cpf_canc)
        if consultas:
            for c in consultas:
                database.atualizar_status_consulta(c['id'], 'Cancelada')
                print(f"[SQLite] SUCESSO: Consulta #{c['id']} cancelada via CPF {cpf_canc}")
            return f"✅ *[Sistema Senai Tech: Consulta(s) associada(s) ao CPF {cpf_canc} cancelada(s) no banco de dados.]*"

    # Tentativa C: Cancelar por ID ativo na sessão atual
    if session_id in dados_sessao_paciente and "consulta_id" in dados_sessao_paciente[session_id]:
        c_id = dados_sessao_paciente[session_id]["consulta_id"]
        sucesso = database.atualizar_status_consulta(c_id, 'Cancelada')
        if sucesso:
            print(f"[SQLite] SUCESSO: Consulta #{c_id} cancelada na sessão atual.")
            return f"✅ *[Sistema Senai Tech: Consulta #{c_id} cancelada com sucesso no banco de dados.]*"

    return None

# ============================================================================
# AGENDAMENTO ROBUSTO NO BANCO SQLITE (clinica.db)
# ============================================================================
def tentar_sincronizar_agendamento(session_id: str, msg_usuario: str, resposta_agente: str):
    """
    Extrai informações acumuladas da conversa e salva a consulta no SQLite
    para que apareça imediatamente no Painel dos Médicos (/admin).
    """
    if session_id not in dados_sessao_paciente:
        dados_sessao_paciente[session_id] = {}

    dados = dados_sessao_paciente[session_id]
    texto_total = f"{msg_usuario}\n{resposta_agente}"
    hoje = date.today()

    # 1. Médico (Dr. Clark ou Dr. Jorge)
    m_med = re.search(r'\b(Dr\.\s*Clark|Dr\.\s*Jorge|Clark|Jorge)\b', texto_total, re.IGNORECASE)
    if m_med:
        val = m_med.group(1).lower()
        dados["medico"] = "Dr. Clark" if "clark" in val else "Dr. Jorge"

    # 2. Datas no formato numérico DD/MM/AAAA (ex: 18/10/2026, 14/08/2006)
    datas_barras = re.findall(r'\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b', texto_total)
    for d, m, a in datas_barras:
        d_int, m_int, a_int = int(d), int(m), int(a)
        if a_int >= hoje.year and 1 <= m_int <= 12 and 1 <= d_int <= 31:
            dados["data"] = f"{a_int}-{m_int:02d}-{d_int:02d}"
        elif a_int < hoje.year and 1 <= m_int <= 12 and 1 <= d_int <= 31:
            dados["data_nascimento"] = f"{d_int:02d}/{m_int:02d}/{a_int}"

    # Datas relativas ou por extenso
    if "data" not in dados:
        if re.search(r'\bamanh[aã]\b', texto_total, re.IGNORECASE):
            dados["data"] = (hoje + timedelta(days=1)).strftime('%Y-%m-%d')
        elif re.search(r'\bhoje\b', texto_total, re.IGNORECASE):
            dados["data"] = hoje.strftime('%Y-%m-%d')
        else:
            m_ext = re.search(r'(\d{1,2})\s+de\s+([a-zA-Zç]+)(?:\s+de\s+(\d{4}))?', texto_total, re.IGNORECASE)
            if m_ext:
                dia_ext = int(m_ext.group(1))
                mes_nome = m_ext.group(2).lower()
                ano_ext = int(m_ext.group(3)) if m_ext.group(3) else hoje.year
                if mes_nome in MESES_PT:
                    dados["data"] = f"{ano_ext}-{MESES_PT[mes_nome]:02d}-{dia_ext:02d}"

    # 3. Horários no formato HH:MM ou HHh (ex: 10:00, 14h, às 10)
    m_hora = re.search(r'\b(0?[9]|1[0-7]):([0-5][0-9])\b', texto_total)
    if m_hora:
        dados["horario"] = f"{int(m_hora.group(1)):02d}:{m_hora.group(2)}"
    else:
        m_hora_h = re.search(r'\b(0?[9]|1[0-7])h(?:([0-5][0-9]))?\b', texto_total, re.IGNORECASE)
        if m_hora_h:
            minuto = m_hora_h.group(2) if m_hora_h.group(2) else "00"
            dados["horario"] = f"{int(m_hora_h.group(1)):02d}:{minuto}"

    # 4. CPF do Paciente (11 dígitos ou XXX.XXX.XXX-XX)
    m_cpf = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2}|\b\d{11}\b)', msg_usuario)
    if m_cpf:
        nums = re.sub(r'\D', '', m_cpf.group(1))
        dados["cpf"] = f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"

    # 5. Nome do Paciente (com filtro anti-obrigado)
    m_nome_user = re.search(r'(?:meu nome [eé]|me chamo|nome:\s*|sou o|sou a)\s*([A-Za-zÀ-ÖØ-öø-ÿ\s]{3,35})', msg_usuario, re.IGNORECASE)
    if m_nome_user:
        nome_c = m_nome_user.group(1).split(',')[0].strip().title()
        if nome_c.lower() not in PALAVRAS_INVALIDAS_NOME:
            dados["nome_paciente"] = nome_c
    elif "nome_paciente" not in dados or dados["nome_paciente"].lower() in PALAVRAS_INVALIDAS_NOME:
        # Tenta da resposta da Anna (ex: "Perfeito, Enzo Coppini" ou "Claro, Enzo")
        m_nome_agente = re.search(r'(?:Perfeito|Ol[aá]|Claro|Certo),?\s*([A-Za-zÀ-ÖØ-öø-ÿ\s]{3,35})[.,!]', resposta_agente, re.IGNORECASE)
        if m_nome_agente:
            nome_c = m_nome_agente.group(1).strip().title()
            if nome_c.lower() not in PALAVRAS_INVALIDAS_NOME:
                dados["nome_paciente"] = nome_c

    # 6. Indicador de Confirmação pelo Agente
    confirmado = bool(re.search(
        r'(?:foi agendada|agendada para o dia|agendamento.*ficou|consulta.*confirmada|confirmad[oa]|recebi seus dados|agendamento.*encaminhado)',
        resposta_agente,
        re.IGNORECASE
    ))

    # ========================================================================
    # GRAVAÇÃO / ATUALIZAÇÃO NO BANCO SQLITE (clinica.db)
    # ========================================================================
    if "medico" in dados and "data" in dados and "horario" in dados:
        nome = dados.get("nome_paciente", "Paciente Agendado")
        if nome.lower() in PALAVRAS_INVALIDAS_NOME:
            nome = "Paciente Agendado"

        cpf = dados.get("cpf", "000.000.000-00")
        data_nasc = dados.get("data_nascimento", "Não informada")
        medico = dados["medico"]
        data_c = dados["data"]
        horario_c = dados["horario"]

        # Se ainda não foi gravada no banco:
        if "consulta_id" not in dados:
            if confirmado or (nome != "Paciente Agendado" and cpf != "000.000.000-00"):
                consulta_id, msg = database.criar_consulta(nome, cpf, data_nasc, medico, data_c, horario_c)
                if consulta_id:
                    dados["consulta_id"] = consulta_id
                    partes = data_c.split('-')
                    data_br = f"{partes[2]}/{partes[1]}/{partes[0]}"
                    print(f"[SQLite] SUCESSO: Consulta #{consulta_id} gravada no banco para {medico} em {data_c} às {horario_c} ({nome})")
                    return f"✅ *[Sistema Senai Tech: Consulta #{consulta_id} registrada com sucesso no banco de dados para o {medico} em {data_br} às {horario_c}. Paciente: {nome}]*"
                else:
                    print(f"[SQLite Aviso] Não foi possível criar consulta: {msg}")
        else:
            # Se já foi gravada, atualiza com os dados enriquecidos
            consulta_id = dados["consulta_id"]
            database.atualizar_dados_consulta(consulta_id, nome, cpf, data_nasc)
            print(f"[SQLite] Consulta #{consulta_id} atualizada com dados do paciente: {nome}, CPF: {cpf}, Nasc: {data_nasc}")

    return None
