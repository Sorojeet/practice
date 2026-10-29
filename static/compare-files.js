// Compare Files: load two files, choose how rows are matched, then review added, removed and changed rows.
let result = null, tab = 'changed';
const names = u => (u && u.sheet() ? u.sheet().cols.map(c => c.name) : []);
const common = () => names(A).filter(c => names(B).includes(c));
const keysPick = ColPicker($('#keys'), {label: 'Add key column…'});
const ignorePick = ColPicker($('#ignore'), {label: 'Ignore a column…'});

function changed() {
  result = null; $('#results').hidden = true;
  const ready = A.info && B.info;
  $('#opts').hidden = !ready;
  if (!ready) return;
  const cm = common();
  keysPick.set(cm, []); ignorePick.set(cm, []);
  $('#shared').textContent = cm.length ? `${cm.length} column(s) have the same name in both files.` : 'These files share no column names, so they cannot be compared.';
  $('#go').disabled = !cm.length;
}
const A = Uploader($('#upA'), {title: 'File A: the original', hint: 'The older or reference file.', onLoad: changed});
const B = Uploader($('#upB'), {title: 'File B: the new version', hint: 'The file to compare against A.', onLoad: changed});

const side = u => ({token: u.info.token, sheet: u.sheetName, name: u.info.name});
$('#go').onclick = async () => {
  loadUI.show('Comparing files'); loadUI.wait('');
  const j = await api('/api/tools/compare/run', {a: side(A), b: side(B), keys: keysPick.selected, ignore: ignorePick.selected, trim: $('#trim').checked, ignore_case: $('#icase').checked});
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
$('#dxlsx').onclick = () => download('/api/tools/compare/download', {token: result.token, fmt: 'xlsx', which: 'all'}, 'differences.xlsx');
$('#dcsv').onclick = () => download('/api/tools/compare/download', {token: result.token, fmt: 'csv', which: tab}, `${tab}.csv`);
