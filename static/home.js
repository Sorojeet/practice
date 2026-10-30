// Home: upload once, then pick a tool. The open file is remembered by every page (see workspace.js).
WS.dropzone($('#up'), {title: 'Drop a spreadsheet here', hint: 'Excel and CSV files work. You can also click to choose one.'});
$('#sample').onclick = () => WS.sample();
$('#rAdd').onclick = () => WS.pick();
$('#rRm').onclick = () => WS.remove(WS.file);
let leaving = false;
function render() {
  const s = WS.sheetMeta(), hero = $('#hero'), ready = $('#ready');
  if (!s) { leaving = false; hero.hidden = false; ready.hidden = true; return; }
  const f = WS.fileMeta();
  $('#readyinfo').textContent = `${f.name}: ${s.rows.toLocaleString()} rows, ${s.cols.length} columns${f.sheets.length > 1 ? `, ${f.sheets.length} sheets` : ''}${WS.files.length > 1 ? ` (${WS.files.length} files open)` : ''}.`;
  if (hero.hidden || leaving) { ready.hidden = false; return; }
  leaving = true; hero.classList.add('leaving');  // the upload card fades away, then the tools take its place
  setTimeout(() => { hero.hidden = true; hero.classList.remove('leaving'); ready.hidden = false; ready.classList.add('enter'); setTimeout(() => ready.classList.remove('enter'), 800); }, 480);
}
WS.on(render);
WS.init();
