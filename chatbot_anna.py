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

# ============================================================================
# EXTRAÇÃO E VALIDAÇÃO DE DISPONIBILIDADE EM TEMPO REAL NO SQLITE
# ============================================================================
def extrair_dados_parciais(texto: str, dados_acumulados: dict = None) -> dict:
    """Extrai informações parciais de agendamento da mensagem do usuário e do contexto."""
    res = dict(dados_acumulados) if dados_acumulados else {}
    hoje = date.today()

    # Médico
    if re.search(r'\b(Dr\.\s*Clark|Clark)\b', texto, re.IGNORECASE):
        res["medico"] = "Dr. Clark"
    elif re.search(r'\b(Dr\.\s*Jorge|Jorge)\b', texto, re.IGNORECASE):
        res["medico"] = "Dr. Jorge"

    # Data no formato DD/MM/AAAA
    datas_barras = re.findall(r'\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b', texto)
    for d, m, a in datas_barras:
        d_int, m_int, a_int = int(d), int(m), int(a)
        if a_int >= hoje.year and 1 <= m_int <= 12 and 1 <= d_int <= 31:
            res["data"] = f"{a_int}-{m_int:02d}-{d_int:02d}"
        elif a_int < hoje.year and 1 <= m_int <= 12 and 1 <= d_int <= 31:
            res["data_nascimento"] = f"{d_int:02d}/{m_int:02d}/{a_int}"

    # Data no formato DD/MM (apenas se NÃO for parte de DD/MM/AAAA)
    if "data" not in res:
        datas_curtas = re.findall(r'\b(\d{1,2})\/(\d{1,2})(?!\/\d{2,4})\b', texto)
        for d, m in datas_curtas:
            d_int, m_int = int(d), int(m)
            if 1 <= m_int <= 12 and 1 <= d_int <= 31:
                ano_escolhido = hoje.year
                try:
                    dt_check = date(ano_escolhido, m_int, d_int)
                    if dt_check < hoje:
                        ano_escolhido += 1
                    res["data"] = f"{ano_escolhido}-{m_int:02d}-{d_int:02d}"
                    break
                except ValueError:
                    pass

    # Datas relativas ou por extenso
    if "data" not in res:
        if re.search(r'\bamanh[aã]\b', texto, re.IGNORECASE):
            res["data"] = (hoje + timedelta(days=1)).strftime('%Y-%m-%d')
        elif re.search(r'\bhoje\b', texto, re.IGNORECASE):
            res["data"] = hoje.strftime('%Y-%m-%d')
        else:
            m_ext = re.search(r'(\d{1,2})\s+de\s+([a-zA-Zç]+)(?:\s+de\s+(\d{4}))?', texto, re.IGNORECASE)
            if m_ext:
                dia_ext = int(m_ext.group(1))
                mes_nome = m_ext.group(2).lower()
                ano_ext = int(m_ext.group(3)) if m_ext.group(3) else hoje.year
                if mes_nome in MESES_PT:
                    res["data"] = f"{ano_ext}-{MESES_PT[mes_nome]:02d}-{dia_ext:02d}"

    # Horário (HH:MM, HHh, às HH)
    m_hora = re.search(r'\b(0?[9]|1[0-7]):([0-5][0-9])\b', texto)
    if m_hora:
        res["horario"] = f"{int(m_hora.group(1)):02d}:{m_hora.group(2)}"
    else:
        m_hora_h = re.search(r'\b(0?[9]|1[0-7])h(?:([0-5][0-9]))?\b', texto, re.IGNORECASE)
        if m_hora_h:
            minuto = m_hora_h.group(2) if m_hora_h.group(2) else "00"
            res["horario"] = f"{int(m_hora_h.group(1)):02d}:{minuto}"
        else:
            m_hora_as = re.search(r'\b[àa]s\s*(0?[9]|1[0-7])\b', texto, re.IGNORECASE)
            if m_hora_as:
                res["horario"] = f"{int(m_hora_as.group(1)):02d}:00"

    # CPF
    m_cpf = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2}|\b\d{11}\b)', texto)
    if m_cpf:
        nums = re.sub(r'\D', '', m_cpf.group(1))
        res["cpf"] = f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"

    return res

