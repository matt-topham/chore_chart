const $ = (id) => document.getElementById(id);
let data = null;

function esc(value) { const d=document.createElement('div'); d.textContent=value ?? ''; return d.innerHTML; }
function weatherIcon(code) {
  if (code === 0) return '☀️';
  if ([1,2].includes(code)) return '🌤️';
  if (code === 3) return '☁️';
  if ([45,48].includes(code)) return '🌫️';
  if ([51,53,55,56,57,61,63,65,66,67,80,81,82].includes(code)) return '🌧️';
  if ([71,73,75,77,85,86].includes(code)) return '🌨️';
  if ([95,96,99].includes(code)) return '⛈️';
  return '🌡️';
}
function shortDate(iso) { return new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric'}).format(new Date(`${iso}T12:00:00`)); }
function relativeDate(iso) {
  const today=new Date(); today.setHours(0,0,0,0); const d=new Date(`${iso}T00:00:00`); const n=Math.round((d-today)/86400000);
  if(n<0) return `${Math.abs(n)}d overdue`; if(n===0) return 'Today'; if(n===1) return 'Tomorrow'; return `In ${n} days`;
}
function eventTime(e) { if(e.all_day) return 'All day'; return new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date(e.start)); }
function showToast(text){ const t=$('toast'); t.textContent=text; t.classList.remove('hidden'); clearTimeout(t.timer); t.timer=setTimeout(()=>t.classList.add('hidden'),2500); }

function renderTasks() {
  const c=data.chores; const total=c.counts.due+c.counts.completed; const pct=total ? Math.round(c.counts.completed/total*100) : 100;
  $('task-progress').innerHTML=`<span>${c.counts.completed} of ${total} finished</span><strong>${pct}%</strong>`; $('progress-bar').style.width=`${pct}%`;
  $('today-tasks').innerHTML=c.due.slice(0,5).map(x=>`<button class="task-row" data-task="${x.id}"><span class="check">✓</span><span><strong>${esc(x.task)}</strong><small>${esc(x.area)}${x.days_overdue?` · ${x.days_overdue}d overdue`:''}</small></span></button>`).join('') || '<p class="empty">Everything due today is finished.</p>';
  document.querySelectorAll('[data-task]').forEach(b=>b.onclick=async()=>{ b.disabled=true; await fetch(`/api/chores/${b.dataset.task}/complete`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); showToast('Task completed'); load(); });
  $('upcoming-count').textContent=c.upcoming.length;
  $('upcoming-tasks').innerHTML=c.upcoming.map(x=>`<div class="plain-row"><span><strong>${esc(x.task)}</strong><small>${esc(x.area)}</small></span><em>${shortDate(x.next_due)}</em></div>`).join('') || '<p class="empty">Nothing upcoming.</p>';
}
function renderCalendar() {
  const cal=data.calendar;
  if(!cal.configured){ $('calendar-events').innerHTML='<p class="setup">Connect Google Calendar in the Pi configuration.</p>'; return; }
  if(cal.error){ $('calendar-events').innerHTML=`<p class="setup">Calendar unavailable: ${esc(cal.error)}</p>`; return; }
  $('calendar-events').innerHTML=cal.events.slice(0,6).map(e=>`<div class="calendar-row"><time>${eventTime(e)}</time><span><strong>${esc(e.title)}</strong><small>${new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric'}).format(new Date(e.start))}${e.location?` · ${esc(e.location)}`:''}</small></span></div>`).join('') || '<p class="empty">No events in the next week.</p>';
}
function renderWeather() {
  const w=data.weather;
  if(!w.configured || w.error){ $('weather-current').innerHTML='<p class="setup">Set your location to enable weather.</p>'; $('hero-weather').innerHTML='<span>🌡️</span><strong>--°</strong>'; return; }
  const c=w.current; $('hero-weather').innerHTML=`<span>${weatherIcon(c.code)}</span><strong>${Math.round(c.temperature)}°</strong>`;
  $('weather-current').innerHTML=`<div class="weather-now"><span>${weatherIcon(c.code)}</span><div><strong>${Math.round(c.temperature)}°</strong><small>Feels like ${Math.round(c.feels_like)}° · Wind ${Math.round(c.wind)} mph</small></div></div>`;
  $('forecast').innerHTML=w.daily.slice(0,4).map(d=>`<div><small>${new Intl.DateTimeFormat(undefined,{weekday:'short'}).format(new Date(`${d.date}T12:00:00`))}</small><span>${weatherIcon(d.code)}</span><strong>${Math.round(d.high)}°</strong><em>${Math.round(d.low)}°</em></div>`).join('');
}
function renderReminders(){ $('reminders').innerHTML=data.reminders.map(r=>`<button class="reminder-row" data-reminder="${r.id}"><span class="big-icon">${esc(r.icon)}</span><span><strong>${esc(r.title)}</strong><small>${relativeDate(r.due_date)}${r.notes?` · ${esc(r.notes)}`:''}</small></span><span class="done-dot">✓</span></button>`).join('') || '<p class="empty">No upcoming reminders.</p>'; document.querySelectorAll('[data-reminder]').forEach(b=>b.onclick=async()=>{await fetch(`/api/reminders/${b.dataset.reminder}/complete`,{method:'POST'});load();}); }
function renderGroceries(){ $('groceries').innerHTML=data.groceries.map(g=>`<div class="plain-row"><span><strong>${esc(g.item)}</strong><small>${esc(g.category)}${g.quantity?` · ${esc(g.quantity)}`:''}</small></span></div>`).join('') || '<p class="empty">Shopping list is empty.</p>'; }
function renderNotes(){ $('notes').innerHTML=data.notes.map(n=>`<div class="note-row"><span>${esc(n.body)}</span><button data-note="${n.id}">×</button></div>`).join('') || '<p class="empty">No household notes.</p>'; document.querySelectorAll('[data-note]').forEach(b=>b.onclick=async()=>{await fetch(`/api/notes/${b.dataset.note}`,{method:'DELETE'});load();}); }
function render(){ renderTasks(); renderCalendar(); renderWeather(); renderReminders(); renderGroceries(); renderNotes(); }
async function load(){ try{ const r=await fetch('/api/dashboard',{cache:'no-store'}); if(!r.ok)throw new Error(); data=await r.json(); render(); }catch(e){ showToast('Could not refresh dashboard'); } }
function updateClock(){ const now=new Date(); $('date-title').textContent=new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric'}).format(now); $('clock').textContent=new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(now); }

document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>$(b.dataset.open).showModal());
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('grocery-form').onsubmit=async e=>{e.preventDefault(); const f=new FormData(e.target); await fetch('/api/groceries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f))}); e.target.reset(); $('grocery-dialog').close(); load();};
$('reminder-form').onsubmit=async e=>{e.preventDefault(); const f=new FormData(e.target); await fetch('/api/reminders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f))}); e.target.reset(); $('reminder-dialog').close(); load();};
$('note-form').onsubmit=async e=>{e.preventDefault(); const f=new FormData(e.target); await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(f))}); e.target.reset(); $('note-dialog').close(); load();};
$('calendar-refresh').onclick=load;
updateClock(); setInterval(updateClock,15000); load(); setInterval(load,10*60*1000);
