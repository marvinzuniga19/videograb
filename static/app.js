/* A donde se piden los datos:
   - vista previa alojada: el marcador se reemplaza por la direccion del servidor
   - uso local: el mismo puerto desde el que se abrio la pagina
   - pruebas con la interfaz servida aparte en 8080: el puerto 8000 */
const RAW_API = '__PORT_8000__';
const IS_LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
const API = !RAW_API.startsWith('__')
  ? RAW_API
  : IS_LOCAL && location.port !== '8080'
    ? location.origin
    : 'http://localhost:8000';

const $ = (id) => document.getElementById(id);
const form = $('form');
const urlInput = $('url');
const analyzeBtn = $('analyze');
const errorBox = $('error');
const skeleton = $('skeleton');
const resultBox = $('result');
const playlistBox = $('playlist');
const queueWrap = $('queue-wrap');
const queueList = $('queue');

const QUALITY_PRESETS = [
  { label: 'Máxima', height: null },
  { label: '1080p', height: 1080 },
  { label: '720p', height: 720 },
  { label: '480p', height: 480 },
  { label: '360p', height: 360 },
];

let current = null; // video analizado
let list = null; // lista analizada
const COMMON_LANGS = [
  { code: 'es', name: 'Español' },
  { code: 'en', name: 'Inglés' },
  { code: 'pt', name: 'Portugués' },
  { code: 'fr', name: 'Francés' },
  { code: 'de', name: 'Alemán' },
  { code: 'it', name: 'Italiano' },
];

const subsSel = new Map(); // codigo -> es automatico
const plSubsSel = new Map();
let subsMode = 'file';
let plSubsMode = 'file';

let mode = 'video';
let height = null;
let plMode = 'video';
let plHeight = null;
let lastUrl = '';
const timers = new Map();

/* ------------------------------ motor ------------------------------ */
fetch(`${API}/api/health`)
  .then((r) => r.json())
  .then((d) => {
    const el = $('health');
    el.textContent = `motor yt-dlp ${d.yt_dlp}`;
    el.classList.add('ok');
  })
  .catch(() => ($('health').textContent = 'motor sin conexión'));