def verificar_restricoes_agendamento(session_id: str, mensagem_usuario: str):
    """
    Verifica se a tentativa de agendamento viola regras de negócio:
    - Horário já alocado para outro paciente
    - Horário no passado
    - Horário fora do expediente (09:00 às 17:00)
    """
    dados_acum = dados_sessao_paciente.get(session_id, {})
    dados = extrair_dados_parciais(mensagem_usuario, dados_acum)

    # Se ainda não temos médico e data, não há restrição a verificar
    if "medico" not in dados or "data" not in dados:
        return None

    medico = dados["medico"]
    data_str = dados["data"]
    partes = data_str.split('-')
    data_br = f"{partes[2]}/{partes[1]}/{partes[0]}"
    hoje = date.today()

    # 1. Se informou horário específico, checa conflito
    if "horario" in dados:
        horario = dados["horario"]

        # Checa se está no passado
        try:
            dt_hora = datetime.strptime(f"{data_str} {horario}", "%Y-%m-%d %H:%M")
            if dt_hora < datetime.now():
                return {
                    "status": "passado",
                    "medico": medico,
                    "data": data_str,
                    "data_br": data_br,
                    "horario": horario
                }
        except Exception:
            pass

        # Checa se já está alocado para outro paciente no SQLite
        consulta_ocupada = database.obter_consulta_no_horario(medico, data_str, horario)
        if consulta_ocupada:
            cid_sessao = dados_acum.get("consulta_id")
            # Se a consulta encontrada não pertencer à sessão do usuário atual:
            if not cid_sessao or cid_sessao != consulta_ocupada["id"]:
                livres = database.obter_horarios_disponiveis(medico, data_str)
                return {
                    "status": "ocupado",
                    "medico": medico,
                    "data": data_str,
                    "data_br": data_br,
                    "horario": horario,
                    "horarios_livres": livres,
                    "paciente_alocado": consulta_ocupada.get("nome_paciente")
                }

    # 2. Se for uma consulta geral sobre disponibilidade de horários
    termos_busca = ["horarios", "horários", "vagas", "livre", "livres", "disponivel", "disponível", "tem horario", "tem horário"]
    if any(t in mensagem_usuario.lower() for t in termos_busca) and "horario" not in dados:
        livres = database.obter_horarios_disponiveis(medico, data_str)
        return {
            "status": "consulta_horarios",
            "medico": medico,
            "data": data_str,
            "data_br": data_br,
            "horarios_livres": livres
        }

    return None

