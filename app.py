from flask import Flask, render_template, request, jsonify, session
import secrets
from datetime import date

# Carrega variáveis do arquivo .env automaticamente (nunca subir o .env no GitHub)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv opcional; use variáveis de ambiente do sistema se não instalado

import database
import chatbot_anna

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Inicializa o banco de dados e dados de exemplo ao iniciar a aplicação
database.init_db()

# Médicos autorizados e senha fixa
MEDICOS_CREDENCIAIS = {
    "Dr. Clark": "1234",
    "Dr. Jorge": "1234"
}

# ============================================================================
# ROTAS DE PÁGINAS (FRONT-END)
# ============================================================================

@app.route("/")
def index():
    """Página principal de Atendimento ao Paciente (Chatbot estilo WhatsApp)."""
    return render_template("index.html")

@app.route("/admin")
def admin():
    """Página do Portal do Administrador / Painel dos Médicos."""
    return render_template("admin.html")

# ============================================================================
# ENDPOINTS DO CHAT E AGENTE DE IA
# ============================================================================

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Recebe as mensagens do chat e delega 100% para o Agente de IA da Secretária Anna.
    """
    dados = request.get_json() or {}
    mensagem = dados.get("message", "").strip()
    session_id = dados.get("session_id") or secrets.token_hex(8)

    if not mensagem:
        return jsonify({"error": "Mensagem não pode estar vazia"}), 400

    # Direciona a mensagem para o agente de IA
    resposta_ia = chatbot_anna.processar_mensagem_agente(session_id, mensagem)

    return jsonify({
        "response": resposta_ia,
        "session_id": session_id
    })

@app.route("/api/chat/reset", methods=["POST"])
def api_chat_reset():
    """Limpa o histórico de conversa da sessão atual."""
    dados = request.get_json() or {}
    session_id = dados.get("session_id")
    if session_id:
        chatbot_anna.resetar_historico(session_id)
    return jsonify({"success": True})

# ============================================================================
# ENDPOINTS DE FERRAMENTAS / TOOLS (Para uso de Agentes Externos via REST API)
# ============================================================================

@app.route("/api/tools/disponibilidade", methods=["POST"])
def api_tool_disponibilidade():
    """Endpoint para agentes de IA consultarem horários disponíveis."""
    dados = request.get_json() or {}
    medico = dados.get("medico")
    data_str = dados.get("data")
    resultado = chatbot_anna.tool_consultar_disponibilidade(medico, data_str)
    return jsonify(resultado)

@app.route("/api/tools/agendar", methods=["POST"])
def api_tool_agendar():
    """Endpoint para agentes de IA realizarem o agendamento no banco SQLite."""
    dados = request.get_json() or {}
    resultado = chatbot_anna.tool_agendar_consulta(
        nome_paciente=dados.get("nome_paciente"),
        cpf=dados.get("cpf"),
        data_nascimento=dados.get("data_nascimento"),
        medico=dados.get("medico"),
        data=dados.get("data"),
        horario=dados.get("horario")
    )
    return jsonify(resultado)

@app.route("/api/tools/consultas-cpf", methods=["POST"])
def api_tool_buscar_cpf():
    """Endpoint para agentes de IA buscarem agendamentos por CPF."""
    dados = request.get_json() or {}
    cpf = dados.get("cpf")
    resultado = chatbot_anna.tool_buscar_consultas_cpf(cpf)
    return jsonify(resultado)

@app.route("/api/tools/cancelar", methods=["POST"])
def api_tool_cancelar():
    """Endpoint para agentes de IA cancelarem uma consulta médica."""
    dados = request.get_json() or {}
    consulta_id = dados.get("consulta_id")
    resultado = chatbot_anna.tool_cancelar_consulta(consulta_id)
    return jsonify(resultado)

# ============================================================================
# AUTENTICAÇÃO E PAINEL DOS MÉDICOS
# ============================================================================

@app.route("/api/login", methods=["POST"])
def api_login():
    """Autenticação simples dos médicos Dr. Clark e Dr. Jorge com senha fixa 1234."""
    dados = request.get_json() or {}
    medico = dados.get("medico", "").strip()
    senha = dados.get("senha", "").strip()

    if medico in MEDICOS_CREDENCIAIS and MEDICOS_CREDENCIAIS[medico] == senha:
        session["medico"] = medico
        return jsonify({
            "success": True,
            "medico": medico,
            "message": f"Bem-vindo(a), {medico}!"
        })

    return jsonify({
        "success": False,
        "message": "Médico ou senha inválidos. Verifique as credenciais."
    }), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Encerra a sessão do médico."""
    session.pop("medico", None)
    return jsonify({"success": True})

@app.route("/api/me", methods=["GET"])
def api_me():
    """Verifica se há um médico autenticado na sessão."""
    medico = session.get("medico")
    if medico:
        return jsonify({"authenticated": True, "medico": medico})
    return jsonify({"authenticated": False})

@app.route("/api/consultas", methods=["GET"])
def api_consultas():
    """
    Lista as consultas do médico logado.
    Permite filtrar por data e status.
    """
    medico_logado = session.get("medico")
    medico = medico_logado or request.args.get("medico")

    if not medico:
        return jsonify({"error": "Acesso não autorizado. Faça login primeiro."}), 401

    data_filtro = request.args.get("data")
    status_filtro = request.args.get("status")

    consultas = database.listar_consultas(
        medico=medico,
        data_str=data_filtro if data_filtro else None,
        status=status_filtro if status_filtro else None
    )

    return jsonify({
        "medico": medico,
        "total": len(consultas),
        "consultas": consultas
    })

@app.route("/api/consultas/<int:consulta_id>/status", methods=["PATCH"])
def api_atualizar_status(consulta_id):
    """Atualiza o status de uma consulta pelo médico (ex: Realizada ou Cancelada)."""
    if "medico" not in session:
        return jsonify({"error": "Acesso não autorizado."}), 401

    dados = request.get_json() or {}
    novo_status = dados.get("status")

    if novo_status not in ["Agendada", "Realizada", "Cancelada"]:
        return jsonify({"error": "Status inválido."}), 400

    sucesso = database.atualizar_status_consulta(consulta_id, novo_status)
    if sucesso:
        return jsonify({"success": True, "message": f"Consulta #{consulta_id} marcada como '{novo_status}'."})
    return jsonify({"error": "Consulta não encontrada."}), 404

if __name__ == "__main__":
    print("=" * 60)
    print("🏥 Senai Tech - Sistema de Atendimento com Agente de IA")
    print("📍 Chatbot Anna: http://127.0.0.1:5000/")
    print("📍 Painel dos Médicos: http://127.0.0.1:5000/admin")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=5000)