/* ----------------------------- analizar ----------------------------- */
async function analyze(url, asPlaylist = false) {
  errorBox.hidden = true;
  resultBox.hidden = true;
  playlistBox.hidden = true;
  skeleton.hidden = false;
  analyzeBtn.classList.add('is-loading');
  analyzeBtn.disabled = true;
  lastUrl = url;

  try {
    const res = await fetch(`${API}/api/info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, playlist: asPlaylist }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'No se pudo analizar el enlace.');
    if (data.type === 'playlist') renderPlaylist(data);
    else renderVideo(data);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    skeleton.hidden = true;
    analyzeBtn.classList.remove('is-loading');
    analyzeBtn.disabled = false;
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return urlInput.focus();
  analyze(url, false);
});

$('offer-btn').onclick = () => analyze(lastUrl, true);

/* -------------------------- video individual ------------------------ */
function renderVideo(data) {
  current = data;
  list = null;
  mode = 'video';
  height = null;

  const thumb = $('thumb');
  if (data.thumbnail) {
    thumb.src = data.thumbnail;
    thumb.alt = `Miniatura de ${data.title}`;
    thumb.style.display = '';
  } else {
    thumb.style.display = 'none';
  }

  $('duration').textContent = data.is_live ? 'EN VIVO' : data.duration || '';
  $('duration').hidden = !data.duration && !data.is_live;
  $('title').textContent = data.title;
  $('uploader').textContent = data.uploader || 'Autor desconocido';
  $('site').textContent = data.site || '';
  $('offer').hidden = !data.in_playlist;

  const chips = $('qualities');
  chips.innerHTML = '';
  if (data.videos.length === 0) {
    chips.innerHTML = '<p class="pane-label">Sin pistas de video; usa la pestaña de audio.</p>';
    setMode('audio');
  } else {
    data.videos.forEach((v, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip' + (i === 0 ? ' is-on' : '');
      b.dataset.testid = `button-quality-${v.label}`;
      b.innerHTML = `${v.label}${v.fps && v.fps >= 50 ? ' ' + Math.round(v.fps) : ''}${
        v.size ? `<small>${v.size}</small>` : ''
      }`;
      b.onclick = () => {
        chips.querySelectorAll('.chip').forEach((c) => c.classList.remove('is-on'));
        b.classList.add('is-on');
        height = v.height;
      };
      chips.appendChild(b);
    });
    height = data.videos[0].height;
    setMode('video');
  }

  renderSubs(data.subtitles || { manual: [], auto: [] });
  resultBox.hidden = false;
}

/* ----------------------------- subtítulos --------------------------- */
function subsChip(track, isAuto, sel, onChange) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'chip' + (sel.has(track.code) ? ' is-on' : '');
  b.dataset.testid = `button-sub-${track.code}`;
  b.innerHTML = `${escapeHtml(track.name)}${isAuto ? '<span class="tag">auto</span>' : ''}`;
  b.onclick = () => {
    if (sel.has(track.code)) sel.delete(track.code);
    else sel.set(track.code, isAuto);
    b.classList.toggle('is-on', sel.has(track.code));
    onChange();
  };
  return b;
}

function renderSubs(tracks) {
  subsSel.clear();
  subsMode = 'file';
  const block = $('subs-block');
  const box = $('subs-langs');
  const manual = tracks.manual || [];
  const auto = tracks.auto || [];

  if (!manual.length && !auto.length) {
    block.hidden = true;
    return;
  }

  box.innerHTML = '';
  manual.forEach((t) => box.appendChild(subsChip(t, false, subsSel, refreshSubs)));

  $('subs-hint').textContent = manual.length
    ? `${manual.length} ${manual.length === 1 ? 'idioma disponible' : 'idiomas disponibles'}`
    : 'solo hay pistas generadas automáticamente';

  const autoRow = $('subs-auto-row');
  const select = $('subs-auto');
  autoRow.hidden = auto.length === 0;
  if (auto.length) {
    select.innerHTML =
      '<option value="">Elige un idioma…</option>' +
      auto
        .map((t) => `<option value="${escapeHtml(t.code)}">${escapeHtml(t.name)}</option>`)
        .join('');
    select.onchange = () => {
      const code = select.value;
      if (!code || subsSel.has(code)) return;
      const track = auto.find((t) => t.code === code);
      subsSel.set(code, true);
      box.appendChild(subsChip(track, true, subsSel, refreshSubs));
      select.value = '';
      refreshSubs();
    };
  }

  refreshSubs();
  block.hidden = mode === 'audio';
}

function refreshSubs() {
  $('subs-mode').hidden = subsSel.size === 0;
  $('start').textContent =
    mode === 'audio'
      ? 'Descargar MP3'
      : subsSel.size
        ? `Descargar video + ${subsSel.size} ${subsSel.size === 1 ? 'subtítulo' : 'subtítulos'}`
        : 'Descargar video';
}

$('subs-mode').onclick = (e) => {
  const b = e.target.closest('.tab');
  if (!b) return;
  subsMode = b.dataset.sm;
  $('subs-mode')
    .querySelectorAll('.tab')
    .forEach((t) => t.classList.toggle('is-on', t === b));
};

$('pl-subs-mode').onclick = (e) => {
  const b = e.target.closest('.tab');
  if (!b) return;
  plSubsMode = b.dataset.sm;
  $('pl-subs-mode')
    .querySelectorAll('.tab')
    .forEach((t) => t.classList.toggle('is-on', t === b));
};

function subsPayload(sel, subMode, autoFlag) {
  if (!sel.size) return null;
  return {
    langs: [...sel.keys()],
    auto: autoFlag != null ? autoFlag : [...sel.values()].some(Boolean),
    mode: subMode,
  };
}

function setMode(next) {
  mode = next;
  $('tab-video').classList.toggle('is-on', next === 'video');
  $('tab-audio').classList.toggle('is-on', next === 'audio');
  $('pane-video').hidden = next !== 'video';
  $('pane-audio').hidden = next !== 'audio';
  const hasTracks = $('subs-langs').children.length > 0;
  $('subs-block').hidden = next === 'audio' || !hasTracks;
  refreshSubs();
}

$('tab-video').onclick = () => setMode('video');
$('tab-audio').onclick = () => setMode('audio');

$('start').onclick = () => {
  if (!current) return;
  const subs = mode === 'audio' ? null : subsPayload(subsSel, subsMode);
  startJob(
    { url: current.url, mode, height, title: current.title, subs },
    current.title,
    (mode === 'audio' ? 'MP3' : height ? `${height}p` : 'máx') + (subs ? ' + SUB' : ''),
  );
};

/* ---------------------------- lista completa ------------------------ */
function renderPlaylist(data) {
  list = data;
  current = null;
  plMode = 'video';
  plHeight = null;

  $('pl-title').textContent = data.title;
  $('pl-uploader').textContent = data.uploader || 'Autor desconocido';
  $('pl-count').textContent = `${data.total} ${data.total === 1 ? 'video' : 'videos'}`;

  const cap = $('pl-cap');
  if (data.total >= data.max_items) {
    cap.textContent = `Se muestran los primeros ${data.max_items} videos de la lista; descarga por tandas si hay más.`;
    cap.hidden = false;
  } else {
    cap.hidden = true;
  }

  const ul = $('pl-items');
  ul.innerHTML = '';
  data.items.forEach((it, i) => {
    const li = document.createElement('li');
    li.className = 'pl-row';
    li.dataset.testid = `row-item-${i}`;
    const id = `it-${i}`;
    li.innerHTML = `
      <input type="checkbox" id="${id}" ${it.unavailable ? '' : 'checked'} ${
        it.unavailable ? 'disabled' : ''
      } data-testid="checkbox-item-${i}" />
      <span class="pl-num">${i + 1}</span>
      <label class="pl-name" for="${id}" title="${escapeHtml(it.title)}">${escapeHtml(
        it.title,
      )}</label>
      <span class="pl-dur">${it.unavailable ? 'no disponible' : it.duration || ''}</span>`;
    li.querySelector('input').onchange = refreshCount;
    ul.appendChild(li);
  });

  const chips = $('pl-qualities');
  chips.innerHTML = '';
  QUALITY_PRESETS.forEach((q, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip' + (i === 0 ? ' is-on' : '');
    b.dataset.testid = `button-pl-quality-${q.label}`;
    b.textContent = q.label;
    b.onclick = () => {
      chips.querySelectorAll('.chip').forEach((c) => c.classList.remove('is-on'));
      b.classList.add('is-on');
      plHeight = q.height;
    };
    chips.appendChild(b);
  });

  plSubsSel.clear();
  plSubsMode = 'file';
  const subBox = $('pl-subs-langs');
  subBox.innerHTML = '';
  COMMON_LANGS.forEach((t) => subBox.appendChild(subsChip(t, false, plSubsSel, refreshCount)));

  setPlMode('video');
  refreshCount();
  playlistBox.hidden = false;
}

function selected() {
  return [...$('pl-items').querySelectorAll('input')]
    .map((cb, i) => (cb.checked ? list.items[i] : null))
    .filter(Boolean);
}

function refreshCount() {
  const n = selected().length;
  const btn = $('pl-start');
  const withSubs = plMode !== 'audio' && plSubsSel.size > 0;
  $('pl-subs-extra').hidden = !withSubs;
  $('pl-subs-mode').hidden = !withSubs;
  btn.disabled = n === 0;
  btn.textContent = n === 0
    ? 'Selecciona al menos un video'
    : plMode === 'audio'
      ? `Descargar ${n} MP3`
      : `Descargar ${n} ${n === 1 ? 'video' : 'videos'}${withSubs ? ' con subtítulos' : ''}`;
  const boxes = [...$('pl-items').querySelectorAll('input:not([disabled])')];
  const allOn = boxes.length > 0 && boxes.every((b) => b.checked);
  $('pl-toggle').textContent = allOn ? 'Quitar todos' : 'Marcar todos';
}

$('pl-toggle').onclick = () => {
  const boxes = [...$('pl-items').querySelectorAll('input:not([disabled])')];
  const allOn = boxes.every((b) => b.checked);
  boxes.forEach((b) => (b.checked = !allOn));
  refreshCount();
};

function setPlMode(next) {
  plMode = next;
  $('pl-tab-video').classList.toggle('is-on', next === 'video');
  $('pl-tab-audio').classList.toggle('is-on', next === 'audio');
  $('pl-pane-video').hidden = next !== 'video';
  $('pl-pane-audio').hidden = next !== 'audio';
  $('pl-subs').hidden = next === 'audio';
  refreshCount();
}

$('pl-tab-video').onclick = () => setPlMode('video');
$('pl-tab-audio').onclick = () => setPlMode('audio');

$('pl-start').onclick = () => {
  if (!list) return;
  const items = selected().map((it) => ({ url: it.url, title: it.title }));
  if (!items.length) return;
  const subs =
    plMode === 'audio' ? null : subsPayload(plSubsSel, plSubsMode, $('pl-subs-auto').checked);
  startJob(
    { items, mode: plMode, height: plHeight, title: list.title, subs },
    list.title,
    `${items.length}× ${plMode === 'audio' ? 'MP3' : plHeight ? `${plHeight}p` : 'máx'}${
      subs ? ' + SUB' : ''
    }`,
    items.length,
  );
};

/* ------------------------------- cola ------------------------------- */
async function startJob(payload, title, tag, count = 1) {
  const res = await fetch(`${API}/api/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    errorBox.textContent = data.error || 'No se pudo iniciar la descarga.';
    errorBox.hidden = false;
    return;
  }
  addJob(data.job_id, title, tag, count > 1);
}

function addJob(id, title, tag, isList) {
  queueWrap.hidden = false;
  const li = document.createElement('li');
  li.className = 'job';
  li.id = `job-${id}`;
  li.dataset.testid = `card-job-${id}`;
  li.innerHTML = `
    <div class="job-top">
      <div style="min-width:0">
        <div class="job-name">${escapeHtml(title)}</div>
        ${isList ? '<p class="job-sub"></p>' : ''}
      </div>
      <span class="job-tag">${escapeHtml(tag)}</span>
    </div>
    <div class="bar indeterminate"><i></i></div>
    <div class="job-foot"><span class="state">en cola…</span><span class="right"></span></div>`;
  queueList.prepend(li);
  poll(id);
}

function poll(id) {
  const tick = async () => {
    let job;
    try {
      const res = await fetch(`${API}/api/progress/${id}`);
      job = await res.json();
      if (!res.ok) throw new Error(job.error);
    } catch {
      return;
    }

    const li = $(`job-${id}`);
    if (!li) return;
    const bar = li.querySelector('.bar');
    const fill = li.querySelector('.bar > i');
    const state = li.querySelector('.state');
    const right = li.querySelector('.right');
    const sub = li.querySelector('.job-sub');
    const isList = job.kind === 'playlist';

    if (job.percent != null) {
      bar.classList.remove('indeterminate');
      fill.style.width = `${job.percent}%`;
    }
    if (sub && job.index) {
      sub.textContent = job.current
        ? `${job.index} de ${job.count} · ${job.current}`
        : `${job.index} de ${job.count}`;
    }

    if (job.status === 'downloading') {
      state.textContent = isList
        ? `${job.percent != null ? job.percent + '%' : 'descargando'} de la lista`
        : `${job.percent != null ? job.percent + '%' : 'descargando'}${
            job.total_size ? ` · ${job.downloaded} de ${job.total_size}` : ''
          }`;
      right.textContent = [job.speed, job.eta && `faltan ${job.eta}`].filter(Boolean).join(' · ');
    } else if (job.status === 'processing') {
      state.textContent = job.mode === 'audio' ? 'convirtiendo a MP3…' : 'uniendo video y audio…';
      right.textContent = '';
    } else if (job.status === 'packing') {
      state.textContent = 'empaquetando el ZIP…';
      right.textContent = '';
    } else if (job.status === 'done') {
      clearInterval(timers.get(id));
      if (sub) sub.textContent = `${job.ok} de ${job.count} completados`;
      const subsNote = job.subs
        ? job.subs_found
          ? job.subs.mode === 'embed'
            ? ' · subtítulos incrustados'
            : ` · ${job.subs_found} ${job.subs_found === 1 ? 'subtítulo' : 'subtítulos'}`
          : ' · sin subtítulos en esos idiomas'
        : '';
      state.textContent = job.filename
        ? `listo · ${job.size}${job.is_zip ? ' · ZIP' : ''}${subsNote}`
        : 'listo';
      right.innerHTML = job.filename
        ? `<a class="save" href="${API}/api/file/${id}" data-testid="link-save-${id}">${
            job.is_zip ? 'Guardar ZIP' : 'Guardar archivo'
          }</a>`
        : '';
      showFailures(li, job);
      return;
    } else if (job.status === 'error') {
      clearInterval(timers.get(id));
      li.classList.add('err');
      bar.classList.remove('indeterminate');
      fill.style.width = '100%';
      fill.style.background = 'var(--danger)';
      state.textContent = job.error || 'Falló la descarga.';
      right.textContent = '';
      showFailures(li, job);
      return;
    }
  };
  tick();
  timers.set(id, setInterval(tick, 900));
}

function showFailures(li, job) {
  const bad = (job.items || []).filter((it) => it.status === 'error');
  if (!bad.length || li.querySelector('.job-fails')) return;
  const ul = document.createElement('ul');
  ul.className = 'job-fails';
  ul.dataset.testid = 'list-failures';
  ul.innerHTML = bad
    .map((it) => `<li>${escapeHtml(it.title || 'Video')} — ${escapeHtml(it.error || 'falló')}</li>`)
    .join('');
  li.appendChild(ul);
}

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}