def processar_mensagem_agente(session_id: str, mensagem_usuario: str) -> str:
    """
    Envia a mensagem do paciente para o Agente Azure 'enzo-coppini' (Anna),
    mantendo o histórico conversacional e sincronizando agendamentos/cancelamentos no SQLite.
    Garante aplicação rigorosa das regras de negócio de horários alocados.
    """
    try:
        client = obter_cliente_azure()
        conv_id = obter_ou_criar_conversacao(session_id)

        # Atualiza dados conhecidos da sessão com base no texto do usuário
        if session_id not in dados_sessao_paciente:
            dados_sessao_paciente[session_id] = {}
        dados_atualizados = extrair_dados_parciais(mensagem_usuario, dados_sessao_paciente[session_id])
        dados_sessao_paciente[session_id].update(dados_atualizados)

        # 1. Checa previamente se há restrição de horário ocupado no SQLite
        restricao = verificar_restricoes_agendamento(session_id, mensagem_usuario)
        msg_para_ia = mensagem_usuario

        if restricao:
            if restricao["status"] == "ocupado":
                medico = restricao["medico"]
                data_br = restricao["data_br"]
                horario = restricao["horario"]
                livres = restricao["horarios_livres"]
                txt_livres = ", ".join(livres) if livres else "nenhum horário livre nesta data (ofereça outra data)"
                
                # Injeta aviso de sistema com dados reais do SQLite para o Agente da Azure
                msg_para_ia = (
                    f"[INFORMAÇÃO DO SISTEMA DA CLÍNICA SENAI TECH - BANCO DE DADOS EM TEMPO REAL]\n"
                    f"O paciente deseja marcar para {data_br} às {horario} com o {medico}.\n"
                    f"REGRA DE NEGÓCIO RIGOROSA: Este horário JÁ ESTÁ ALOCADO para outro paciente e é PROIBIDO agendar nele!\n"
                    f"Você DEVE informar educadamente que o horário das {horario} já está ocupado e oferecer as seguintes opções livres para o {medico} nesta data: {txt_livres}.\n"
                    f"NUNCA solicite dados cadastrais e NUNCA confirme agendamento para horários já ocupados!\n"
                    f"[FIM DA INFORMAÇÃO]\n\n"
                    f"Mensagem do paciente: {mensagem_usuario}"
                )
            elif restricao["status"] == "consulta_horarios":
                medico = restricao["medico"]
                data_br = restricao["data_br"]
                livres = restricao["horarios_livres"]
                txt_livres = ", ".join(livres) if livres else "todos os horários estão ocupados nesta data"
                msg_para_ia = (
                    f"[INFORMAÇÃO DO SISTEMA - HORÁRIOS DISPONÍVEIS]: Os horários vagos para o {medico} no dia {data_br} são: {txt_livres}.\n\n"
                    f"Mensagem do paciente: {mensagem_usuario}"
                )
            elif restricao["status"] == "passado":
                msg_para_ia = (
                    f"[INFORMAÇÃO DO SISTEMA]: O paciente pediu uma data ou horário que já passou ({restricao['data_br']} às {restricao['horario']}). "
                    f"Informe gentilmente que não é possível agendar no passado e peça para escolher uma data futura.\n\n"
                    f"Mensagem do paciente: {mensagem_usuario}"
                )

        # 2. Envia mensagem para o agente no Azure AI
        response = client.responses.create(
            conversation=conv_id,
            input=[{"role": "user", "content": msg_para_ia}]
        )

        texto_agente = response.output_text or ""
        resposta_formatada = limpar_resposta_agente(texto_agente)

        # 3. Blindagem determinística: se o horário estava ocupado, garante que a resposta nunca aceite o horário ocupado
        if restricao and restricao["status"] == "ocupado":
            medico = restricao["medico"]
            data_br = restricao["data_br"]
            horario = restricao["horario"]
            livres = restricao["horarios_livres"]
            txt_livres = ", ".join(livres) if livres else "Infelizmente todos os horários deste dia já foram preenchidos. Gostaria de verificar outra data?"

            # Se a IA alucinar e pedir dados ou disser que agendou mesmo com o aviso:
            pediu_dados = any(k in resposta_formatada.lower() for k in ["cpf", "nascimento"]) and "nome" in resposta_formatada.lower()
            confirmou = any(k in resposta_formatada.lower() for k in ["confirmad", "agendad", "marcad"]) and horario in resposta_formatada

            if pediu_dados or confirmou:
                # Remove o horário ocupado da sessão para não insistir
                if "horario" in dados_sessao_paciente[session_id]:
                    del dados_sessao_paciente[session_id]["horario"]

                resposta_formatada = (
                    f"Olá! Consultei a nossa agenda e o horário das **{horario}** no dia **{data_br}** com o **{medico}** "
                    f"já está alocado para outro paciente.\n\n"
                    f"Para melhor atendê-lo(a), os horários disponíveis para o **{medico}** nesta data são:\n"
                    f"🕒 **{txt_livres}**\n\n"
                    f"Qual desses horários você prefere?"
                )

        # 4. Sincroniza cancelamento primeiro (caso seja solicitação de cancelamento)
        msg_canc = tentar_sincronizar_cancelamento(session_id, mensagem_usuario, resposta_formatada)
        if msg_canc:
            resposta_formatada += f"\n\n{msg_canc}"
        else:
            # 5. Só tenta sincronizar novo agendamento se NÃO for cancelamento e NÃO houver conflito de horário ocupado
            if not (restricao and restricao["status"] in ["ocupado", "passado"]):
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
    respeitando estritamente a alocação e bloqueio de horários já preenchidos.
    """
    if session_id not in dados_sessao_paciente:
        dados_sessao_paciente[session_id] = {}

    dados = dados_sessao_paciente[session_id]
    texto_total = f"{msg_usuario}\n{resposta_agente}"

    # Enriquece os dados com tudo que foi dito
    dados.update(extrair_dados_parciais(texto_total, dados))

    # Nome do Paciente (com filtro anti-obrigado)
    m_nome_user = re.search(r'(?:meu nome [eé]|me chamo|nome:\s*|sou o|sou a)\s*([A-Za-zÀ-ÖØ-öø-ÿ\s]{3,35})', msg_usuario, re.IGNORECASE)
    if m_nome_user:
        nome_c = m_nome_user.group(1).split(',')[0].strip().title()
        if nome_c.lower() not in PALAVRAS_INVALIDAS_NOME:
            dados["nome_paciente"] = nome_c
    elif "nome_paciente" not in dados or dados["nome_paciente"].lower() in PALAVRAS_INVALIDAS_NOME:
        m_nome_agente = re.search(r'(?:Perfeito|Ol[aá]|Claro|Certo),?\s*([A-Za-zÀ-ÖØ-öø-ÿ\s]{3,35})[.,!]', resposta_agente, re.IGNORECASE)
        if m_nome_agente:
            nome_c = m_nome_agente.group(1).strip().title()
            if nome_c.lower() not in PALAVRAS_INVALIDAS_NOME:
                dados["nome_paciente"] = nome_c

    # Indicador de Confirmação pelo Agente
    confirmado = bool(re.search(
        r'(?:foi agendada|agendada para o dia|agendamento.*ficou|consulta.*confirmada|confirmad[oa]|recebi seus dados|agendamento.*encaminhado)',
        resposta_agente,
        re.IGNORECASE
    ))

    # Gravação / Atualização no banco SQLite respeitando alocação
    if "medico" in dados and "data" in dados and "horario" in dados:
        nome = dados.get("nome_paciente", "Paciente Agendado")
        if nome.lower() in PALAVRAS_INVALIDAS_NOME:
            nome = "Paciente Agendado"

        cpf = dados.get("cpf", "000.000.000-00")
        data_nasc = dados.get("data_nascimento", "Não informada")
        medico = dados["medico"]
        data_c = dados["data"]
        horario_c = dados["horario"]
        sessao_cid = dados.get("consulta_id")

        if sessao_cid is None:
            if confirmado or (nome != "Paciente Agendado" and cpf != "000.000.000-00"):
                consulta_id, msg = database.criar_consulta(
                    nome, cpf, data_nasc, medico, data_c, horario_c, session_consulta_id=sessao_cid
                )
                if consulta_id:
                    dados["consulta_id"] = consulta_id
                    partes = data_c.split('-')
                    data_br = f"{partes[2]}/{partes[1]}/{partes[0]}"
                    print(f"[SQLite] SUCESSO: Consulta #{consulta_id} gravada no banco para {medico} em {data_c} às {horario_c} ({nome})")
                    return f"✅ *[Sistema Senai Tech: Consulta #{consulta_id} registrada com sucesso no banco de dados para o {medico} em {data_br} às {horario_c}. Paciente: {nome}]*"
                else:
                    print(f"[SQLite Bloqueio]: Não foi possível criar consulta: {msg}")
        else:
            # Se já pertence à sessão, atualiza os dados cadastrais
            database.atualizar_dados_consulta(sessao_cid, nome, cpf, data_nasc)
            print(f"[SQLite] Consulta #{sessao_cid} atualizada com dados do paciente: {nome}, CPF: {cpf}, Nasc: {data_nasc}")

    return None
