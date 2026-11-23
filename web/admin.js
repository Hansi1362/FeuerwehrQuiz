const view = document.getElementById('view');
let quizzes = [], current = null /* gerade bearbeitete Runde */, G = null /* Spielstatus */;

function msg(text, kind) {
  const m = document.getElementById('msg');
  m.replaceChildren();
  if (!text) return;
  m.append(el('div', 'msg ' + (kind || 'err'), text));
  clearTimeout(msg.h); msg.h = setTimeout(() => m.replaceChildren(), 5000);
}
async function guard(fn) { try { await fn(); } catch (e) { msg(e.message); } }
async function control(action, extra) {
  await guard(async () => { await api('/api/control', Object.assign({ action }, extra || {})); await refreshStatus(); });
}

// ---------- Spielstatus
const PHASES = { lobby: 'Lobby (wartet auf Start)', read: 'Frage wird gelesen', answer: 'Antwortphase', result: 'Auflösung', scoreboard: 'Zwischenstand', finished: 'Spiel beendet' };
async function refreshStatus() {
  try { G = await api('/api/host/state'); } catch (e) { return; }
  const s = document.getElementById('status'); s.replaceChildren();
  const info = el('span', 'grow');
  info.append('Status: ', el('b', '', PHASES[G.phase] + (G.paused ? ' (pausiert)' : '')));
  if (G.phase !== 'lobby') info.append(` · Frage ${Math.max(1, G.q_index + 1)}/${G.total}`);
  info.append(` · ${G.players.length} Spieler`);
  s.append(info);
  if (['read', 'answer', 'result', 'scoreboard'].includes(G.phase)) {
    const bp = el('button', 'btn small ghost', G.paused ? '▶ Fortsetzen' : '⏸ Anhalten'); bp.onclick = () => control(G.paused ? 'resume' : 'pause');
    const bs = el('button', 'btn small ghost', '⏭ Weiter'); bs.onclick = () => control('skip');
    s.append(bp, bs);
  }
  if (G.phase !== 'lobby') {
    const bx = el('button', 'btn small danger', G.phase === 'finished' ? 'Neues Spiel' : '■ Abbrechen');
    bx.onclick = () => { if (G.phase === 'finished' || confirm('Spiel abbrechen? Spieler und Punkte werden gelöscht.')) control('stop'); };
    s.append(bx);
  }
  // Liste nur neu zeichnen, wenn sich Auswahl oder Lobby-Zustand geändert haben
  const key = (G.quiz ? G.quiz.id : '') + '|' + (G.phase === 'lobby');
  if (!current && key !== refreshStatus.key) { refreshStatus.key = key; renderList(); }
}

// ---------- Import / Export
const FORMAT = 'quizrunde';
function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function slug(s) { return (s || 'fragerunde').toLowerCase().replace(/[^a-z0-9äöüß]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 50) || 'fragerunde'; }
function exportQuiz(z) {
  downloadJson(slug(z.name) + '.quizrunde.json',
    { format: FORMAT, version: 1, quiz: { name: z.name, questions: z.questions } });
}
function pickFiles() {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = '.json,application/json'; inp.multiple = true;
  inp.onchange = () => guard(async () => {
    const ok = [], bad = [];
    for (const f of inp.files) {
      let data;
      try { data = JSON.parse(await f.text()); } catch (e) { bad.push(`${f.name}: keine gültige JSON-Datei`); continue; }
      try { const r = await api('/api/quizzes/import', { data }); ok.push(...r.imported); bad.push(...r.errors.map(e => `${f.name}: ${e}`)); }
      catch (e) { bad.push(`${f.name}: ${e.message}`); }
    }
    await loadQuizzes(); renderList();
    if (ok.length) msg(`Importiert: ${ok.join(', ')}` + (bad.length ? ` – Probleme: ${bad.join(' | ')}` : ''), 'ok');
    else msg(bad.join(' | ') || 'Keine Datei gewählt.');
  });
  inp.click();
}

// ---------- Liste
async function loadQuizzes() { await guard(async () => { quizzes = await api('/api/quizzes'); }); }
function renderList() {
  view.replaceChildren();
  const head = el('div', 'top');
  head.append(el('h2', '', 'Fragerunden'));
  head.firstChild.style.cssText = 'margin:0;flex:1';
  const nb = el('button', 'btn', '+ Neue Fragerunde'); nb.onclick = () => edit(newQuiz());
  const ib = el('button', 'btn ghost', '⬆ Importieren'); ib.onclick = pickFiles;
  head.append(ib, nb); view.append(head);
  if (!quizzes.length) view.append(el('div', 'empty', 'Noch keine Fragerunden. Lege die erste an!'));
  const list = el('div', 'list');
  quizzes.forEach(z => {
    const selected = G && G.quiz && G.quiz.id === z.id;
    const it = el('div', 'item' + (selected ? ' sel' : ''));
    const nm = el('div', 'nm'); nm.append(el('b', '', z.name), el('span', '', `${z.questions.length} Fragen`));
    const lobby = !G || G.phase === 'lobby';
    const bsel = el('button', 'btn small ghost', selected ? '✓ Ausgewählt' : 'Auswählen');
    bsel.disabled = !lobby; bsel.onclick = () => control('select', { quiz_id: z.id });
    const bgo = el('button', 'btn small', '▶ Starten'); bgo.disabled = !lobby;
    bgo.onclick = () => control('start', { quiz_id: z.id });
    const bex = el('button', 'btn small ghost', '⬇ Export'); bex.onclick = () => exportQuiz(z);
    const bed = el('button', 'btn small ghost', 'Bearbeiten'); bed.onclick = () => edit(JSON.parse(JSON.stringify(z)));
    const bdel = el('button', 'btn small danger', 'Löschen');
    bdel.onclick = () => guard(async () => {
      if (!confirm(`„${z.name}“ wirklich löschen?`)) return;
      await api('/api/quizzes/delete', { id: z.id }); await loadQuizzes(); renderList();
    });
    it.append(nm, bsel, bgo, bed, bex, bdel); list.append(it);
  });
  view.append(list);
  view.append(el('p', 'hint', 'Zum Starten müssen zuerst Spieler über den QR-Code im Spielbildschirm beitreten.'));
  view.lastChild.style.cssText = 'color:var(--muted);font-size:.9rem;margin-top:1rem';
}