urlInput.addEventListener('paste', () => setTimeout(() => form.requestSubmit(), 60));

/* ------------------------ arrastrar y soltar enlaces ----------------- */
const dropzone = $('dropzone');
let dragDepth = 0;

/* Saca la direccion de lo que se arrastro: un enlace de otra pestana, texto
   seleccionado, o un fragmento de HTML con un href dentro. */
function urlFromDrop(dt) {
  if (!dt) return null;

  const uriList = dt.getData('text/uri-list');
  if (uriList) {
    const first = uriList
      .split(/\r?\n/)
      .map((l) => l.trim())
      .find((l) => l && !l.startsWith('#'));
    if (first) return first;
  }

  const plain = dt.getData('text/plain');
  const inPlain = plain && plain.match(/https?:\/\/[^\s"'<>]+/);
  if (inPlain) return inPlain[0];

  const html = dt.getData('text/html');
  const inHtml = html && html.match(/(?:href|src)\s*=\s*["']([^"']+)["']/i);
  if (inHtml && /^https?:\/\//i.test(inHtml[1])) return inHtml[1];

  return null;
}

function dragHasText(e) {
  const types = [...(e.dataTransfer?.types || [])];
  return ['text/uri-list', 'text/plain', 'text/html'].some((t) => types.includes(t));
}

function showDropzone(on) {
  dropzone.hidden = !on;
}

window.addEventListener('dragenter', (e) => {
  if (!dragHasText(e)) return;
  e.preventDefault();
  dragDepth += 1;
  showDropzone(true);
});

window.addEventListener('dragover', (e) => {
  if (!dragHasText(e)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
});

window.addEventListener('dragleave', () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) showDropzone(false);
});

window.addEventListener('drop', (e) => {
  if (!dragHasText(e)) return;
  e.preventDefault();
  dragDepth = 0;
  showDropzone(false);

  const url = urlFromDrop(e.dataTransfer);
  if (!url) {
    errorBox.textContent = 'Eso que soltaste no trae una dirección web. Arrastra un enlace.';
    errorBox.hidden = false;
    return;
  }

  urlInput.value = url;
  form.requestSubmit();
});

// si el arrastre se cancela fuera de la ventana, no dejamos el aviso pegado
window.addEventListener('dragend', () => {
  dragDepth = 0;
  showDropzone(false);
});
