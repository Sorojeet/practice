// Data Cleaner: build a list of cleaning steps, run them on the server, preview and download the result.
const yes = [['', 'Choose…']];
const colList = () => (WS.sheetMeta() ? WS.sheetMeta().cols.map(c => c.name) : []);
const COLS = {k: 'cols', t: 'cols', label: 'Columns (none selected = all that apply)'};
const OPS = {
  trim: {label: 'Trim spaces', help: 'Removes spaces at the start and end of text cells.', fields: [COLS, {k: 'collapse', t: 'bool', label: 'Also shrink repeated spaces inside text'}]},
  empty_rows: {label: 'Remove empty rows', help: 'Deletes rows where every cell is empty or blank.', fields: []},
  empty_cols: {label: 'Remove empty columns', help: 'Deletes columns that have no values at all.', fields: []},
  duplicates: {label: 'Remove duplicates', help: 'Deletes repeated rows. Pick columns to match on, or leave empty to compare whole rows.', fields: [COLS, {k: 'keep', t: 'select', label: 'Keep', options: () => [['first', 'First occurrence'], ['last', 'Last occurrence']]}]},
  case: {label: 'Change text case', help: 'Changes the case of text cells.', fields: [COLS, {k: 'mode', t: 'select', label: 'Change to', options: () => [['lower', 'lowercase'], ['upper', 'UPPERCASE'], ['title', 'Title Case']]}]},
  missing: {label: 'Handle missing values', help: 'Blank cells count as missing. Choose what to do with them.', fields: [COLS,
    {k: 'action', t: 'select', label: 'Action', rerender: true, options: () => [['drop', 'Remove rows with missing values'], ['value', 'Fill with a value'], ['mean', 'Fill with the average (number columns)'], ['median', 'Fill with the median (number columns)'], ['mode', 'Fill with the most common value'], ['ffill', 'Fill down from the cell above'], ['bfill', 'Fill up from the cell below']]},
    {k: 'value', t: 'text', label: 'Value to fill in', show: st => st.action === 'value'}]},
  replace: {label: 'Find and replace', help: 'Replaces text inside text cells.', fields: [{k: 'find', t: 'text', label: 'Find'}, {k: 'replace', t: 'text', label: 'Replace with (can be empty)'}, COLS,
    {k: 'case', t: 'bool', label: 'Match upper and lower case exactly'}, {k: 'whole', t: 'bool', label: 'Only replace when the whole cell matches'}]},
  convert: {label: 'Convert column type', help: 'Converts one column. Values that cannot be converted become empty and are counted.', fields: [
    {k: 'col', t: 'select', label: 'Column', options: () => yes.concat(colList().map(c => [c, c]))},
    {k: 'to', t: 'select', label: 'Convert to', rerender: true, options: () => [['number', 'Number'], ['text', 'Text'], ['date', 'Date']]},
    {k: 'datefmt', t: 'select', label: 'Date format in the file', show: st => st.to === 'date', options: () => [['iso', 'YYYY-MM-DD'], ['dmy', 'DD/MM/YYYY'], ['mdy', 'MM/DD/YYYY'], ['dmy-', 'DD-MM-YYYY'], ['ymd/', 'YYYY/MM/DD']]}]},
  rename: {label: 'Clean column names', help: 'Tidies the header row.', fields: [{k: 'style', t: 'select', label: 'Style', options: () => [['trim', 'Trim spaces'], ['snake', 'snake_case'], ['lower', 'lowercase'], ['upper', 'UPPERCASE'], ['title', 'Title Case']]}]},
  drop_cols: {label: 'Remove columns', help: 'Deletes the columns you pick.', fields: [{k: 'cols', t: 'cols', label: 'Columns to remove'}]},
};
let steps = [], ranOnce = false;

WS.dropzone($('#up'), {title: 'Choose a file to clean'});
WS.bar($('#wsbar'));
let seen = '';
function render() {  // runs whenever the workspace changes: another file, sheet or header row starts fresh
  const s = WS.sheetMeta(); $('#up').hidden = !!s; $('#work').hidden = !s;
  if (WS.key() === seen) return;
  seen = WS.key(); steps = []; ranOnce = false; $('#results').hidden = true;
  if (s) { drawSteps(); drawCols(); }
}
WS.on(render);

