const OPS = {contains: 'contains', eq: 'equals (=)', ne: 'does not equal (≠)', starts: 'starts with', gt: 'greater than (>)', gte: 'greater than or equal to (≥)', lt: 'less than (<)', lte: 'less than or equal to (≤)', empty: 'is empty', filled: 'is not empty'};
const CMP = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte'];
const numCol = col => !!sheet().cols.find(c => c.name === col)?.numeric;
const opsFor = col => numCol(col) ? [...CMP, 'contains', 'empty', 'filled'] : ['contains', 'starts', ...CMP, 'empty', 'filled'];
const newPivot = () => ({rows: [], cols: [], values: [{fn: 'count', cols: []}], totals: true});
const S = {search: '', filters: [], picks: {}, pivot: newPivot(), sort: null, page: 1};
const pivotOn = () => S.pivot.rows.length > 0;
const sheet = () => WS.sheetMeta();
const spec = () => ({...WS.params(), search: S.search, sort: S.sort, page: S.page,
  filters: S.filters.filter(f => f.col && (['empty', 'filled'].includes(f.op) || (f.value !== '' && (!numCol(f.col) || !CMP.includes(f.op) || !isNaN(Number(f.value)))))),
  picks: Object.entries(S.picks).map(([col, p]) => ({col, mode: p.mode, values: p.vals, blank: p.blank})), pivot: pivotOn() ? S.pivot : null});


// the open file comes from the workspace (see workspace.js)
WS.dropzone($('#up'), {title: 'Open a file to view'});
WS.bar($('#wsbar'));
let seen = '';
function render() {  // runs whenever the workspace changes: another file, sheet or header row starts a fresh view
  const s = WS.sheetMeta(); $('#up').hidden = !!s; $('#exp').hidden = !s; $('#app').hidden = !s;
  if (WS.key() === seen) return;
  seen = WS.key();
  Object.assign(S, {search: '', filters: [], picks: {}, pivot: newPivot(), sort: null, page: 1});
  if (!s) return;
  $('#search').value = ''; $('#vcol').innerHTML = colOpts(''); $('#vq').value = '';
  drawF(); drawP(); drawStats(); run();
}
WS.on(render);
function drawStats() {
  const s = sheet(), n = t => s.cols.filter(c => c.type === t).length;
  $('#stats').innerHTML = [[s.rows.toLocaleString(), 'Rows'], [s.cols.length, 'Columns'], [n('number'), 'Number columns'], [n('text'), 'Text columns'], [n('date') + n('bool'), 'Date or true/false']]
    .map(([v, l]) => `<div class="glass stat"><b>${v}</b><span class="muted">${l}</span></div>`).join('');
}
$('#search').oninput = debounce(e => { S.search = e.target.value; S.page = 1; run(); });
$('#bF').onclick = () => { $('#pF').hidden = !$('#pF').hidden; loadVals(); };

// grid
let runId = 0, valId = 0;
async function run() {
  const my = ++runId;
  const r = await fetch('/api/query', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(spec())});
  const j = await r.json(); if (my !== runId) return; if (!r.ok) return msg(j.error); msg('');
  $('#grid').innerHTML = '<thead><tr>' + j.columns.map(c => {
    const on = S.sort && S.sort.col === c; const tp = pivotOn() ? '' : (sheet().cols.find(x => x.name === c) || {}).type, ty = tp ? `<small class="ty" title="Detected type: ${tp}">${{number: '123', text: 'abc', date: 'date', bool: 't/f'}[tp]}</small>` : ''; const fb = !pivotOn() && sheet().cols.some(x => x.name === c) ? `<button class="fb${S.picks[c] ? ' on' : ''}" data-f="${esc(c)}" aria-label="Pick values in ${esc(c)}">▾</button>` : '';
    return `<th data-c="${esc(c)}">${esc(c)}${on ? (S.sort.dir === 'desc' ? ' ▼' : ' ▲') : ''}${ty}${fb}</th>`;
  }).join('') + '</tr></thead><tbody>' + j.rows.map(r => '<tr>' + r.map((v, k) => `<td${typeof v === 'number' ? ' class="n"' : ''}>${esc(typeof v === 'number' ? v.toLocaleString(undefined, {maximumFractionDigits: 6, useGrouping: j.grouped && k >= S.pivot.rows.length}) : v)}</td>`).join('') + '</tr>').join('') + (j.rows.length ? '' : `<tr><td colspan="${j.columns.length}">No rows match. <button class="btn" data-clear>Clear all filters</button></td></tr>`) + '</tbody>';
  $('#count').textContent = j.grouped ? `${(j.total - (S.pivot.totals ? 1 : 0)).toLocaleString()} rows` : `${j.total.toLocaleString()} of ${sheet().rows.toLocaleString()} rows`;
  $('#pager').innerHTML = j.pages > 1 ? `<button class="btn" id="pv" ${j.page < 2 ? 'disabled' : ''}>Previous</button><span>Page ${j.page} of ${j.pages}</span><button class="btn" id="nx" ${j.page >= j.pages ? 'disabled' : ''}>Next</button>` : '';
  $('#pdfBtn').disabled = !j.grouped; $('#bF').classList.toggle('on', spec().filters.length > 0 || spec().picks.length > 0); $('#bP').classList.toggle('on', pivotOn()); loadVals();
}
$('#pager').onclick = e => { if (e.target.id === 'pv') S.page--; else if (e.target.id === 'nx') S.page++; else return; run(); };
$('#grid').onclick = e => {
  const fb = e.target.closest('.fb');
  if (fb) { $('#vcol').value = fb.dataset.f; $('#pF').hidden = false; loadVals(); return; }
  const c = e.target.closest('th')?.dataset.c; if (!c) return;
  S.sort = !S.sort || S.sort.col !== c ? {col: c, dir: 'asc'} : S.sort.dir === 'asc' ? {col: c, dir: 'desc'} : null; S.page = 1; run();
};

