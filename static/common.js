// Helpers shared by every page: DOM shortcuts, messages, theme, loading bar, uploads and the mobile menu.
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const post = (url, body) => fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});

// error and info banner with a close button
const msg = t => { clearTimeout(msg.t); $('#mtext').textContent = t || ''; $('#msg').hidden = !t; if (t) msg.t = setTimeout(() => msg(''), 10000); };
$('#mclose').onclick = () => msg('');
document.addEventListener('keydown', e => { if (e.key === 'Escape') { msg(''); closeMenu(); } });

// light / dark theme
const root = document.documentElement;
try { root.dataset.theme = localStorage.getItem('gg-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch (e) {}
$('#theme').onclick = () => { root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('gg-theme', root.dataset.theme); } catch (e) {} document.dispatchEvent(new Event('themechange')); };

// mobile menu
const closeMenu = () => { $('#top').classList.remove('open'); $('#menuBtn').setAttribute('aria-expanded', 'false'); };
$('#menuBtn').onclick = () => { const o = $('#top').classList.toggle('open'); $('#menuBtn').setAttribute('aria-expanded', String(o)); };
document.addEventListener('click', e => { if (!e.target.closest('#top')) closeMenu(); });

// loading bar: progress while uploading, then a moving bar while the server works
const loadUI = {
  show(t) { $('#lname').textContent = t; $('#lpct').textContent = '0%'; $('#lfill').style.width = '0'; $('#loadbox').classList.remove('ind'); $('#loadbox').hidden = false; },
  pct(p) { $('#lfill').style.width = p + '%'; $('#lpct').textContent = Math.round(p) + '%'; },
  wait(t) { $('#loadbox').classList.add('ind'); $('#lpct').textContent = t; },
  hide() { $('#loadbox').hidden = true; }
};
function sendForm(url, fd) {  // XHR, because fetch cannot report upload progress
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest(); x.open('POST', url);
    x.upload.onprogress = e => e.lengthComputable && loadUI.pct(e.loaded / e.total * 100);
    x.upload.onload = () => loadUI.wait('Reading sheets…');
    x.onload = () => { try { res({ok: x.status < 300, j: JSON.parse(x.responseText)}); } catch (e) { rej(e); } };
    x.onerror = () => rej(new Error('network'));
    x.send(fd);
  });
}
