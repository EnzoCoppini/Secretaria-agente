/**
 * admin.js - Controle de Autenticação e Dashboard Médico (Dr. Clark e Dr. Jorge)
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elementos de Autenticação
  const loginWrapper = document.getElementById('loginWrapper');
  const dashboardWrapper = document.getElementById('dashboardWrapper');
  const loginForm = document.getElementById('loginForm');
  const selectMedico = document.getElementById('selectMedico');
  const inputSenha = document.getElementById('inputSenha');
  const loginError = document.getElementById('loginError');
  const loginErrorMsg = document.getElementById('loginErrorMsg');
  const btnTogglePass = document.getElementById('btnTogglePass');
  const btnLogout = document.getElementById('btnLogout');
  const medicoNomeDisplay = document.getElementById('medicoNomeDisplay');
  const dataExtensoDisplay = document.getElementById('dataExtensoDisplay');

  // Elementos do Dashboard
  const filtroData = document.getElementById('filtroData');
  const filtroStatus = document.getElementById('filtroStatus');
  const btnFiltroHoje = document.getElementById('btnFiltroHoje');
  const btnFiltroAmanha = document.getElementById('btnFiltroAmanha');
  const btnFiltroTodas = document.getElementById('btnFiltroTodas');
  const btnAtualizar = document.getElementById('btnAtualizar');
  const consultasTableBody = document.getElementById('consultasTableBody');
  const emptyState = document.getElementById('emptyState');

  // Elementos de Métricas
  const statTotal = document.getElementById('statTotal');
  const statAgendadas = document.getElementById('statAgendadas');
  const statRealizadas = document.getElementById('statRealizadas');
  const statCanceladas = document.getElementById('statCanceladas');

  let medicoAtual = null;

  // Por padrão, exibimos TODAS as consultas do médico para que nenhum agendamento fique oculto
  const hojeISO = obterDataISO(new Date());
  filtroData.value = '';
  desmarcarBotoesTags();
  btnFiltroTodas.classList.add('active');
  atualizarDataExtenso();

  // 1. Checa autenticação inicial
  verificarSessao();

  // ========================================================================
  // Event Listeners - Autenticação
  // ========================================================================

  btnTogglePass.addEventListener('click', () => {
    const tipo = inputSenha.getAttribute('type') === 'password' ? 'text' : 'password';
    inputSenha.setAttribute('type', tipo);
    btnTogglePass.innerHTML = tipo === 'password' 
      ? '<i class="fa-regular fa-eye"></i>' 
      : '<i class="fa-regular fa-eye-slash"></i>';
  });

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.style.display = 'none';

    const medico = selectMedico.value;
    const senha = inputSenha.value;

    try {
      const resp = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ medico, senha })
      });

      const data = await resp.json();

      if (resp.ok && data.success) {
        medicoAtual = data.medico;
        exibirDashboard();
        mostrarToast(`Bem-vindo, ${medicoAtual}!`);
      } else {
        loginErrorMsg.textContent = data.message || 'Credenciais inválidas.';
        loginError.style.display = 'flex';
      }
    } catch (err) {
      console.error(err);
      loginErrorMsg.textContent = 'Erro ao conectar ao servidor.';
      loginError.style.display = 'flex';
    }
  });

  btnLogout.addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    medicoAtual = null;
    dashboardWrapper.style.display = 'none';
    loginWrapper.style.display = 'flex';
    inputSenha.value = '';
    mostrarToast('Sessão encerrada com sucesso.');
  });

  // ========================================================================
  // Event Listeners - Filtros da Tabela
  // ========================================================================

  filtroData.addEventListener('change', () => {
    desmarcarBotoesTags();
    if (filtroData.value === hojeISO) {
      btnFiltroHoje.classList.add('active');
    }
    carregarConsultas();
  });

  btnFiltroHoje.addEventListener('click', () => {
    desmarcarBotoesTags();
    btnFiltroHoje.classList.add('active');
    filtroData.value = hojeISO;
    carregarConsultas();
  });

  btnFiltroAmanha.addEventListener('click', () => {
    desmarcarBotoesTags();
    btnFiltroAmanha.classList.add('active');
    const amanha = new Date();
    amanha.setDate(amanha.getDate() + 1);
    filtroData.value = obterDataISO(amanha);
    carregarConsultas();
  });

  btnFiltroTodas.addEventListener('click', () => {
    desmarcarBotoesTags();
    btnFiltroTodas.classList.add('active');
    filtroData.value = '';
    carregarConsultas();
  });

  filtroStatus.addEventListener('change', () => {
    carregarConsultas();
  });

  btnAtualizar.addEventListener('click', () => {
    carregarConsultas();
    mostrarToast('Agenda atualizada.');
  });

  function desmarcarBotoesTags() {
    btnFiltroHoje.classList.remove('active');
    btnFiltroAmanha.classList.remove('active');
    btnFiltroTodas.classList.remove('active');
  }

  // ========================================================================
  // Comunicação com a API e Renderização
  // ========================================================================

  async function verificarSessao() {
    try {
      const resp = await fetch('/api/me');
      const data = await resp.json();
      if (data.authenticated && data.medico) {
        medicoAtual = data.medico;
        exibirDashboard();
      }
    } catch (err) {
      console.warn('Sessão não ativa');
    }
  }

  function exibirDashboard() {
    loginWrapper.style.display = 'none';
    dashboardWrapper.style.display = 'flex';
    medicoNomeDisplay.textContent = medicoAtual;
    carregarConsultas();
  }

  async function carregarConsultas() {
    if (!medicoAtual) return;

    const dataEscolhida = filtroData.value;
    const statusEscolhido = filtroStatus.value;

    let url = `/api/consultas?medico=${encodeURIComponent(medicoAtual)}`;
    if (dataEscolhida) url += `&data=${encodeURIComponent(dataEscolhida)}`;
    if (statusEscolhido && statusEscolhido !== 'Todas') url += `&status=${encodeURIComponent(statusEscolhido)}`;

    try {
      // 1. Busca consultas filtradas para a tabela
      const resp = await fetch(url);
      if (!resp.ok) throw new Error('Erro ao listar consultas');

      const data = await resp.json();
      const consultas = data.consultas || [];

      // 2. Busca o resumo global do médico para atualizar as métricas sem viés de filtro de data
      await atualizarMetricasGlobais(medicoAtual);

      renderizarTabela(consultas, dataEscolhida);
    } catch (err) {
      console.error(err);
      mostrarToast('Falha ao carregar as consultas.', true);
    }
  }

  async function atualizarMetricasGlobais(medico) {
    try {
      const resp = await fetch(`/api/consultas?medico=${encodeURIComponent(medico)}`);
      if (resp.ok) {
        const data = await resp.json();
        const todas = data.consultas || [];
        statTotal.textContent = todas.length;
        statAgendadas.textContent = todas.filter(c => c.status === 'Agendada').length;
        statRealizadas.textContent = todas.filter(c => c.status === 'Realizada').length;
        statCanceladas.textContent = todas.filter(c => c.status === 'Cancelada').length;
      }
    } catch (e) {
      console.warn('Erro ao calcular métricas globais:', e);
    }
  }

  function renderizarTabela(consultas, dataFiltro) {
    consultasTableBody.innerHTML = '';

    if (consultas.length === 0) {
      emptyState.style.display = 'block';
      if (dataFiltro) {
        emptyState.innerHTML = `
          <div class="empty-icon"><i class="fa-regular fa-calendar-check"></i></div>
          <h3>Nenhuma consulta encontrada para a data selecionada</h3>
          <p>Não há consultas marcadas para este dia específico.</p>
          <button class="btn-tag active" style="margin-top: 14px; padding: 8px 18px;" id="btnVerTodasVazio">
            <i class="fa-solid fa-list-ul"></i> Ver Todas as Datas Agendadas
          </button>
        `;
        document.getElementById('btnVerTodasVazio')?.addEventListener('click', () => {
          btnFiltroTodas.click();
        });
      } else {
        emptyState.innerHTML = `
          <div class="empty-icon"><i class="fa-regular fa-calendar-check"></i></div>
          <h3>Nenhuma consulta agendada</h3>
          <p>Quando os pacientes marcarem uma consulta pelo chat com a Anna, elas aparecerão aqui automaticamente.</p>
        `;
      }
      return;
    }

    emptyState.style.display = 'none';

    consultas.forEach(c => {
      const tr = document.createElement('tr');

      const partesData = c.data.split('-');
      const dataFormatada = partesData.length === 3 ? `${partesData[2]}/${partesData[1]}/${partesData[0]}` : c.data;

      // Destaca se for hoje
      const isHoje = c.data === hojeISO;
      const badgeData = isHoje ? '<span class="status-badge" style="background:#e0f2fe; color:#0284c7; font-size:0.7rem; margin-left:6px;">Hoje</span>' : '';

      tr.innerHTML = `
        <td><span class="time-badge">${c.horario}</span></td>
        <td>
          <span class="paciente-nome">${escapar(c.nome_paciente)}</span>
          <br><small style="color:#64748b; font-size:0.75rem;">ID #${c.id}</small>
        </td>
        <td><code>${escapar(c.cpf)}</code></td>
        <td>${escapar(c.data_nascimento)}</td>
        <td><strong>${dataFormatada}</strong>${badgeData}</td>
        <td>
          <span class="status-badge ${c.status}">
            <span class="status-dot-sm"></span>
            ${c.status}
          </span>
        </td>
        <td class="text-right">
          <div class="actions-cell">
            ${c.status === 'Agendada' ? `
              <button class="btn-action btn-action-realizada" data-id="${c.id}" data-action="Realizada" title="Marcar como realizada">
                <i class="fa-solid fa-check"></i> Concluir
              </button>
              <button class="btn-action btn-action-cancelar" data-id="${c.id}" data-action="Cancelada" title="Cancelar consulta">
                <i class="fa-solid fa-xmark"></i> Cancelar
              </button>
            ` : `
              <span style="font-size: 0.8rem; color: #94a3b8;">${c.status}</span>
            `}
          </div>
        </td>
      `;

      consultasTableBody.appendChild(tr);
    });

    // Anexa ações dos botões
    document.querySelectorAll('.btn-action').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        const novoStatus = btn.getAttribute('data-action');
        await alterarStatusConsulta(id, novoStatus);
      });
    });
  }

  async function alterarStatusConsulta(id, novoStatus) {
    try {
      const resp = await fetch(`/api/consultas/${id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: novoStatus })
      });

      const res = await resp.json();
      if (resp.ok && res.success) {
        mostrarToast(`Consulta #${id} marcada como '${novoStatus}'.`);
        carregarConsultas();
      } else {
        mostrarToast(res.error || 'Erro ao alterar status', true);
      }
    } catch (err) {
      console.error(err);
      mostrarToast('Erro ao atualizar status', true);
    }
  }

  // ========================================================================
  // Utilitários
  // ========================================================================

  function obterDataISO(d) {
    const ano = d.getFullYear();
    const mes = String(d.getMonth() + 1).padStart(2, '0');
    const dia = String(d.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
  }

  function atualizarDataExtenso() {
    const hoje = new Date();
    const opcoes = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    const formatado = hoje.toLocaleDateString('pt-BR', opcoes);
    dataExtensoDisplay.textContent = formatado.charAt(0).toUpperCase() + formatado.slice(1);
  }

  function escapar(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function mostrarToast(mensagem, isError = false) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
      <i class="fa-solid ${isError ? 'fa-circle-xmark' : 'fa-circle-check'}" style="color: ${isError ? '#f87171' : '#4ade80'}"></i>
      <span>${mensagem}</span>
    `;

    document.getElementById('toastContainer').appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }
});
