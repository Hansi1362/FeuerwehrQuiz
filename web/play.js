const main = document.getElementById('main');
const store = {
  get: k => { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignorieren */ } },
};
let pid = store.get('quiz_pid');
let S = null, viewKey = null, refs = {}, sel = new Set(), sending = false;

const setClock = makeClock((left, dur) => {
  const bar = document.querySelector('#timer .bar > i');
  if (bar) { bar.style.width = Math.min(100, left / dur * 100) + '%'; bar.classList.toggle('low', left < 5); }
});

// ---- Beitreten
function buildJoin() {
  main.replaceChildren();
  const card = el('div', 'card');
  const brand = el('div', 'brand'); const logo = el('img'); logo.src = '/static/logo.png'; logo.alt = ''; logo.onerror = () => logo.remove(); brand.append(logo);
  card.append(brand, el('h1', 'display', '🚒 ' + S.title), el('div', 'hint', 'Wie heißt du?'));
  const inp = el('input', 'name'); inp.maxLength = 20; inp.placeholder = 'Dein Name'; inp.value = store.get('quiz_name');
  inp.autocomplete = 'nickname';
  const err = el('div', 'err');
  const b = el('button', 'btn wide', 'Antreten!');
  const go = async () => {
    err.textContent = '';
    try {
      const r = await api('/api/join', { name: inp.value, pid: null });
      pid = r.pid; store.set('quiz_pid', pid); store.set('quiz_name', r.name);
      poll();
    } catch (e) { err.textContent = e.message; }
  };
  b.onclick = go; inp.onkeydown = e => { if (e.key === 'Enter') go(); };
  card.append(inp, b, err); main.append(card);
}

// ---- Fragen
function buildQuestion() {
  main.replaceChildren(); sel = new Set(); sending = false;
  const q = S.question;
  main.append(el('div', 'qtext', q.text));
  refs.hint = el('div', 'hint'); main.append(refs.hint);
  const grid = el('div', 'answers' + (q.type === 'yesno' ? ' two' : ''));
  refs.btns = q.options.map((t, i) => {
    const b = el('button', 'ans ' + optClass(q, i));
    b.append(el('span', 'num', q.type === 'yesno' ? t : String(i + 1)));
    if (q.type !== 'yesno') b.append(el('span', 'txt', t));
    b.onclick = () => choose(i);
    grid.append(b); return b;
  });
  main.append(grid);
  refs.send = el('button', 'btn wide', 'Antwort senden');
  refs.send.onclick = () => submit([...sel]);
  if (q.multiple) main.append(refs.send);
}
function choose(i) {
  const q = S.question;
  if (S.phase !== 'answer' || S.my_choice || sending) return;
  if (!q.multiple) return submit([i]);
  sel.has(i) ? sel.delete(i) : sel.add(i);
  updateQuestion();
}
async function submit(choice) {
  if (!choice.length || sending) return;
  sending = true;
  try { await api('/api/answer', { pid, choice }); S.my_choice = choice; }
  catch (e) { sending = false; refs.hint.textContent = e.message; return; }
  poll();
}
function updateQuestion() {
  const q = S.question, locked = S.phase !== 'answer' || S.paused || !!S.my_choice;
  const chosen = S.my_choice ? new Set(S.my_choice) : sel;
  refs.btns.forEach((b, i) => {
    b.disabled = locked;
    b.classList.toggle('lock', S.phase === 'read');
    b.classList.toggle('sel', chosen.has(i));
    b.classList.toggle('off', !!S.my_choice && !chosen.has(i));
  });
  refs.send.disabled = locked || sel.size === 0;
  refs.send.classList.toggle('hidden', !!S.my_choice);
  refs.hint.textContent = S.my_choice ? 'Antwort gesendet ✓ – warte auf die anderen …'
    : S.phase === 'read' ? 'Lies die Frage … gleich kannst du antworten'
    : q.multiple ? 'Mehrere Antworten möglich – dann „Antwort senden“' : '';
}

