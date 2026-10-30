// The workspace: the files you open, remembered across pages. Upload once, then use every tool on the same file.
const WS = (() => {
  const W = {token: null, files: [], file: null, sheet: null}, subs = [];
  const KEY = 'gg-ws', ACCEPT = '.xlsx,.xlsm,.xls,.xlsb,.ods,.csv,.tsv,.txt';
  const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } };
  const emit = () => { try { localStorage.setItem(KEY, JSON.stringify({t: W.token, f: W.file, s: W.sheet})); } catch (e) {} subs.forEach(fn => fn(W)); };
  W.fileMeta = (id = W.file) => W.files.find(f => f.id === id);
  W.sheetMeta = (fid = W.file, sid = W.sheet) => { const f = W.fileMeta(fid); return f && f.sheets.find(s => s.id === sid); };
  W.params = () => ({ws: W.token, file: W.file, sheet: W.sheet});
  W.on = fn => { subs.push(fn); };
  W.key = () => { const s = W.sheetMeta(); return s ? `${W.file}:${W.sheet}:${s.hdr}:${s.rows}:${s.cols.map(c => c.name + c.type).join('|')}` : ''; };  // changes when the data a page shows changes

  function apply(st, pickFile) {
    W.token = st.ws; W.files = st.files;
    if (pickFile != null && W.fileMeta(pickFile)) { W.file = pickFile; W.sheet = W.fileMeta(pickFile).sheets[0].id; }
    else if (!W.sheetMeta()) { const f = W.files[0]; W.file = f ? f.id : null; W.sheet = f ? f.sheets[0].id : null; }
  }
  W.init = async () => {
    const s = read();
    if (s.t) {
      try { const r = await post('/api/ws/state', {ws: s.t}), j = await r.json(); if (r.ok) { W.file = s.f; W.sheet = s.s; apply(j); } } catch (e) {}
    }
    emit();
  };
  W.adopt = (st, pick) => { apply(st, pick); emit(); };
  W.select = (fid, sid) => { const f = W.fileMeta(fid); if (f) { W.file = fid; W.sheet = sid != null ? sid : f.sheets[0].id; emit(); } };
  W.upload = async file => {
    msg(''); const fd = new FormData(); fd.append('file', file); if (W.token) fd.append('ws', W.token);
    loadUI.show('Uploading ' + file.name);
    let x; try { x = await sendForm('/api/ws/upload', fd); } catch (e) { loadUI.hide(); msg('Upload failed. Check that the server is still running.'); return false; }
    loadUI.hide();
    if (!x.ok) { msg(x.j.error || 'This file could not be read.'); return false; }
    apply(x.j, x.j.file); emit(); return true;
  };
  W.setHeader = async (row, fid = W.file, sid = W.sheet) => {  // read the sheet again with another header row; types are detected again
    row = Math.max(1, parseInt(row) || 1); const m = W.sheetMeta(fid, sid);
    if (!m || m.hdr === row) { emit(); return false; }
    loadUI.show('Reading sheet…'); loadUI.wait('');
    const j = await api('/api/ws/header', {ws: W.token, file: fid, sheet: sid, row}); loadUI.hide();
    if (j) apply(j);
    emit(); return !!j;
  };
  W.remove = async fid => { const j = await api('/api/ws/remove', {ws: W.token, file: fid}); if (j) { apply(j); emit(); } };
  W.pick = () => { const i = Object.assign(document.createElement('input'), {type: 'file', accept: ACCEPT}); i.onchange = () => { if (i.files[0]) W.upload(i.files[0]); }; i.click(); };
  W.sample = () => {  // a small generated dataset so everything can be tried without a file
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    const regions = ['North', 'South', 'East', 'West'], items = ['Laptop', 'Monitor', 'Keyboard', 'Mouse', 'Dock'], rows = ['Region,Product,Year,Quarter,Units,Revenue'];
    for (let i = 0; i < 240; i++) { const u = 1 + Math.floor(rnd() * 60); rows.push([regions[i % 4], items[Math.floor(rnd() * 5)], 2023 + (i % 3), 'Q' + (1 + Math.floor(rnd() * 4)), u, (u * (20 + rnd() * 380)).toFixed(2)].join(',')); }
    return W.upload(new File([rows.join('\n')], 'sample-sales.csv', {type: 'text/csv'}));
  };

  // drop area that adds a file to the workspace
  W.dropzone = (root, {title = 'Choose a file', hint = 'Drop an Excel or CSV file here, or click to choose one.'} = {}) => {
    root.innerHTML = `<div class="glass dzbox" tabindex="0" role="button" aria-label="${esc(title)}"><b>${esc(title)}</b><p class="muted">${esc(hint)}</p><input type="file" accept="${ACCEPT}" hidden></div>`;
    const dz = root.firstElementChild, input = dz.querySelector('input');
    dz.onclick = e => { if (e.target !== input) input.click(); };
    dz.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } };
    input.onchange = () => { const f = input.files[0]; input.value = ''; if (f) W.upload(f); };
    dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); };
    dz.ondragleave = () => dz.classList.remove('over');
    dz.ondrop = e => { e.preventDefault(); e.stopPropagation(); dz.classList.remove('over'); if (e.dataTransfer.files[0]) W.upload(e.dataTransfer.files[0]); };
  };
  document.addEventListener('dragover', e => e.preventDefault());
  document.addEventListener('drop', e => { e.preventDefault(); const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) W.upload(f); });  // a drop anywhere else adds the file too

  // bar with file, sheet and header row controls
  W.bar = root => {
    const draw = () => {
      const f = W.fileMeta(), s = W.sheetMeta();
      root.hidden = !s; if (!s) { root.innerHTML = ''; return; }
      root.innerHTML = `${W.files.length > 1 ? `<select id="wsFile" aria-label="File" title="File">${W.files.map(x => `<option value="${x.id}"${x.id === W.file ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</select>` : `<b class="fn" title="${esc(f.name)}">${esc(f.name)}</b>`}
      ${f.sheets.length > 1 ? `<select id="wsSheet" aria-label="Sheet" title="Sheet">${f.sheets.map(x => `<option value="${x.id}"${x.id === W.sheet ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</select>` : ''}
      <label class="wsitem">Header row <input id="wsHdr" type="number" min="1" value="${s.hdr}"${f.derived ? ' disabled title="Cleaned files have their own header"' : ''}></label>
      <span class="muted wsmeta">${s.rows.toLocaleString()} rows · ${s.cols.length} columns</span>
      <span class="wsbtns"><button class="btn small" id="wsAdd">Add file</button><button class="btn small" id="wsRm">Remove</button></span>`;
    };
    root.classList.add('glass', 'wsbar');
    root.addEventListener('change', e => {
      const t = e.target;
      if (t.id === 'wsFile') W.select(+t.value); else if (t.id === 'wsSheet') W.select(W.file, +t.value); else if (t.id === 'wsHdr') W.setHeader(t.value);
    });
    root.addEventListener('click', e => { if (e.target.id === 'wsAdd') W.pick(); else if (e.target.id === 'wsRm') W.remove(W.file); });
    W.on(draw);
  };
  return W;
})();
