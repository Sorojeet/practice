// Building blocks shared by the tool pages: file uploader, column picker, table renderer and downloads.
const TY = {number: '123', text: 'abc', date: 'date', bool: 't/f'};

function saveBlob(blob, name) {
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(blob), download: name});
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

async function download(url, body, fallback) {
  loadUI.show('Preparing your file'); loadUI.wait('');
  try {
    const r = await post(url, body);
    if (!r.ok) { let m = 'The download failed.'; try { m = (await r.json()).error || m; } catch (e) {} return msg(m); }
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(r.headers.get('Content-Disposition') || '');
    saveBlob(await r.blob(), m ? decodeURIComponent(m[1]) : fallback);
  } catch (e) { msg('The download failed. Check that the server is still running.'); }
  finally { loadUI.hide(); }
}

async function api(url, body) {  // JSON call that shows server errors in the banner; resolves null on failure
  try {
    const r = await post(url, body), j = await r.json();
    if (!r.ok) { msg(j.error || 'Something went wrong.'); return null; }
    return j;
  } catch (e) { msg('Could not reach the server. Check that it is still running.'); return null; }
}

// ---- uploader: drop area, then a file bar with a sheet picker ----
function Uploader(root, {title, hint, onLoad}) {
  const self = {info: null, sheetName: null, sheet() { return this.info && this.info.sheets.find(s => s.name === this.sheetName); }};
  root.innerHTML = `<div class="glass dzbox" tabindex="0" role="button" aria-label="${esc(title)}"><b>${esc(title)}</b><p class="muted">${esc(hint || 'Drop an Excel or CSV file here, or click to choose one.')}</p><input type="file" accept=".xlsx,.xlsm,.xls,.xlsb,.ods,.csv,.tsv,.txt" hidden></div>
  <div class="glass filebar" hidden><div class="fi"><b class="fn"></b><span class="muted fm"></span></div><select class="sheetsel" aria-label="Sheet"></select><button class="btn rm">Remove</button></div>`;
  const dz = root.querySelector('.dzbox'), input = root.querySelector('input'), bar = root.querySelector('.filebar'), sel = root.querySelector('select');
  const show = () => {
    const s = self.sheet(); dz.hidden = !!self.info; bar.hidden = !self.info;
    if (!self.info) return;
    root.querySelector('.fn').textContent = self.info.name;
    root.querySelector('.fm').textContent = `${s.rows.toLocaleString()} rows · ${s.cols.length} columns`;
    sel.hidden = self.info.sheets.length < 2;
    sel.innerHTML = self.info.sheets.map(x => `<option value="${esc(x.name)}"${x.name === self.sheetName ? ' selected' : ''}>${esc(x.name)}</option>`).join('');
  };
  const clear = () => { if (self.info) post('/api/tools/close', {token: self.info.token}); self.info = self.sheetName = null; };
  async function load(file) {
    msg(''); const fd = new FormData(); fd.append('file', file);
    loadUI.show('Uploading ' + file.name);
    let x; try { x = await sendForm('/api/tools/upload', fd); } catch (e) { loadUI.hide(); return msg('Upload failed. Check that the server is still running.'); }
    loadUI.hide();
    if (!x.ok) return msg(x.j.error || 'This file could not be read.');
    clear(); self.info = x.j; self.sheetName = x.j.sheets[0].name; show(); onLoad(self);
  }
  dz.onclick = () => input.click();
  dz.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } };
  input.onchange = () => { const f = input.files[0]; input.value = ''; if (f) load(f); };
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); };
  dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove('over'); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]); };
  sel.onchange = () => { self.sheetName = sel.value; show(); onLoad(self); };
  root.querySelector('.rm').onclick = () => { clear(); show(); onLoad(null); };
  return self;
}
['dragover', 'drop'].forEach(ev => document.addEventListener(ev, e => e.preventDefault()));  // a missed drop must not open the file

// ---- column picker: chips plus an "add" list ----
function ColPicker(root, {onChange, label = 'Add column…'}) {
  const self = {cols: [], selected: [], set(cols, sel = []) { self.cols = cols; self.selected = sel; draw(); }};
  const draw = () => {
    root.innerHTML = self.selected.map((c, i) => `<span class="chip">${esc(c)}<button data-i="${i}" aria-label="Remove ${esc(c)}">×</button></span>`).join('')
      + `<select aria-label="${esc(label)}"><option value="">${esc(label)}</option>${self.cols.filter(c => !self.selected.includes(c)).map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('')}</select>`;
  };
  root.addEventListener('change', e => { if (e.target.tagName === 'SELECT' && e.target.value) { self.selected.push(e.target.value); draw(); onChange && onChange(self.selected); } });
  root.addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (b) { self.selected.splice(+b.dataset.i, 1); draw(); onChange && onChange(self.selected); } });
  return self;
}

// ---- tables ----
function cellHTML(v) {
  if (v && typeof v === 'object') return `<td class="chg"><del>${esc(v.o)}</del><ins>${esc(v.n)}</ins></td>`;
  if (typeof v === 'number') return `<td class="n">${esc(v.toLocaleString(undefined, {maximumFractionDigits: 6, useGrouping: false}))}</td>`;
  return `<td>${esc(v)}</td>`;
}
function tableHTML(columns, rows, types) {
  const th = columns.map((c, i) => `<th>${esc(c)}${types && types[i] ? `<small class="ty" title="Detected type: ${types[i]}">${TY[types[i]]}</small>` : ''}</th>`).join('');
  const body = rows.map(r => '<tr>' + r.map(cellHTML).join('') + '</tr>').join('') || `<tr><td colspan="${columns.length}">No rows.</td></tr>`;
  return `<thead><tr>${th}</tr></thead><tbody>${body}</tbody>`;
}
const metric = (v, l, cls = '') => `<div class="glass stat ${cls}"><b>${esc(typeof v === 'number' ? v.toLocaleString() : v)}</b><span class="muted">${esc(l)}</span></div>`;