// ---- Ergebnis & Rang
function buildResult() {
  main.replaceChildren();
  const q = S.question, r = S.result;
  const card = el('div', 'card');
  const ok = r.correct;
  card.append(el('div', 'big', ok ? '✅' : r.answered ? '❌' : '⏱️'));
  const t = el('h1', ok ? 'res-ok' : 'res-bad', ok ? 'Richtig!' : r.answered ? 'Leider falsch' : 'Keine Antwort');
  t.style.marginTop = '.6rem'; card.append(t);
  if (ok) card.append(el('div', 'rank', '+' + r.points));
  if (ok) card.append(el('div', 'hint', `Du warst Nr. ${r.answer_rank} unter den richtigen Antworten`));
  main.append(card);
  const right = q.correct.map(i => q.type === 'yesno' ? q.options[i] : `${i + 1} – ${q.options[i]}`).join(' · ');
  const c2 = el('div', 'card'); c2.append(el('div', 'hint', 'Richtig ist'), el('div', 'qtext', right));
  main.append(c2);
  const c3 = el('div', 'card'); refs.rankcard = c3; main.append(c3);
  fillRank(c3);
}
function fillRank(c) {
  c.replaceChildren(el('div', 'hint', 'Dein Platz'), el('div', 'rank', `${S.rank}. von ${S.players}`),
    el('div', 'hint', S.score + ' Punkte'));
}

function buildScoreboard() {
  main.replaceChildren();
  refs.rankcard = el('div', 'card'); main.append(refs.rankcard);
  main.append(el('div', 'hint', `Frage ${S.q_index + 1} von ${S.total} geschafft`));
}

function buildWait(title, sub) {
  main.replaceChildren();
  const c = el('div', 'card'); c.append(el('div', 'big', '🚒'), el('h1', '', title)); c.firstChild.style.marginBottom = '.6rem';
  refs.sub = el('div', 'hint', sub); c.append(refs.sub); main.append(c);
}

function buildFinished() {
  main.replaceChildren();
  const c = el('div', 'card');
  const medal = S.rank === 1 ? '🏆' : S.rank === 2 ? '🥈' : S.rank === 3 ? '🥉' : '🎉';
  c.append(el('div', 'big', medal), el('h1', '', 'Spiel beendet'));
  c.append(el('div', 'rank', `Platz ${S.rank} von ${S.players}`), el('div', 'hint', S.score + ' Punkte'));
  main.append(c);
}

// ---- Hauptschleife
function render() {
  document.title = S.title;
  const head = document.getElementById('head');
  const joined = S.joined;
  head.classList.toggle('hidden', !joined);
  const active = joined && ['read', 'answer'].includes(S.phase);
  document.getElementById('timer').classList.toggle('hidden', !active);
  document.getElementById('banner').classList.toggle('hidden', !(joined && S.paused));
  setClock(S.time_left, S.duration, S.paused);

  if (!joined) {
    if (viewKey !== 'join') { viewKey = 'join'; refs = {}; buildJoin(); }
    return;
  }
  document.getElementById('who').textContent = S.name;
  document.getElementById('pts').textContent = S.phase === 'lobby' ? '' : S.score + ' Punkte';

  const key = S.phase === 'read' || S.phase === 'answer' ? 'q' + S.q_index : S.phase + S.q_index;
  if (key !== viewKey) {
    viewKey = key; refs = {};
    if (S.phase === 'lobby') buildWait('Du bist dabei!', 'Warte, bis das Spiel gestartet wird …');
    else if (S.phase === 'read' || S.phase === 'answer') buildQuestion();
    else if (S.phase === 'result') buildResult();
    else if (S.phase === 'scoreboard') buildScoreboard();
    else if (S.phase === 'finished') buildFinished();
  }
  if (S.phase === 'read' || S.phase === 'answer') updateQuestion();
  else if ((S.phase === 'result' || S.phase === 'scoreboard') && refs.rankcard) fillRank(refs.rankcard);
}

async function poll() {
  try { S = await api('/api/play/state?pid=' + encodeURIComponent(pid)); render(); } catch (e) { /* Verbindung weg */ }
}
poll(); setInterval(poll, 500);
