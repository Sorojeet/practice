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
