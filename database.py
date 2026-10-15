import sqlite3
import os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), 'clinica.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_paciente TEXT NOT NULL,
                cpf TEXT NOT NULL,
                data_nascimento TEXT NOT NULL,
                medico TEXT NOT NULL,
                data TEXT NOT NULL,
                horario TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Agendada',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    seed_sample_data()

def seed_sample_data():
    """Insere alguns agendamentos de exemplo caso o banco esteja vazio."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as total FROM consultas')
        total = cursor.fetchone()['total']
        if total == 0:
            hoje = date.today().strftime('%Y-%m-%d')
            amostras = [
                ('Carlos Eduardo Silva', '123.456.789-00', '1985-04-12', 'Dr. Clark', hoje, '09:00', 'Agendada'),
                ('Maria Aparecida Santos', '234.567.890-11', '1972-11-23', 'Dr. Clark', hoje, '10:00', 'Agendada'),
                ('João Pedro Fernandes', '345.678.901-22', '1990-07-08', 'Dr. Clark', hoje, '14:00', 'Realizada'),
                ('Ana Paula Guimarães', '456.789.012-33', '1988-02-17', 'Dr. Jorge', hoje, '09:00', 'Agendada'),
                ('Roberto Carlos Menezes', '567.890.123-44', '1965-09-30', 'Dr. Jorge', hoje, '11:00', 'Agendada'),
                ('Beatriz Vasconcelos', '678.901.234-55', '1995-12-05', 'Dr. Jorge', hoje, '15:00', 'Cancelada'),
            ]
            cursor.executemany('''
                INSERT INTO consultas (nome_paciente, cpf, data_nascimento, medico, data, horario, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', amostras)
            conn.commit()

HORARIOS_EXPEDIENTE = [
    "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"
]

def obter_consulta_no_horario(medico, data_str, horario):
    """
    Retorna a consulta ativa no médico, data e horário especificados, ou None se vago.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, nome_paciente, cpf, data_nascimento, medico, data, horario, status
            FROM consultas 
            WHERE medico = ? AND data = ? AND horario = ? AND status != 'Cancelada'
        ''', (medico, data_str, horario))
        row = cursor.fetchone()
        return dict(row) if row else None

def obter_horarios_disponiveis(medico, data_str):
    """
    Retorna a lista de horários livres no expediente para o médico na data informada.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT horario FROM consultas 
            WHERE medico = ? AND data = ? AND status != 'Cancelada'
        ''', (medico, data_str))
        ocupados = {row['horario'] for row in cursor.fetchall()}

    livres = [h for h in HORARIOS_EXPEDIENTE if h not in ocupados]
    return livres

def verificar_disponibilidade(medico, data_str, horario):
    """
    Verifica se o médico tem vaga no horário e data solicitados.
    Retorna True se estiver livre, False se já ocupado.
    """
    consulta = obter_consulta_no_horario(medico, data_str, horario)
    return consulta is None

def criar_consulta(nome_paciente, cpf, data_nascimento, medico, data_str, horario, session_consulta_id=None):
    """
    Cria uma nova consulta no sistema respeitando a regra de negócio:
    - Se o horário já estiver alocado para outro paciente, BLOQUEIA o agendamento.
    - Só permite atualização se o registro já pertencer à mesma sessão do paciente.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, nome_paciente, cpf FROM consultas 
            WHERE medico = ? AND data = ? AND horario = ? AND status != 'Cancelada'
        ''', (medico, data_str, horario))
        row = cursor.fetchone()

        if row:
            c_id = row['id']
            # Se for a consulta pertencente à própria sessão do usuário em andamento, atualiza
            if session_consulta_id and session_consulta_id == c_id:
                atualizar_dados_consulta(c_id, nome_paciente, cpf, data_nascimento)
                return c_id, "Consulta atualizada com sucesso!"
            else:
                # REGRA DE NEGÓCIO: Horário já alocado para outro paciente!
                print(f"[Database Bloqueio] Conflito de horário! Dr. {medico} em {data_str} {horario} já pertence à consulta #{c_id} ({row['nome_paciente']}).")
                return None, f"O horário {horario} do dia {data_str} com o {medico} já está alocado para outro paciente."

        # Se o horário está vago, insere novo registro
        cursor.execute('''
            INSERT INTO consultas (nome_paciente, cpf, data_nascimento, medico, data, horario, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Agendada')
        ''', (nome_paciente, cpf, data_nascimento, medico, data_str, horario))
        conn.commit()
        consulta_id = cursor.lastrowid
        return consulta_id, "Consulta agendada com sucesso!"

def atualizar_dados_consulta(consulta_id, nome_paciente=None, cpf=None, data_nascimento=None):
    """Atualiza dados cadastrais de uma consulta já criada."""
    campos = []
    valores = []
    if nome_paciente and nome_paciente != 'Paciente Agendado':
        campos.append("nome_paciente = ?")
        valores.append(nome_paciente)
    if cpf and cpf != '000.000.000-00':
        campos.append("cpf = ?")
        valores.append(cpf)
    if data_nascimento and data_nascimento != 'Não informada':
        campos.append("data_nascimento = ?")
        valores.append(data_nascimento)

    if not campos:
        return False

    valores.append(consulta_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE consultas SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()
        return cursor.rowcount > 0

def listar_consultas(medico=None, data_str=None, status=None):
    """Retorna consultas filtradas por médico, data e/ou status."""
    query = 'SELECT * FROM consultas WHERE 1=1'
    params = []

    if medico:
        query += ' AND medico = ?'
        params.append(medico)
    if data_str:
        query += ' AND data = ?'
        params.append(data_str)
    if status and status != 'Todas':
        query += ' AND status = ?'
        params.append(status)

    query += ' ORDER BY data ASC, horario ASC'

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def buscar_consultas_por_cpf(cpf):
    """Retorna consultas ativas vinculadas ao CPF."""
    cpf_limpo = ''.join(filter(str.isdigit, cpf))
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM consultas 
            WHERE (cpf = ? OR REPLACE(REPLACE(cpf, '.', ''), '-', '') = ?)
              AND status = 'Agendada'
            ORDER BY data ASC, horario ASC
        ''', (cpf, cpf_limpo))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def cancelar_consulta_por_id(consulta_id):
    """Cancela uma consulta específica pelo ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE consultas 
            SET status = 'Cancelada' 
            WHERE id = ? AND status = 'Agendada'
        ''', (consulta_id,))
        conn.commit()
        return cursor.rowcount > 0

def atualizar_status_consulta(consulta_id, novo_status):
    """Atualiza o status de uma consulta (ex: Realizada, Cancelada, Agendada)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE consultas 
            SET status = ? 
            WHERE id = ?
        ''', (novo_status, consulta_id))
        conn.commit()
        return cursor.rowcount > 0

def obter_horarios_disponiveis(medico, data_str):
    """Retorna a lista de horários do expediente (09:00 às 17:00) livres para o médico."""
    todos_horarios = [
        "09:00", "10:00", "11:00", "12:00",
        "13:00", "14:00", "15:00", "16:00", "17:00"
    ]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT horario FROM consultas 
            WHERE medico = ? AND data = ? AND status != 'Cancelada'
        ''', (medico, data_str))
        ocupados = {row['horario'] for row in cursor.fetchall()}
    
    return [h for h in todos_horarios if h not in ocupados]
