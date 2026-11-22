// Gemeinsame Hilfsfunktionen
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch (e) { /* leer */ }
  if (!r.ok) throw new Error(data.error || ('Fehler ' + r.status));
  return data;
}

// Lokal weiterlaufender Countdown (der Server schickt die Restzeit bei jedem Poll)
function makeClock(onTick) {
  let left = 0, duration = 1, paused = false, stamp = performance.now();
  setInterval(() => {
    const now = paused ? left : Math.max(0, left - (performance.now() - stamp) / 1000);
    onTick(now, duration);
  }, 100);
  return (l, d, p) => { left = l; duration = d || 1; paused = p; stamp = performance.now(); };
}

function optClass(q, i) {
  return q.type === 'yesno' ? (i === 0 ? 'cyes' : 'cno') : 'c' + i;
}