// ---------- Editor
function newQuestion(type) {
  return type === 'yesno'
    ? { type: 'yesno', text: '', options: ['Ja', 'Nein'], correct: [0], time: 15 }
    : { type: 'multi', text: '', options: ['', '', '', ''], correct: [0], time: 20 };
}
function newQuiz() { return { id: null, name: '', questions: [newQuestion('multi')] }; }

function edit(q) { current = q; renderEditor(); window.scrollTo(0, 0); }

function renderEditor() {
  view.replaceChildren();
  const f = el('div', 'field');
  f.append(el('label', '', 'Name der Fragerunde'));
  const name = el('input'); name.type = 'text'; name.maxLength = 80; name.value = current.name; name.placeholder = 'z. B. Allgemeinwissen';
  name.oninput = () => { current.name = name.value; };
  f.append(name); view.append(f);

  current.questions.forEach((q, qi) => view.append(questionCard(q, qi)));

  const add = el('div', 'actions');
  const a1 = el('button', 'btn ghost', '+ Frage mit 4 Antworten'); a1.onclick = () => { current.questions.push(newQuestion('multi')); renderEditor(); scrollEnd(); };
  const a2 = el('button', 'btn ghost', '+ Ja/Nein-Frage'); a2.onclick = () => { current.questions.push(newQuestion('yesno')); renderEditor(); scrollEnd(); };
  const save = el('button', 'btn', '💾 Speichern');
  save.onclick = () => guard(async () => {
    const saved = await api('/api/quizzes', current);
    await loadQuizzes(); current = null; renderList(); msg(`„${saved.name}“ gespeichert.`, 'ok');
  });
  const cancel = el('button', 'btn ghost', 'Abbrechen');
  cancel.onclick = () => { current = null; renderList(); };
  add.append(a1, a2, save, cancel); view.append(add);
}
function scrollEnd() { window.scrollTo(0, document.body.scrollHeight); }

function questionCard(q, qi) {
  const card = el('div', 'q');
  const top = el('div', 'qtop');
  top.append(el('span', 'num', `Frage ${qi + 1}`));
  const sel = el('select');
  sel.append(new Option('4 Antworten (eine oder mehrere richtig)', 'multi'), new Option('Ja / Nein', 'yesno'));
  sel.value = q.type;
  sel.onchange = () => {
    const keep = q.text, t = q.time, n = newQuestion(sel.value);
    Object.assign(q, n, { text: keep, time: t }); renderEditor();
  };
  const tw = el('label', 'time'); tw.append('Zeit (s)');
  const time = el('input'); time.type = 'number'; time.min = 5; time.max = 120; time.value = q.time;
  time.oninput = () => { q.time = parseInt(time.value, 10) || 20; };
  tw.append(time);
  const up = el('button', 'btn small ghost', '↑'), down = el('button', 'btn small ghost', '↓'), del = el('button', 'btn small danger', '🗑');
  up.disabled = qi === 0; down.disabled = qi === current.questions.length - 1; del.disabled = current.questions.length === 1;
  const swap = j => { const a = current.questions; [a[qi], a[j]] = [a[j], a[qi]]; renderEditor(); };
  up.onclick = () => swap(qi - 1); down.onclick = () => swap(qi + 1);
  del.onclick = () => { current.questions.splice(qi, 1); renderEditor(); };
  top.append(sel, tw, up, down, del);
  card.append(top);

  const ta = el('textarea'); ta.placeholder = 'Fragetext'; ta.maxLength = 300; ta.value = q.text;
  ta.oninput = () => { q.text = ta.value; };
  card.append(ta);

  if (q.type === 'yesno') {
    card.append(el('div', 'lbl', 'Richtige Antwort'));
    card.lastChild.style.margin = '.8rem 0 .4rem';
    const yn = el('div', 'yn');
    ['Ja', 'Nein'].forEach((t, i) => {
      const l = el('label'); const r = el('input'); r.type = 'radio'; r.name = `yn${qi}`; r.checked = q.correct[0] === i;
      r.onchange = () => { q.correct = [i]; };
      l.append(r, t); yn.append(l);
    });
    card.append(yn);
  } else {
    card.append(el('div', 'lbl', 'Antworten – Haken setzen bei allen richtigen'));
    card.lastChild.style.margin = '.8rem 0 .2rem';
    q.options.forEach((t, i) => {
      const row = el('div', 'opt c' + i);
      const cb = el('input'); cb.type = 'checkbox'; cb.checked = q.correct.includes(i); cb.title = 'richtig';
      cb.onchange = () => { q.correct = cb.checked ? [...new Set([...q.correct, i])].sort() : q.correct.filter(c => c !== i); };
      const inp = el('input'); inp.type = 'text'; inp.maxLength = 120; inp.placeholder = `Antwort ${i + 1}`; inp.value = t;
      inp.oninput = () => { q.options[i] = inp.value; };
      row.append(el('span', 'tag', String(i + 1)), inp, cb); card.append(row);
    });
  }
  return card;
}

(async () => {
  await refreshStatus();
  await loadQuizzes();
  renderList();
  setInterval(refreshStatus, 1000);
})();
