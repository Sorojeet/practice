// Chart Maker: the server aggregates the data; this file draws the chart as SVG and exports it as PNG, SVG or csv.
const PALS = {
  Gridglass: ['#1f9d5c', '#3b82c4', '#f0a030', '#d9534f', '#8a6bd1', '#17a2b8', '#e0679d', '#7a8793', '#9ac234', '#ff7f50', '#4b8b3b', '#b5832a'],
  Ocean: ['#2563eb', '#0ea5e9', '#14b8a6', '#6366f1', '#22d3ee', '#0f766e', '#4f46e5', '#38bdf8', '#2dd4bf', '#818cf8', '#1d4ed8', '#0891b2'],
  Sunset: ['#ef4444', '#f97316', '#f59e0b', '#ec4899', '#a855f7', '#e11d48', '#fb923c', '#fbbf24', '#d946ef', '#dc2626', '#ea580c', '#c026d3'],
};
const SINGLE_Y = ['scatter', 'pie', 'donut'];
let data = null, svgText = '', dims = [900, 520];

const up = Uploader($('#up'), {title: 'Choose a file to chart', onLoad: u => { data = null; $('#work').hidden = !u; $('#chart').innerHTML = ''; if (u) setup(); }});
const yPick = ColPicker($('#ys'), {label: 'Add value column…', onChange: s => { if (SINGLE_Y.includes($('#type').value) && s.length > 1) { yPick.selected = s.slice(-1); yPick.set(yPick.cols, yPick.selected); } refresh(); }});
const types = () => Object.fromEntries(up.sheet().cols.map(c => [c.name, c.type]));
const opts = (cols, none) => (none ? '<option value="">None</option>' : '') + cols.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');

function setup() {
  const cols = up.sheet().cols, num = cols.filter(c => c.type === 'number').map(c => c.name), cat = cols.filter(c => c.type !== 'number').map(c => c.name);
  $('#x').innerHTML = opts(cols.map(c => c.name)); $('#x').value = (cat[0] || cols[0].name);
  $('#group').innerHTML = opts(cols.map(c => c.name), true);
  yPick.set(num, num.length ? [num[0]] : []);
  $('#agg').value = num.length ? 'sum' : 'count';
  controls(); refresh();
}
function controls() {
  const t = $('#type').value, tp = types(), isDate = tp[$('#x').value] === 'date', hist = t === 'hist', sc = t === 'scatter', pie = t === 'pie' || t === 'donut';
  const numCols = up.sheet().cols.filter(c => c.type === 'number').map(c => c.name);
  const xCols = (hist || sc) ? numCols : up.sheet().cols.map(c => c.name), cur = $('#x').value;
  $('#x').innerHTML = opts(xCols); $('#x').value = xCols.includes(cur) ? cur : (xCols[0] || '');
  const showAgg = !hist && !sc;
  $('#xl').firstChild.textContent = hist ? 'Number column' : sc ? 'X axis (number)' : 'X axis (categories)';
  $('#yw').hidden = hist || (showAgg && ['count'].includes($('#agg').value));
  const allCols = up.sheet().cols.map(c => c.name), ycols = (sc || ['sum', 'avg', 'min', 'max'].includes($('#agg').value)) ? numCols : allCols;
  yPick.set(ycols, yPick.selected.filter(c => ycols.includes(c)));
  $('#aggw').hidden = !showAgg; $('#gw').hidden = hist || pie; $('#pw').hidden = !(showAgg && isDate);
  $('#sw').hidden = !showAgg; $('#lw').hidden = !showAgg; $('#bw').hidden = !hist; $('#stw').hidden = !['bar', 'hbar', 'area'].includes(t);
}
let seq = 0;
async function refresh() {
  controls();
  const t = $('#type').value, ys = yPick.selected.slice(), agg = $('#agg').value, hist = t === 'hist', sc = t === 'scatter';
  if (!hist && !sc && agg !== 'count' && !ys.length) { $('#chart').innerHTML = '<p class="muted center">Choose a value column to chart, or set “Combine values with” to Count.</p>'; return; }
  if (sc && !ys.length) { $('#chart').innerHTML = '<p class="muted center">Choose a number column for the Y axis.</p>'; return; }
  const my = ++seq;
  const j = await api('/api/tools/chart/data', {token: up.info.token, sheet: up.sheetName, type: t, x: $('#x').value, ys, agg, group: $('#group').value || null, part: $('#part').value || null,
    sort: $('#sort').value, limit: +$('#limit').value || 30, bins: +$('#bins').value || 20});
  if (my !== seq) return;
  if (!j) { $('#chart').innerHTML = ''; return; }
  msg(''); data = j; render();
}

