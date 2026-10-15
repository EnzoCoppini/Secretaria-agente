/**
 * chat.js - Interface Conversacional com o Agente de IA da Secretária Anna (Senai Tech)
 */

document.addEventListener('DOMContentLoaded', () => {
  const chatMessages = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const userInput = document.getElementById('userInput');
  const typingIndicator = document.getElementById('typingIndicator');
  const btnRestart = document.getElementById('btnRestart');
  const welcomeTime = document.getElementById('welcomeTime');

  // Gerenciamento de Session ID único para o paciente
  let sessionId = localStorage.getItem('senai_chat_session_id');
  if (!sessionId) {
    sessionId = 'sess_' + Math.random().toString(36).substring(2, 10);
    localStorage.setItem('senai_chat_session_id', sessionId);
  }

  // Atualiza horário da mensagem de boas-vindas inicial
  if (welcomeTime) {
    welcomeTime.textContent = obterHoraAtual();
  }

  // ========================================================================
  // Event Listeners
  // ========================================================================

  // Envio de mensagem pelo formulário
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const texto = userInput.value.trim();
    if (!texto) return;

    enviarMensagem(texto);
    userInput.value = '';
    userInput.focus();
  });

  // Botão de Reiniciar / Limpar histórico de conversa
  btnRestart.addEventListener('click', async () => {
    if (confirm('Deseja reiniciar a conversa e limpar o histórico com a Anna?')) {
      try {
        await fetch('/api/chat/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId })
        });
      } catch (e) {
        console.warn('Erro ao resetar histórico no backend:', e);
      }
      
      // Gera novo ID de sessão e recarrega
      localStorage.setItem('senai_chat_session_id', 'sess_' + Math.random().toString(36).substring(2, 10));
      window.location.reload();
    }
  });

  // Clique nos botões de Prompts Rápidos (Chips)
  document.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip-btn');
    if (chip) {
      const acao = chip.getAttribute('data-action');
      if (acao) {
        enviarMensagem(acao);
      }
    }
  });

  // ========================================================================
  // Funções Principais de Mensagem
  // ========================================================================

  async function enviarMensagem(mensagemTexto) {
    // 1. Renderiza a mensagem enviada pelo paciente
    renderizarMensagemUsuario(mensagemTexto);
    rolarParaFinal();

    // 2. Exibe o indicador de processamento do Agente de IA
    mostrarDigitando(true);
    rolarParaFinal();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: mensagemTexto,
          session_id: sessionId
        })
      });

      if (!response.ok) {
        throw new Error('Falha na comunicação com o servidor.');
      }

      const data = await response.json();
      
      mostrarDigitando(false);
      renderizarMensagemAnna(data.response);
      rolarParaFinal();

    } catch (err) {
      console.error('Erro ao enviar mensagem:', err);
      mostrarDigitando(false);
      renderizarMensagemAnna('⚠️ Desculpe, tive uma instabilidade momentânea na conexão com o servidor. Poderia tentar novamente?');
      rolarParaFinal();
    }
  }

  function renderizarMensagemUsuario(texto) {
    const row = document.createElement('div');
    row.className = 'message-row user-row';

    row.innerHTML = `
      <div class="message-bubble user-bubble">
        <div class="message-text">${escaparHTML(texto)}</div>
        <div class="message-meta">
          <span class="msg-time">${obterHoraAtual()}</span>
          <span class="msg-ticks" title="Mensagem enviada"><i class="fa-solid fa-check-double"></i></span>
        </div>
      </div>
    `;

    chatMessages.insertBefore(row, typingIndicator);
  }

  function renderizarMensagemAnna(textoMarkdown) {
    const row = document.createElement('div');
    row.className = 'message-row bot-row';

    // Formata o texto Markdown retornado pelo modelo de IA
    const textoFormatado = formatarMarkdown(textoMarkdown);

    row.innerHTML = `
      <div class="message-bubble bot-bubble">
        <div class="message-sender">Anna • Secretária Virtual</div>
        <div class="message-text">${textoFormatado}</div>
        <div class="message-meta">
          <span class="msg-time">${obterHoraAtual()}</span>
        </div>
      </div>
    `;

    chatMessages.insertBefore(row, typingIndicator);
  }

  function mostrarDigitando(visivel) {
    typingIndicator.style.display = visivel ? 'flex' : 'none';
  }

  function rolarParaFinal() {
    chatMessages.scrollTo({
      top: chatMessages.scrollHeight,
      behavior: 'smooth'
    });
  }

  // ========================================================================
  // Utilitários de Formatação
  // ========================================================================

  function obterHoraAtual() {
    const agora = new Date();
    const horas = String(agora.getHours()).padStart(2, '0');
    const minutos = String(agora.getMinutes()).padStart(2, '0');
    return `${horas}:${minutos}`;
  }

  function escaparHTML(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatarMarkdown(texto) {
    if (!texto) return '';

    let res = escaparHTML(texto);

    // Formata negrito: **texto** -> <strong>texto</strong>
    res = res.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Formata itálico: _texto_ ou *texto* -> <em>texto</em>
    res = res.replace(/_(.*?)_/g, '<em>$1</em>');
    res = res.replace(/\*([^\*]+)\*/g, '<em>$1</em>');

    // Formata código inline: `texto` -> <code>texto</code>
    res = res.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Quebras de linha para <br>
    res = res.replace(/\n/g, '<br>');

    return res;
  }
});
