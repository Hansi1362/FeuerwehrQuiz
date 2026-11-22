const stage = document.getElementById('stage');
let S = null;          // letzter Serverzustand
let viewKey = null;    // aktuell aufgebaute Ansicht
let refs = {};         // DOM-Referenzen der Ansicht

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.remove('hidden');
  clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.add('hidden'), 3500);
}
async function control(action, extra) {
  try { await api('/api/control', Object.assign({ action }, extra || {})); poll(); }
  catch (e) { toast(e.message); }
}

// ---- Countdown / Zeitbalken
const setClock = makeClock((left, dur) => {
  const bar = document.querySelector('#timer .bar > i');
  if (bar) {
    bar.style.width = (dur ? Math.min(100, left / dur * 100) : 0) + '%';
    bar.classList.toggle('low', left < 5);
  }
  if (refs.count) refs.count.textContent = Math.ceil(left);
});

// ---- Ansichten
function buildLobby() {
  stage.replaceChildren();
  const wrap = el('div', 'lobby');
  const left = el('div');
  const qr = el('div', 'qrcard'); const img = el('img'); img.alt = 'QR-Code'; img.src = '/qr.svg?' + Date.now(); qr.append(img);
  const info = el('div', 'joininfo');
  info.append(el('div', '', 'Handy-Kamera auf den Code richten oder öffnen:'));
  refs.url = el('b'); info.append(refs.url);
  left.append(qr, info);

  const right = el('div');
  const brand = el('div', 'brand');
  const logo = el('img'); logo.src = '/static/logo.png'; logo.alt = ''; logo.onerror = () => logo.remove();
  refs.h1 = el('h1', 'display'); brand.append(logo, refs.h1); right.append(brand);
  refs.sub = el('div', 'dim'); right.append(refs.sub);
  refs.chips = el('div', 'chips'); right.append(refs.chips);
  const row = el('div', 'startrow');
  refs.sel = el('select');
  refs.sel.onchange = () => control('select', { quiz_id: refs.sel.value || null });
  refs.start = el('button', 'btn', '▶ Spiel starten');
  refs.start.onclick = () => control('start');
  row.append(refs.sel, refs.start);
  right.append(row);
  wrap.append(left, right);
  stage.append(wrap);
  refs.names = null; refs.quizKey = null;
}
function updateLobby() {
  refs.url.textContent = S.join_url;
  refs.h1.textContent = '🚒 ' + S.title;
  const n = S.players.length;
  refs.sub.textContent = n ? n + (n === 1 ? ' Spieler startklar' : ' Spieler startklar') : 'Warte auf Einsatzkräfte … (Spieler)';
  const names = S.players.map(p => p.name).join('\n');
  if (names !== refs.names) {
    refs.names = names;
    refs.chips.replaceChildren(...S.players.map(p => el('span', 'chip', p.name)));
  }
  const qk = JSON.stringify(S.quizzes);
  if (qk !== refs.quizKey) {
    refs.quizKey = qk;
    const opts = [new Option('– Fragerunde wählen –', '')];
    S.quizzes.forEach(z => opts.push(new Option(`${z.name} (${z.count} Fragen)`, z.id)));
    refs.sel.replaceChildren(...opts);
  }
  if (document.activeElement !== refs.sel) refs.sel.value = S.quiz ? S.quiz.id : '';
  refs.start.disabled = !(S.quiz && S.players.length);
}

function optionTile(q, i, extra) {
  const o = el('div', 'opt ' + optClass(q, i) + (extra ? ' ' + extra : ''));
  o.append(el('span', 'n', q.type === 'yesno' ? (i === 0 ? '✓' : '✕') : String(i + 1)), el('span', '', q.options[i]));
  return o;
}

function buildQuestion() {
  stage.replaceChildren();
  const q = S.question;
  const head = el('div', 'qhead');
  head.append(el('h1', '', q.text));
  refs.count = el('div', 'count'); head.append(refs.count);
  const opts = el('div', 'opts' + (q.type === 'yesno' ? ' two' : ''));
  q.options.forEach((_, i) => opts.append(optionTile(q, i)));
  refs.status = el('div', 'status');
  stage.append(head, opts, refs.status);
}
function updateQuestion() {
  const hint = S.question.multiple ? ' · Mehrere Antworten möglich' : '';
  refs.status.textContent = S.phase === 'read'
    ? 'Lies die Frage … gleich geht es los' + hint
    : `${S.answered} von ${S.players.length} haben geantwortet` + hint;
}

function buildResult() {
  stage.replaceChildren();
  const q = S.question;
  stage.append(el('h1', '', q.text));
  const cols = el('div', 'cols'); cols.style.marginTop = '1.5rem';
  const left = el('div'); const opts = el('div', 'opts');
  q.options.forEach((_, i) => {
    const right = q.correct.includes(i);
    const o = optionTile(q, i, right ? 'right' : 'wrong');
    o.append(el('span', 'cnt', String(S.counts[i])));
    opts.append(o);
  });
  left.append(opts);
  const right = el('div');
  right.append(el('h2', '', 'Punkte dieser Frage'));
  const rows = el('div', 'rows');
  const scorers = S.players.filter(p => p.answer_rank).sort((a, b) => a.answer_rank - b.answer_rank);
  const max = Math.max(1, ...scorers.map(p => p.gain));
  scorers.slice(0, 8).forEach(p => {
    const r = el('div', 'row' + (p.answer_rank === 1 ? ' first' : ''));
    const track = el('div', 'track'); const fill = el('div', 'fill'); track.append(fill);
    r.append(el('span', 'rk', p.answer_rank + '.'), el('span', 'nm', p.name), track, el('span', 'pt', '+' + p.gain));
    rows.append(r);
    setTimeout(() => { fill.style.width = (p.gain / max * 100) + '%'; }, 80);
  });
  right.append(rows);
  const none = S.players.length - scorers.length;
  if (scorers.length > 8) right.append(el('div', 'dim', `… und ${scorers.length - 8} weitere mit Punkten`));
  if (none > 0) right.append(el('div', 'dim', none + (none === 1 ? ' Spieler ohne Punkte' : ' Spieler ohne Punkte')));
  if (!scorers.length) right.append(el('div', 'dim', 'Niemand hatte die richtige Antwort.'));
  cols.append(left, right); stage.append(cols);
}