// ---------- drawing ----------
const fmt = v => v == null ? '' : Math.abs(v) >= 1e9 ? +(v / 1e9).toFixed(2) + 'B' : Math.abs(v) >= 1e6 ? +(v / 1e6).toFixed(2) + 'M' : Math.abs(v) >= 1e4 ? +(v / 1e3).toFixed(1) + 'k' : (+v.toFixed(2)).toLocaleString();
const cut = (s, n) => { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
function ticks(lo, hi, n = 5) {
  if (lo === hi) { hi = lo + 1; }
  const raw = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag, step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + step / 2; v += step) out.push(+v.toFixed(10));
  return out;
}
const colors = () => { const d = root.dataset.theme === 'dark'; return {bg: d ? '#0b1d14' : '#ffffff', ink: d ? '#e3f5ea' : '#0e2a1b', mut: d ? '#8db5a0' : '#4d6b59', grid: d ? '#21402f' : '#dfece3'}; };
const T = (x, y, s, o = {}) => `<text x="${x}" y="${y}" font-size="${o.size || 12}" fill="${o.fill}" text-anchor="${o.anchor || 'start'}"${o.weight ? ` font-weight="${o.weight}"` : ''}${o.rot ? ` transform="rotate(${o.rot} ${x} ${y})"` : ''}>${esc(s)}</text>`;

