(() => {
  const style = document.createElement('style');
  style.textContent = `
    .bellamy-status{position:fixed;z-index:30;right:18px;bottom:92px;display:flex;align-items:center;gap:9px;max-width:min(420px,calc(100% - 36px));padding:10px 14px;border-radius:999px;background:#fff;color:#192233;border:1px solid #dce1e8;box-shadow:0 8px 24px rgba(20,33,61,.14);font-size:.92rem;font-weight:750;transition:.2s ease}
    .bellamy-status.hidden{display:none}.bellamy-status .dot{width:10px;height:10px;border-radius:50%;background:#98a2b3;flex:0 0 auto}.bellamy-status.listening .dot{background:#2563eb;animation:bellamyPulse 1s infinite}.bellamy-status.processing .dot{background:#c05621;animation:bellamyPulse .7s infinite}.bellamy-status.done .dot{background:#2f855a}.bellamy-status.error .dot{background:#b42318}.bellamy-status.offline .dot{background:#98a2b3}.bellamy-status small{font-weight:600;color:#667085;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    @keyframes bellamyPulse{50%{transform:scale(1.55);opacity:.55}}
    @media(max-width:650px){.bellamy-status{right:10px;bottom:82px;max-width:calc(100% - 20px)}}
  `;
  document.head.appendChild(style);

  const pill = document.createElement('div');
  pill.className = 'bellamy-status hidden';
  pill.setAttribute('role', 'status');
  pill.setAttribute('aria-live', 'polite');
  pill.innerHTML = '<span class="dot"></span><span>Bellamy</span><small></small>';
  document.body.appendChild(pill);
  const detail = pill.querySelector('small');
  let lastKey = '';

  async function refresh() {
    try {
      const response = await fetch(`/static/voice-status.json?t=${Date.now()}`, {cache: 'no-store'});
      if (!response.ok) { pill.classList.add('hidden'); return; }
      const data = await response.json();
      const key = `${data.state}|${data.text}`;
      if (key === lastKey) return;
      lastKey = key;
      pill.className = `bellamy-status ${data.state || 'idle'}`;
      const labels = {idle:'Ready',listening:'Listening',processing:'Processing',done:'Done',error:'Problem',offline:'Offline'};
      pill.childNodes[1].textContent = `Bellamy · ${labels[data.state] || 'Ready'}`;
      detail.textContent = data.text || '';
    } catch (_) {
      pill.classList.add('hidden');
    }
  }

  refresh();
  setInterval(refresh, 1000);
})();