function drawCols() {
  const cols = WS.sheetMeta().cols;
  $('#colsum').innerHTML = `<h2>Columns in this sheet</h2><div class="chips">${cols.map(c => `<span class="chip ghost">${esc(c.name)}<small class="ty">${TY[c.type]}</small></span>`).join('')}</div>`;
}
const fieldHTML = (st, f, i) => {
  const v = st[f.k];
  if (f.t === 'cols') return `<div class="field"><span class="lab">${esc(f.label)}</span><div class="frow" data-cp="${f.k}"></div></div>`;
  if (f.t === 'bool') return `<label class="field chk"><input type="checkbox" data-k="${f.k}"${v ? ' checked' : ''}> ${esc(f.label)}</label>`;
  if (f.t === 'select') return `<label class="field"><span class="lab">${esc(f.label)}</span><select data-k="${f.k}">${f.options().map(([val, lab]) => `<option value="${esc(val)}"${val === v ? ' selected' : ''}>${esc(lab)}</option>`).join('')}</select></label>`;
  return `<label class="field"><span class="lab">${esc(f.label)}</span><input type="text" data-k="${f.k}" value="${esc(v ?? '')}"></label>`;
};
function drawSteps() {
  $('#steps').innerHTML = steps.length ? steps.map((st, i) => {
    const o = OPS[st.op];
    return `<div class="step" data-i="${i}"><div class="stephead"><b>${i + 1}. ${esc(o.label)}</b><button class="btn" data-rm="${i}" aria-label="Remove step ${i + 1}">Remove</button></div><p class="muted">${esc(o.help)}</p>${o.fields.filter(f => !f.show || f.show(st)).map(f => fieldHTML(st, f, i)).join('')}</div>`;
  }).join('') : '<p class="muted">No steps yet. Add one from the list, or use the quick clean preset.</p>';
  steps.forEach((st, i) => OPS[st.op].fields.forEach(f => {
    const el = f.t === 'cols' && $(`#steps [data-i="${i}"] [data-cp="${f.k}"]`);
    if (el) ColPicker(el, {onChange: s => { st[f.k] = s.slice(); }}).set(colList(), st[f.k] || []);
  }));
}
function addStep(op, preset = {}) {
  const st = {op};
  OPS[op].fields.forEach(f => { st[f.k] = f.t === 'cols' ? [] : f.t === 'bool' ? false : f.t === 'select' ? f.options()[0][0] : ''; });
  steps.push(Object.assign(st, preset)); drawSteps();
}
$('#addOp').innerHTML = '<option value="">Add a step…</option>' + Object.entries(OPS).map(([k, o]) => `<option value="${k}">${esc(o.label)}</option>`).join('');
$('#addOp').onchange = e => { if (e.target.value) addStep(e.target.value); e.target.value = ''; };
$('#quick').onclick = () => { steps = []; addStep('trim', {collapse: true}); addStep('empty_rows'); addStep('duplicates'); };
$('#clear').onclick = () => { steps = []; drawSteps(); };
$('#steps').addEventListener('click', e => { const b = e.target.closest('[data-rm]'); if (b) { steps.splice(+b.dataset.rm, 1); drawSteps(); } });
$('#steps').addEventListener('input', e => {
  const k = e.target.dataset.k, el = e.target.closest('.step'); if (!k || !el) return;
  const st = steps[+el.dataset.i], f = OPS[st.op].fields.find(x => x.k === k);
  st[k] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
  if (f && f.rerender && e.type !== 'input') drawSteps();
});
$('#steps').addEventListener('change', e => { const k = e.target.dataset.k, el = e.target.closest('.step'); if (k && el && OPS[steps[+el.dataset.i].op].fields.some(f => f.k === k && f.rerender)) drawSteps(); });

$('#run').onclick = async () => {
  if (!steps.length) return msg('Add at least one cleaning step.');
  loadUI.show('Cleaning data'); loadUI.wait('');
  const j = await api('/api/tools/clean/run', {...WS.params(), steps});
  loadUI.hide(); if (!j) return;
  ranOnce = true; msg('');
  $('#results').hidden = false;
  $('#sum').innerHTML = metric(`${j.before.rows.toLocaleString()} → ${j.after.rows.toLocaleString()}`, 'Rows') + metric(`${j.before.cols} → ${j.after.cols}`, 'Columns');
  $('#log').innerHTML = '<ol>' + j.log.map(l => `<li><b>${esc(l.label)}.</b> ${esc(l.message)}</li>`).join('') + '</ol>';
  $('#grid').innerHTML = tableHTML(j.columns.map(c => c.name), j.rows, j.columns.map(c => c.type));
  $('#note').textContent = j.truncated ? `Showing the first ${j.rows.length} of ${j.after.rows.toLocaleString()} rows. The download contains every row.` : `${j.after.rows.toLocaleString()} rows`;
  $('#results').scrollIntoView({behavior: 'smooth', block: 'start'});
};
const dl = fmt => download('/api/tools/clean/download', {ws: WS.token, fmt}, `cleaned.${fmt}`);
$('#dxlsx').onclick = () => dl('xlsx');
$('#dcsv').onclick = () => dl('csv');
$('#save').onclick = async () => {  // keep the cleaned sheet as a new file that every tool can use
  const r = await api('/api/tools/clean/save', {ws: WS.token});
  if (r) { WS.adopt(r, r.file); msg('Saved. The cleaned data is now your open file in the viewer and every tool.', true); }
};
WS.init();