function legend(names, pal, C, W, y0) {  // wraps onto several rows; returns markup and its height
  let x = 16, y = y0, out = '';
  names.forEach((n, i) => {
    const w = Math.min(n.length, 24) * 7 + 30;
    if (x + w > W - 10) { x = 16; y += 20; }
    out += `<rect x="${x}" y="${y - 9}" width="11" height="11" rx="3" fill="${pal[i % pal.length]}"/>` + T(x + 16, y, cut(n, 24), {fill: C.ink, size: 12});
    x += w;
  });
  return [out, names.length ? y - y0 + 22 : 0];
}
function cartesian(d, o, W, C, pal) {
  const n = d.labels.length, S = d.series, hz = o.type === 'hbar', line = o.type === 'line', area = o.type === 'area';
  const stacked = o.stacked && S.length > 1 && ['bar', 'hbar', 'area'].includes(o.type);
  const v = (si, i) => S[si].values[i];
  let lo = 0, hi = 0, minv = Infinity;
  for (let i = 0; i < n; i++) {
    if (stacked) { let p = 0, q = 0; S.forEach((_, si) => { const a = v(si, i) || 0; a >= 0 ? p += a : q += a; }); hi = Math.max(hi, p); lo = Math.min(lo, q); }
    else S.forEach((_, si) => { const a = v(si, i); if (a != null) { hi = Math.max(hi, a); lo = Math.min(lo, a); minv = Math.min(minv, a); } });
  }
  if (line && minv !== Infinity && minv > 0) lo = minv - (hi - minv) * 0.1;
  const tk = ticks(lo, hi), ylo = tk[0], yhi = tk[tk.length - 1];
  const title = o.title ? 34 : 14, [lg, lgH] = o.legend && S.length > 1 ? legend(S.map(s => s.name), pal, C, W, title + 14) : ['', 0];
  const T0 = title + lgH + 14, longest = Math.max(...d.labels.map(l => String(l).length), 1);
  const labW = hz ? Math.min(150, longest * 6.5 + 12) : 0;
  const L = hz ? labW + 12 : 58, R = 18, plotW = W - L - R;
  const rot = !hz && (n > 8 || longest * 6.5 > plotW / n - 4), B = hz ? 44 : (rot ? 96 : 56);
  const H = hz ? Math.max(300, T0 + n * (S.length * 14 + 12) + B) : Math.round(Math.min(560, Math.max(320, W * 0.58)));
  const plotH = H - T0 - B, band = (hz ? plotH : plotW) / n;
  const sx = a => L + plotW * (a - ylo) / (yhi - ylo), sy = a => T0 + plotH * (1 - (a - ylo) / (yhi - ylo));
  let g = '';
  tk.forEach(t => {
    g += hz ? `<line x1="${sx(t)}" x2="${sx(t)}" y1="${T0}" y2="${T0 + plotH}" stroke="${C.grid}"/>` + T(sx(t), T0 + plotH + 16, fmt(t), {fill: C.mut, anchor: 'middle', size: 11})
            : `<line x1="${L}" x2="${L + plotW}" y1="${sy(t)}" y2="${sy(t)}" stroke="${C.grid}"/>` + T(L - 8, sy(t) + 4, fmt(t), {fill: C.mut, anchor: 'end', size: 11});
  });
  const pos = i => (hz ? T0 : L) + band * (i + 0.5);
  d.labels.forEach((l, i) => { g += hz ? T(L - 8, pos(i) + 4, cut(l, 22), {fill: C.mut, anchor: 'end', size: 11}) : T(pos(i), T0 + plotH + 18, cut(l, 16), {fill: C.mut, anchor: rot ? 'end' : 'middle', size: 11, rot: rot ? -40 : 0}); });
  const base = hz ? sx(0) : sy(0), tip = (i, si, a) => `<title>${esc(d.labels[i])}${S.length > 1 ? ' – ' + esc(S[si].name) : ''}: ${esc(fmt(a))}</title>`;
  const cum = new Array(n).fill(0), cumN = new Array(n).fill(0);
  S.forEach((s, si) => {
    const col = pal[si % pal.length];
    if (line || area) {
      let path = '', pts = [];
      s.values.forEach((a, i) => { if (a == null) { path += ' '; return; } const top = stacked ? (cum[i] += a) : a; const x = pos(i), y = sy(top); path += (path.trim() === '' || path.endsWith(' ') ? 'M' : 'L') + x + ',' + y; pts.push([i, x, y, a]); });
      if (area) { const first = pts[0], last = pts[pts.length - 1]; if (first) g += `<path d="${path.trim()} L${last[1]},${sy(0)} L${first[1]},${sy(0)} Z" fill="${col}" fill-opacity="${stacked ? .7 : .25}"/>`; }
      g += `<path d="${path.trim()}" fill="none" stroke="${col}" stroke-width="2.5" stroke-linejoin="round"/>`;
      if (n <= 40) pts.forEach(([i, x, y, a]) => { g += `<circle cx="${x}" cy="${y}" r="3.5" fill="${col}">${tip(i, si, a)}</circle>`; if (o.values && n <= 20) g += T(x, y - 8, fmt(a), {fill: C.ink, anchor: 'middle', size: 11}); });
    } else {
      const gw = band * (o.type === 'hist' ? 0.96 : 0.78), bw = stacked ? gw : gw / S.length;
      s.values.forEach((a, i) => {
        if (a == null) return;
        const off = stacked ? 0 : si * bw - gw / 2, st = stacked ? (a >= 0 ? cum : cumN) : null, from = stacked ? st[i] : 0, to = from + a;
        if (stacked) st[i] = to;
        const p0 = (hz ? sx : sy)(from), p1 = (hz ? sx : sy)(to), x = hz ? Math.min(p0, p1) : pos(i) + off - (stacked ? gw / 2 : 0), y = hz ? pos(i) + off - (stacked ? gw / 2 : 0) : Math.min(p0, p1);
        const w = hz ? Math.abs(p1 - p0) : bw, h = hz ? bw : Math.abs(p1 - p0);
        g += `<rect x="${x}" y="${y}" width="${Math.max(w, 1)}" height="${Math.max(h, 1)}" rx="2" fill="${col}">${tip(i, si, a)}</rect>`;
        if (o.values && n * S.length <= 40 && !stacked) g += hz ? T(Math.max(p0, p1) + 4, y + h / 2 + 4, fmt(a), {fill: C.ink, size: 11}) : T(x + w / 2, y - 4, fmt(a), {fill: C.ink, anchor: 'middle', size: 11});
      });
    }
  });
  g += hz ? `<line x1="${base}" x2="${base}" y1="${T0}" y2="${T0 + plotH}" stroke="${C.mut}"/>` : `<line x1="${L}" x2="${L + plotW}" y1="${base}" y2="${base}" stroke="${C.mut}"/>`;
  g += T(L + plotW / 2, H - 8, d.x_title || '', {fill: C.mut, anchor: 'middle', size: 12});
  if (d.y_title && !hz) g += T(14, T0 + plotH / 2, d.y_title, {fill: C.mut, anchor: 'middle', size: 12, rot: -90});
  return [lg + g, H];
}
function pie(d, o, W, C, pal) {
  let items = d.labels.map((l, i) => [l, d.series[0].values[i] || 0]).filter(a => a[1] > 0).sort((a, b) => b[1] - a[1]);
  if (!items.length) return [T(W / 2, 80, 'No positive values to show.', {fill: C.mut, anchor: 'middle', size: 14}), 160];
  if (items.length > 12) items = items.slice(0, 11).concat([['Other', items.slice(11).reduce((s, a) => s + a[1], 0)]]);
  const total = items.reduce((s, a) => s + a[1], 0), wide = W >= 620, T0 = o.title ? 44 : 20;
  const r = wide ? Math.min(190, W * 0.26) : Math.min(W / 2 - 24, 150), cx = wide ? W * 0.3 : W / 2, cy = T0 + r + 8, lx = wide ? W * 0.58 : 20, ly = wide ? T0 + 16 : cy + r + 30;
  const H = Math.max(wide ? T0 + 2 * r + 36 : 0, ly + items.length * 22 + 14), ri = o.type === 'donut' ? r * 0.58 : 0;
  let g = '', a0 = -Math.PI / 2;
  items.forEach(([l, val], i) => {
    const frac = val / total, a1 = a0 + frac * 2 * Math.PI, col = pal[i % pal.length], tip = `<title>${esc(l)}: ${esc(fmt(val))} (${(frac * 100).toFixed(1)}%)</title>`;
    if (frac > 0.9999) g += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${col}">${tip}</circle>` + (ri ? `<circle cx="${cx}" cy="${cy}" r="${ri}" fill="${C.bg}"/>` : '');
    else {
      const P = (a, rr) => `${cx + rr * Math.cos(a)},${cy + rr * Math.sin(a)}`, big = a1 - a0 > Math.PI ? 1 : 0;
      g += `<path d="M${P(a0, r)} A${r},${r} 0 ${big} 1 ${P(a1, r)} ${ri ? `L${P(a1, ri)} A${ri},${ri} 0 ${big} 0 ${P(a0, ri)}` : `L${cx},${cy}`} Z" fill="${col}" stroke="${C.bg}" stroke-width="1.5">${tip}</path>`;
      if (frac >= 0.05) { const m = (a0 + a1) / 2, rr = ri ? (r + ri) / 2 : r * 0.66; g += T(cx + rr * Math.cos(m), cy + rr * Math.sin(m) + 4, Math.round(frac * 100) + '%', {fill: '#fff', anchor: 'middle', size: 12, weight: 700}); }
    }
    a0 = a1;
    const y = ly + i * 22;
    g += `<rect x="${lx}" y="${y - 10}" width="12" height="12" rx="3" fill="${col}"/>` + T(lx + 18, y, `${cut(l, 24)}  ${fmt(val)} (${(frac * 100).toFixed(1)}%)`, {fill: C.ink, size: 12});
  });
  if (ri) g += T(cx, cy - 2, fmt(total), {fill: C.ink, anchor: 'middle', size: 18, weight: 700}) + T(cx, cy + 16, 'Total', {fill: C.mut, anchor: 'middle', size: 11});
  return [g, H];
}
function scatter(d, o, W, C, pal) {
  const S = d.series, all = S.flatMap(s => s.points), title = o.title ? 34 : 14, [lg, lgH] = o.legend && S.length > 1 ? legend(S.map(s => s.name), pal, C, W, title + 14) : ['', 0];
  if (!all.length) return [T(W / 2, 80, 'No rows have both values.', {fill: C.mut, anchor: 'middle', size: 14}), 160];
  const xs = all.map(p => p[0]), ys = all.map(p => p[1]), tx = ticks(Math.min(...xs), Math.max(...xs)), ty = ticks(Math.min(...ys), Math.max(...ys));
  const T0 = title + lgH + 14, L = 62, R = 18, B = 52, H = Math.round(Math.min(560, Math.max(320, W * 0.6))), pw = W - L - R, ph = H - T0 - B;
  const sx = a => L + pw * (a - tx[0]) / (tx[tx.length - 1] - tx[0]), sy = a => T0 + ph * (1 - (a - ty[0]) / (ty[ty.length - 1] - ty[0]));
  let g = '';
  tx.forEach(t => g += `<line x1="${sx(t)}" x2="${sx(t)}" y1="${T0}" y2="${T0 + ph}" stroke="${C.grid}"/>` + T(sx(t), T0 + ph + 16, fmt(t), {fill: C.mut, anchor: 'middle', size: 11}));
  ty.forEach(t => g += `<line x1="${L}" x2="${L + pw}" y1="${sy(t)}" y2="${sy(t)}" stroke="${C.grid}"/>` + T(L - 8, sy(t) + 4, fmt(t), {fill: C.mut, anchor: 'end', size: 11}));
  S.forEach((s, i) => s.points.forEach(p => g += `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="3.6" fill="${pal[i % pal.length]}" fill-opacity=".62"><title>${esc(d.x_title)}: ${esc(fmt(p[0]))}, ${esc(d.y_title)}: ${esc(fmt(p[1]))}</title></circle>`));
  g += `<line x1="${L}" x2="${L + pw}" y1="${T0 + ph}" y2="${T0 + ph}" stroke="${C.mut}"/><line x1="${L}" x2="${L}" y1="${T0}" y2="${T0 + ph}" stroke="${C.mut}"/>`;
  g += T(L + pw / 2, H - 8, d.x_title, {fill: C.mut, anchor: 'middle', size: 12}) + T(14, T0 + ph / 2, d.y_title, {fill: C.mut, anchor: 'middle', size: 12, rot: -90});
  return [lg + g, H];
}
function render() {
  if (!data) return;
  const C = colors(), o = {type: $('#type').value, title: $('#title').value.trim(), stacked: $('#stacked').checked, values: $('#values').checked, legend: $('#legend').checked};
  const W = Math.max(300, Math.round($('#chart').clientWidth || 900)), pal = PALS[$('#pal').value] || PALS.Gridglass;
  const [body, H] = (o.type === 'pie' || o.type === 'donut' ? pie : o.type === 'scatter' ? scatter : cartesian)(data, o, W, C, pal);
  const heading = o.title || (data.y_title && o.type !== 'hist' ? `${data.y_title} by ${data.x_title}` : data.series.length === 1 && data.series[0].name !== 'Points' ? `${data.series[0].name} by ${data.x_title}` : '');
  dims = [W, H];
  svgText = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" font-family="Schibsted Grotesk, system-ui, sans-serif"><rect width="${W}" height="${H}" fill="${C.bg}"/>${heading ? T(W / 2, 26, heading, {fill: C.ink, anchor: 'middle', size: 17, weight: 700}) : ''}${body}</svg>`;
  $('#chart').innerHTML = svgText; const s = $('#chart svg'); s.style.width = '100%'; s.style.height = 'auto';
  $('#cnote').textContent = data.total > data.shown ? `Showing ${data.shown.toLocaleString()} of ${data.total.toLocaleString()} ${data.kind === 'scatter' ? 'points (a sample)' : 'categories'}. Raise “Max categories” to see more.` : '';
}

