// Compare Files: pick two files from the workspace (a second one can be added here), choose how rows are matched, review the differences.
let result = null, tab = 'changed', sel = {a: null, b: null}, count = 0, sig = '';
const keysPick = ColPicker($('#keys'), {label: 'Add key column…'});
const ignorePick = ColPicker($('#ignore'), {label: 'Ignore a column…'});
const meta = s => s && WS.sheetMeta(s.file, s.sheet);
const names = s => (meta(s) ? meta(s).cols.map(c => c.name) : []);
const common = () => names(sel.a).filter(c => names(sel.b).includes(c));

function fix() {  // keep both picks valid; a newly added file becomes B
  const F = WS.files, ok = s => s && meta(s);
  if (!ok(sel.a)) sel.a = WS.sheetMeta() ? {file: WS.file, sheet: WS.sheet} : null;
  if (F.length > count || !ok(sel.b) || (sel.b && sel.a && sel.b.file === sel.a.file && F.length > 1)) {
    const other = [...F].reverse().find(f => !sel.a || f.id !== sel.a.file);
    sel.b = other ? {file: other.id, sheet: other.sheets[0].id} : null;
  }
  count = F.length;
}
function sideHTML(key, title, hint) {
  const s = sel[key];
  if (!s) return `<h2>${title}</h2>` + (key === 'a' || sel.a ? `<div data-dz="${key}"></div>` : '<p class="muted">Add File A first.</p>');
  const f = WS.fileMeta(s.file), m = meta(s);
  return `<h2>${title}</h2><p class="muted">${hint}</p>
  <label class="field"><span class="lab">File</span><select data-side="${key}" data-k="file">${WS.files.map(x => `<option value="${x.id}"${x.id === s.file ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>
  ${f.sheets.length > 1 ? `<label class="field"><span class="lab">Sheet</span><select data-side="${key}" data-k="sheet">${f.sheets.map(x => `<option value="${x.id}"${x.id === s.sheet ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</select></label>` : ''}
  <label class="field"><span class="lab">Header row</span><input type="number" min="1" data-side="${key}" data-k="hdr" value="${m.hdr}"${f.derived ? ' disabled' : ''}></label>
  <p class="muted">${m.rows.toLocaleString()} rows · ${m.cols.length} columns</p>
  <div class="frow"><button class="btn" data-add>Add another file</button></div>`;
}
function render() {
  fix();
  $('#sideA').innerHTML = sideHTML('a', 'File A: the original', 'The older or reference file.');
  $('#sideB').innerHTML = sideHTML('b', 'File B: the new version', 'The file to compare against A.');
  document.querySelectorAll('[data-dz]').forEach(el => WS.dropzone(el, {title: el.dataset.dz === 'a' ? 'Choose File A' : 'Choose File B', hint: 'Drop an Excel or CSV file here, or click to choose one.'}));
  const next = JSON.stringify([sel.a, sel.b, [sel.a, sel.b].map(s => meta(s) && meta(s).hdr + names(s).join('|'))]);
  const ready = !!(meta(sel.a) && meta(sel.b)), cm = ready ? common() : [];
  $('#opts').hidden = !ready;
  if (next === sig) return;
  sig = next; result = null; $('#results').hidden = true;
  if (!ready) return;
  keysPick.set(cm, []); ignorePick.set(cm, []);
  $('#shared').textContent = !cm.length ? 'These sheets share no column names, so they cannot be compared. Check the header rows.'
    : sel.a.file === sel.b.file && sel.a.sheet === sel.b.sheet ? 'Both sides are the same sheet. Pick a different file or sheet for one side.' : `${cm.length} column(s) have the same name in both sheets.`;
  $('#go').disabled = !cm.length;
}
WS.on(render);
$('#sides').addEventListener('change', e => {
  const t = e.target, side = t.dataset.side, k = t.dataset.k; if (!side) return;
  if (k === 'file') sel[side] = {file: +t.value, sheet: WS.fileMeta(+t.value).sheets[0].id};
  else if (k === 'sheet') sel[side].sheet = +t.value;
  else if (k === 'hdr') return WS.setHeader(t.value, sel[side].file, sel[side].sheet);
  render();
});
$('#sides').addEventListener('click', e => { if (e.target.closest('[data-add]')) WS.pick(); });

$('#go').onclick = async () => {
  loadUI.show('Comparing files'); loadUI.wait('');
  const j = await api('/api/tools/compare/run', {ws: WS.token, a: sel.a, b: sel.b, keys: keysPick.selected, ignore: ignorePick.selected, trim: $('#trim').checked, ignore_case: $('#icase').checked});
  loadUI.hide(); if (!j) return;
  result = j; msg(''); tab = j.summary.changed ? 'changed' : j.summary.added ? 'added' : 'removed'; draw();
  $('#results').hidden = false; $('#results').scrollIntoView({behavior: 'smooth', block: 'start'});
};

function draw() {
  const s = result.summary, notes = [];
  $('#metrics').innerHTML = metric(s.rows_a, 'Rows in A') + metric(s.rows_b, 'Rows in B') + metric(s.added, 'Added', 'good') + metric(s.removed, 'Removed', 'bad') + metric(s.changed, 'Changed', 'warn') + metric(s.same, 'Unchanged');
  notes.push(s.mode === 'key' ? `Rows were matched by: ${s.keys.join(', ')}.` : 'Rows were matched by position (row 1 with row 1, and so on). Pick key columns above to match by an ID instead.');
  if (s.only_a.length) notes.push(`Columns only in A (not compared): ${s.only_a.join(', ')}.`);
  if (s.only_b.length) notes.push(`Columns only in B (not compared): ${s.only_b.join(', ')}.`);
  if (s.dups_a || s.dups_b) notes.push(`Some keys repeat (${s.dups_a} row(s) in A, ${s.dups_b} in B). Repeated keys were matched in order.`);
  if (!s.added && !s.removed && !s.changed) notes.push('No differences found in the compared columns.');
  $('#notes').innerHTML = notes.map(n => `<li>${esc(n)}</li>`).join('');
  $('#coldiff').innerHTML = s.col_diffs.length ? '<h3>Changed cells by column</h3><div class="chips">' + s.col_diffs.map(d => `<span class="chip ghost">${esc(d.column)} <b>${d.count.toLocaleString()}</b></span>`).join('') + '</div>' : '';
  $('#tabs').innerHTML = ['changed', 'added', 'removed'].map(t => `<button role="tab" aria-selected="${t === tab}" data-t="${t}">${t[0].toUpperCase() + t.slice(1)} (${result[t].total.toLocaleString()})</button>`).join('');
  const r = result[tab];
  $('#grid').innerHTML = tableHTML(r.columns, r.rows);
  $('#note').textContent = r.total > r.rows.length ? `Showing the first ${r.rows.length} of ${r.total.toLocaleString()} rows. The download has every row.` : `${r.total.toLocaleString()} row(s)`;
  $('#dcsv').textContent = `Download ${tab} (csv)`;
}
$('#tabs').addEventListener('click', e => { const b = e.target.closest('[data-t]'); if (b) { tab = b.dataset.t; draw(); } });
$('#dxlsx').onclick = () => download('/api/tools/compare/download', {ws: WS.token, fmt: 'xlsx', which: 'all'}, 'differences.xlsx');
$('#dcsv').onclick = () => download('/api/tools/compare/download', {ws: WS.token, fmt: 'csv', which: tab}, `${tab}.csv`);
WS.init();