function rankRows(players, withGain, limit) {
  const rows = el('div', 'rows');
  const max = Math.max(1, ...players.map(p => p.score));
  players.slice(0, limit).forEach(p => {
    const r = el('div', 'row' + (p.rank === 1 ? ' first' : ''));
    const track = el('div', 'track'); const fill = el('div', 'fill'); track.append(fill);
    const pt = el('span', 'pt', String(p.score));
    if (withGain && p.gain) pt.append(el('span', 'gain', '+' + p.gain));
    r.append(el('span', 'rk', p.rank + '.'), el('span', 'nm', p.name), track, pt);
    rows.append(r);
    setTimeout(() => { fill.style.width = (p.score / max * 100) + '%'; }, 80);
  });
  return rows;
}

function buildScoreboard() {
  stage.replaceChildren();
  const last = S.q_index + 1 >= S.total;
  stage.append(el('h1', 'center display', last ? 'Endstand' : 'Zwischenstand'));
  const box = el('div'); box.style.cssText = 'max-width:60rem;width:100%;margin:2rem auto 0';
  box.append(rankRows(S.players, true, 10));
  if (S.players.length > 10) box.append(el('div', 'dim', `… und ${S.players.length - 10} weitere`));
  stage.append(box);
}

function buildFinished() {
  stage.replaceChildren();
  const wrap = el('div', 'center');
  const winners = S.players.filter(p => p.rank === 1);
  wrap.append(el('div', 'dim', '🏆 Bester Einsatzleiter'));
  wrap.append(el('div', 'winner display', winners.map(p => p.name).join(' & ') || '—'));
  const pod = el('div', 'podium');
  const top = S.players.filter(p => p.rank <= 3).slice(0, 3);
  [1, 0, 2].forEach(idx => {
    const p = S.players[idx]; if (!p || !top.includes(p)) return;
    const d = el('div', 'pod p' + p.rank); d.style.animationDelay = (3 - p.rank) * .4 + 's';
    d.append(el('span', '', p.rank + '. ' + p.name), el('small', '', p.score + ' Punkte'));
    pod.append(d);
  });
  wrap.append(pod);
  const rest = S.players.filter(p => !top.includes(p));
  if (rest.length) { const box = el('div', 'rest'); box.append(rankRows(rest, false, 7)); wrap.append(box); }
  const b = el('button', 'btn', '↻ Neues Spiel'); b.style.cssText = 'margin-top:1.5rem;font-size:1.2rem';
  b.onclick = () => control('stop');
  wrap.append(b);
  stage.append(wrap);
}

// ---- Hauptschleife
function render() {
  document.title = S.title + ' – Spielbildschirm';
  const active = ['read', 'answer', 'result', 'scoreboard'].includes(S.phase);
  document.getElementById('top').classList.toggle('hidden', !active);
  document.getElementById('timer').classList.toggle('hidden', !active);
  document.getElementById('pause').classList.toggle('hidden', !(active && S.paused));
  document.getElementById('bPause').textContent = S.paused ? '▶ Fortsetzen' : '⏸ Anhalten';
  if (active) {
    document.getElementById('progress').textContent = `Frage ${S.q_index + 1} / ${S.total}`;
    document.getElementById('quizname').textContent = S.quiz && S.quiz.name || '';
  }
  setClock(S.time_left, S.duration, S.paused);

  const key = S.phase === 'read' || S.phase === 'answer' ? 'q' + S.q_index : S.phase + (S.q_index);
  if (key !== viewKey) {
    viewKey = key; refs = {};
    if (S.phase === 'lobby') buildLobby();
    else if (S.phase === 'read' || S.phase === 'answer') buildQuestion();
    else if (S.phase === 'result') buildResult();
    else if (S.phase === 'scoreboard') buildScoreboard();
    else if (S.phase === 'finished') buildFinished();
  }
  if (S.phase === 'lobby') updateLobby();
  else if (S.phase === 'read' || S.phase === 'answer') updateQuestion();
}

async function poll() {
  try { S = await api('/api/host/state'); render(); } catch (e) { /* Server kurz weg */ }
}
document.getElementById('bPause').onclick = () => control(S && S.paused ? 'resume' : 'pause');
document.getElementById('bResume').onclick = () => control('resume');
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && S && ['read', 'answer', 'result', 'scoreboard'].includes(S.phase)) { e.preventDefault(); control(S.paused ? 'resume' : 'pause'); }
});
document.getElementById('bSkip').onclick = () => control('skip');
document.getElementById('bStop').onclick = () => { if (confirm('Spiel abbrechen? Spieler und Punkte werden gelöscht.')) control('stop'); };
poll(); setInterval(poll, 400);