// filters
const optv = (name, sel) => `<option value="${esc(name)}"${name === sel ? ' selected' : ''}>${esc(name)}</option>`;  // explicit value: names with extra spaces must match exactly
const colOpts = sel => sheet().cols.map(c => optv(c.name, sel)).join('');
function addFilter() { S.filters.push({join: 'AND', col: sheet().cols[0].name, op: numCol(sheet().cols[0].name) ? 'eq' : 'contains', value: ''}); drawF(); }
function drawF() {
  $('#fconds').innerHTML = S.filters.map((f, i) => `<div class="frow" data-i="${i}">${i ? `<select data-k="join"><option${f.join === 'AND' ? ' selected' : ''}>AND</option><option${f.join === 'OR' ? ' selected' : ''}>OR</option></select>` : '<span class="muted">Where</span>'}
  <select data-k="col">${colOpts(f.col)}</select>
  <select data-k="op">${opsFor(f.col).map(k => `<option value="${k}"${k === f.op ? ' selected' : ''}>${OPS[k]}</option>`).join('')}</select>
  <input data-k="value" value="${esc(f.value)}" placeholder="Value" ${['empty', 'filled'].includes(f.op) ? 'disabled' : ''}>
  <button class="btn" data-rm="${i}" aria-label="Remove condition">Remove</button></div>`).join('') +
  '<div class="frow"><button class="btn" id="addF">Add condition</button><button class="btn" data-clear>Clear all filters</button><small class="muted">AND is evaluated before OR.</small></div>';
}
const filt = debounce(() => { S.page = 1; run(); });
$('#pF').addEventListener('input', e => { const k = e.target.dataset.k; if (!k) return; const f = S.filters[+e.target.closest('.frow').dataset.i]; f[k] = e.target.value;
  if (k === 'col' && !opsFor(f.col).includes(f.op)) f.op = opsFor(f.col)[0];  // keep the operator valid for the column type
  if (k === 'op' || k === 'col') drawF(); filt(); });
$('#pF').addEventListener('click', e => {
  if (e.target.id === 'addF') return addFilter();
  if (e.target.dataset.rm !== undefined) { S.filters.splice(+e.target.dataset.rm, 1); drawF(); S.page = 1; run(); }
});

function clearAll() {
  Object.assign(S, {search: '', filters: [], picks: {}, page: 1});
  $('#search').value = ''; $('#vq').value = ''; drawF(); run();
}
document.addEventListener('click', e => { if (e.target.closest('[data-clear]')) clearAll(); });

// value list (pick values, like Excel's filter list)
async function loadVals() {
  const col = $('#vcol').value;
  if ($('#pF').hidden || !WS.token || !col) return;
  const my = ++valId;
  const r = await post('/api/values', {...spec(), col, q: $('#vq').value}), j = await r.json();
  if (my !== valId) return;
  if (!r.ok) return msg(j.error);
  const p = S.picks[col], has = v => p && (v === null ? p.blank : p.vals.includes(v)), box = $('#vlist'), top = box.scrollTop;
  box.innerHTML = j.values.map(([v, n]) => `<label><input type="checkbox" data-blank="${v === null ? 1 : 0}" data-v="${v === null ? '' : esc(v)}"${!p || (p.mode === 'in') === !!has(v) ? ' checked' : ''}><span>${v === null ? '(Blank)' : esc(v)}</span><small class="muted">${n.toLocaleString()}</small></label>`).join('')
    + (j.truncated ? '<small class="muted">Showing the first 1,000 values. Type in the search box to narrow the list.</small>' : '') || '<small class="muted">No values.</small>';
  box.scrollTop = top;
}
$('#vlist').addEventListener('change', e => {
  const col = $('#vcol').value, t = e.target;
  const p = S.picks[col] || (S.picks[col] = {mode: 'out', vals: [], blank: false});
  const member = p.mode === 'in' ? t.checked : !t.checked;  // 'in' lists shown values, 'out' lists hidden ones
  if (t.dataset.blank === '1') p.blank = member;
  else p.vals = member ? [...new Set([...p.vals, t.dataset.v])] : p.vals.filter(x => x !== t.dataset.v);
  if (p.mode === 'out' && !p.vals.length && !p.blank) delete S.picks[col];
  S.page = 1; run();
});
$('#vcol').onchange = loadVals;
$('#vq').oninput = debounce(loadVals);
$('#vall').onclick = () => { delete S.picks[$('#vcol').value]; S.page = 1; run(); };
$('#vnone').onclick = () => { S.picks[$('#vcol').value] = {mode: 'in', vals: [], blank: false}; S.page = 1; run(); };