// ---------- controls and exports ----------
const redo = debounce(refresh, 300), style = debounce(render, 120);
['#type', '#x', '#agg', '#group', '#part', '#sort'].forEach(s => $(s).addEventListener('change', refresh));
['#limit', '#bins'].forEach(s => $(s).addEventListener('input', redo));
['#title', '#pal', '#stacked', '#values', '#legend'].forEach(s => $(s).addEventListener('input', style));
document.addEventListener('themechange', render);
addEventListener('resize', debounce(render, 200));
const fname = () => (up.info ? up.info.name.replace(/\.[^.]+$/, '') : 'chart') + '-chart';
$('#dsvg').onclick = () => svgText ? saveBlob(new Blob([svgText], {type: 'image/svg+xml'}), fname() + '.svg') : msg('Make a chart first.');
$('#dpng').onclick = () => {
  if (!svgText) return msg('Make a chart first.');
  const img = new Image(), url = URL.createObjectURL(new Blob([svgText], {type: 'image/svg+xml;charset=utf-8'}));
  img.onload = () => {
    const c = document.createElement('canvas'), k = 2; c.width = dims[0] * k; c.height = dims[1] * k;
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
    c.toBlob(b => b ? saveBlob(b, fname() + '.png') : msg('The PNG could not be created.'));
  };
  img.onerror = () => { URL.revokeObjectURL(url); msg('The PNG could not be created.'); };
  img.src = url;
};
$('#dcsv').onclick = () => {
  if (!data) return msg('Make a chart first.');
  const q = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const rows = data.kind === 'scatter' ? [['Group', data.x_title, data.y_title]].concat(data.series.flatMap(s => s.points.map(p => [s.name, p[0], p[1]])))
    : [[data.x_title].concat(data.series.map(s => s.name))].concat(data.labels.map((l, i) => [l].concat(data.series.map(s => s.values[i]))));
  saveBlob(new Blob(['\ufeff' + rows.map(r => r.map(q).join(',')).join('\n')], {type: 'text/csv'}), fname() + '-data.csv');
};
