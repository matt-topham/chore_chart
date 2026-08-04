const state = {
  data: null,
  area: 'All',
  lastCompletionId: null,
  toastTimer: null,
};

const els = {
  dueList: document.getElementById('due-list'),
  upcomingList: document.getElementById('upcoming-list'),
  completedList: document.getElementById('completed-list'),
  dueCount: document.getElementById('due-count'),
  upcomingCount: document.getElementById('upcoming-count'),
  completedCount: document.getElementById('completed-count'),
  filters: document.getElementById('area-filters'),
  allDone: document.getElementById('all-done'),
  progressLabel: document.getElementById('progress-label'),
  progressPercent: document.getElementById('progress-percent'),
  progressBar: document.getElementById('progress-bar'),
  todayTitle: document.getElementById('today-title'),
  clock: document.getElementById('clock'),
  toast: document.getElementById('toast'),
  toastText: document.getElementById('toast-text'),
  undoButton: document.getElementById('undo-button'),
  refreshButton: document.getElementById('refresh-button'),
};

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

function formatDueDate(value) {
  const date = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short', month: 'short', day: 'numeric'
  }).format(date);
}

function visible(items) {
  return state.area === 'All' ? items : items.filter(item => item.area === state.area);
}

function choreCard(item, mode = 'due') {
  const overdue = item.days_overdue > 0;
  const badge = overdue
    ? `<span class="status-badge overdue">${item.days_overdue} day${item.days_overdue === 1 ? '' : 's'} overdue</span>`
    : mode === 'upcoming'
      ? `<span class="status-badge upcoming">${formatDueDate(item.next_due)}</span>`
      : `<span class="status-badge today">Due today</span>`;

  const action = mode === 'due'
    ? `<button class="complete-button" data-chore-id="${item.id}" aria-label="Complete ${escapeHtml(item.task)}">
         <span class="check-circle">✓</span><span>Done</span>
       </button>`
    : '';

  return `
    <article class="chore-card ${mode === 'upcoming' ? 'upcoming-card' : ''}">
      <div class="chore-copy">
        <div class="meta-row">
          <span class="area-pill">${escapeHtml(item.area)}</span>
          ${badge}
        </div>
        <h3>${escapeHtml(item.task)}</h3>
        <p>${escapeHtml(item.frequency)}${item.preferred_day ? ` · ${escapeHtml(item.preferred_day)}` : ''}</p>
        ${item.notes ? `<p class="notes">${escapeHtml(item.notes)}</p>` : ''}
      </div>
      ${action}
    </article>`;
}

function completedCard(item) {
  return `
    <article class="chore-card completed-card">
      <div class="completed-check">✓</div>
      <div class="chore-copy">
        <span class="area-pill">${escapeHtml(item.area)}</span>
        <h3>${escapeHtml(item.task)}</h3>
      </div>
    </article>`;
}

function renderFilters() {
  const allItems = [
    ...state.data.due,
    ...state.data.upcoming,
    ...state.data.completed_today,
  ];
  const areas = ['All', ...new Set(allItems.map(item => item.area).sort())];
  if (!areas.includes(state.area)) state.area = 'All';
  els.filters.innerHTML = areas.map(area => `
    <button class="filter-button ${state.area === area ? 'active' : ''}" data-area="${escapeHtml(area)}">
      ${escapeHtml(area)}
    </button>
  `).join('');
  els.filters.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => {
      state.area = button.dataset.area;
      render();
    });
  });
}

function render() {
  const due = visible(state.data.due);
  const upcoming = visible(state.data.upcoming);
  const completed = visible(state.data.completed_today);

  els.dueList.innerHTML = due.map(item => choreCard(item, 'due')).join('');
  els.upcomingList.innerHTML = upcoming.map(item => choreCard(item, 'upcoming')).join('');
  els.completedList.innerHTML = completed.map(completedCard).join('');
  els.allDone.classList.toggle('hidden', due.length !== 0);

  els.dueCount.textContent = due.length;
  els.upcomingCount.textContent = upcoming.length;
  els.completedCount.textContent = completed.length;

  const totalToday = state.data.counts.due + state.data.counts.completed;
  const completedCount = state.data.counts.completed;
  const percent = totalToday === 0 ? 100 : Math.round((completedCount / totalToday) * 100);
  els.progressLabel.textContent = totalToday === 0
    ? 'Nothing scheduled for today'
    : `${completedCount} of ${totalToday} finished`;
  els.progressPercent.textContent = `${percent}%`;
  els.progressBar.style.width = `${percent}%`;

  renderFilters();
  bindCompleteButtons();
}

function bindCompleteButtons() {
  document.querySelectorAll('.complete-button').forEach(button => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.classList.add('working');
      const choreId = button.dataset.choreId;
      const card = button.closest('.chore-card');
      const taskName = card.querySelector('h3').textContent;
      try {
        const response = await fetch(`/api/chores/${choreId}/complete`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({}),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not complete chore');
        state.lastCompletionId = result.completion_id;
        card.classList.add('leaving');
        showToast(`${taskName} completed`);
        setTimeout(loadChores, 220);
      } catch (error) {
        button.disabled = false;
        button.classList.remove('working');
        showToast(error.message, false);
      }
    });
  });
}

function showToast(message, canUndo = true) {
  clearTimeout(state.toastTimer);
  els.toastText.textContent = message;
  els.undoButton.classList.toggle('hidden', !canUndo || !state.lastCompletionId);
  els.toast.classList.remove('hidden');
  state.toastTimer = setTimeout(() => els.toast.classList.add('hidden'), 6500);
}

async function undoLast() {
  if (!state.lastCompletionId) return;
  const response = await fetch(`/api/completions/${state.lastCompletionId}`, {method: 'DELETE'});
  if (response.ok) {
    state.lastCompletionId = null;
    els.toast.classList.add('hidden');
    await loadChores();
  } else {
    showToast('Could not undo completion', false);
  }
}

async function loadChores() {
  els.refreshButton.classList.add('spinning');
  try {
    const response = await fetch('/api/chores', {cache: 'no-store'});
    if (!response.ok) throw new Error('Could not load chores');
    state.data = await response.json();
    render();
  } catch (error) {
    els.dueList.innerHTML = `
      <div class="empty-state error-state">
        <h3>Could not reach the chore service</h3>
        <p>Check that the Raspberry Pi service is running.</p>
      </div>`;
  } finally {
    els.refreshButton.classList.remove('spinning');
  }
}

function updateClock() {
  const now = new Date();
  els.todayTitle.textContent = new Intl.DateTimeFormat(undefined, {
    weekday: 'long', month: 'long', day: 'numeric'
  }).format(now);
  els.clock.textContent = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric', minute: '2-digit'
  }).format(now);
}

els.undoButton.addEventListener('click', undoLast);
els.refreshButton.addEventListener('click', loadChores);
updateClock();
setInterval(updateClock, 15000);
loadChores();
setInterval(loadChores, 5 * 60 * 1000);