const FN = {sum: 'Sum', avg: 'Average', min: 'Minimum', max: 'Maximum'};

// pivot table
const defNum = () => (sheet().cols.find(c => c.numeric) || sheet().cols[0]).name;
const chips = (list, key, attr) => list.map((c, i) => `<span class="chip">${esc(c)}<button ${attr}="${key === undefined ? i : key + ':' + i}" aria-label="Remove ${esc(c)}">×</button></span>`).join('');
function drawP() {
  const cols = sheet().cols, P = S.pivot, FNP = {count: 'Count', ...FN};
  const add = (id, used, label) => `<select id="${id}" aria-label="${label}"><option value="">${label}…</option>${cols.filter(c => !used.includes(c.name)).map(c => optv(c.name, '')).join('')}</select>`;
  $('#pP').innerHTML = `<div class="frow"><b>Rows</b>${chips(P.rows, undefined, 'data-pr')}${add('addPR', P.rows, 'Add row field')}</div>
  <div class="frow"><b>Columns</b>${chips(P.cols, undefined, 'data-pc')}${add('addPC', P.cols, 'Add column field')}</div>
  <b>Values</b>
  ${P.values.map((t, i) => `<div class="frow" data-i="${i}"><select data-k="fn" aria-label="Function">${Object.entries(FNP).map(([k, v]) => `<option value="${k}"${k === t.fn ? ' selected' : ''}>${v}</option>`).join('')}</select>
  ${t.fn !== 'count' ? `<span class="muted">of</span>${chips(t.cols, i, 'data-pvc')}<select data-k="addvc" aria-label="Add column"><option value="">Add column…</option>${cols.filter(c => !t.cols.includes(c.name)).map(c => optv(c.name, '')).join('')}</select>` : ''}
  ${P.values.length > 1 ? `<button class="btn" data-pv="${i}" aria-label="Remove value">Remove</button>` : ''}</div>`).join('')}
  <div class="frow"><button class="btn" id="addV">Add value</button><button class="btn" data-pclear>Clear pivot</button>
  <label><input type="checkbox" id="ptot"${P.totals ? ' checked' : ''}> Show grand totals</label></div>
  <small class="muted">Pick as many row fields, column fields and value columns as you need.</small>`;
}
$('#bP').onclick = () => $('#pP').hidden = !$('#pP').hidden;
$('#pP').addEventListener('change', e => {
  const t = e.target, P = S.pivot;
  if (t.id === 'addPR' && t.value) P.rows.push(t.value);
  else if (t.id === 'addPC' && t.value) P.cols.push(t.value);
  else if (t.id === 'ptot') P.totals = t.checked;
  else if (t.dataset.k) {
    const v = P.values[+t.closest('.frow').dataset.i];
    if (t.dataset.k === 'fn') { v.fn = t.value; if (v.fn !== 'count' && !v.cols.length) v.cols = [defNum()]; }
    else if (t.value) v.cols.push(t.value);
  } else return;
  drawP(); run();
});
$('#pP').addEventListener('click', e => {
  const d = e.target.dataset;
  if (d.pr !== undefined) S.pivot.rows.splice(+d.pr, 1);
  else if (d.pc !== undefined) S.pivot.cols.splice(+d.pc, 1);
  else if (d.pvc !== undefined) { const [i, k] = d.pvc.split(':').map(Number); S.pivot.values[i].cols.splice(k, 1); }
  else if (d.pv !== undefined) S.pivot.values.splice(+d.pv, 1);
  else if (e.target.id === 'addV') S.pivot.values.push({fn: 'sum', cols: [defNum()]});
  else if (d.pclear !== undefined) S.pivot = newPivot();
  else return;
  drawP(); run();
});

// export
$('#exp').addEventListener('click', async e => {
  const fmt = e.target.dataset.fmt; if (!fmt) return;
  const r = await fetch('/api/export', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({...spec(), fmt, scope: document.querySelector('[name=scope]:checked').value})});
  if (!r.ok) return msg((await r.json()).error);
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(await r.blob()), download: `${sheet().name}.${fmt}`});
  a.click(); URL.revokeObjectURL(a.href); $('#exp').open = false;
});


// close the export menu when tapping elsewhere or pressing Escape
document.addEventListener('click', e => { if (!e.target.closest('#exp')) $('#exp').open = false; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') $('#exp').open = false; });
WS.init();
