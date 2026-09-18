'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { files: {}, urls: {}, provider: null, app: { name: 'OpenTryOn', tagline: '开源 AI 虚拟试衣', repository_url: '' }, busy: false, job: null, result: null, mode: 'result', started: 0, timer: null, toastTimer: null };
const storage = { get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch { return fallback; } }, set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Private browsing may disable storage. */ } } };
let apiKey = '';
try { apiKey = sessionStorage.getItem('thread-api-key') || ''; } catch { /* In-memory access still works. */ }

function notify(message, error = false) {
  clearTimeout(state.toastTimer);
  $('#toast').textContent = zhMessage(message);
  $('#toast').classList.toggle('error', error);
  $('#toast').hidden = false;
  state.toastTimer = setTimeout(() => { $('#toast').hidden = true; }, error ? 12000 : 5000);
}

function applyBrand(app = state.app) {
  const name = app?.name || 'OpenTryOn';
  const tagline = app?.tagline || '开源 AI 虚拟试衣';
  state.app = { name, tagline, repository_url: app?.repository_url || '' };
  document.title = `${name} · AI 试衣间`;
  document.querySelector('meta[name="description"]').content = `${name} ${tagline}。上传人物和服装图片，轻松探索全新穿搭。`;
  $('#brand-name').textContent = name;
  $('#brand-mark').firstChild.textContent = name.trim().charAt(0).toUpperCase() || 'O';
  $('#brand-home').setAttribute('aria-label', `${name} 首页`);
  $('#brand-avatar').textContent = name.trim().charAt(0).toUpperCase() || 'O';
  $('#version-brand').textContent = name;
  $('#footer-brand').textContent = name;
  $('#footer-tagline').textContent = tagline;
  $('#about-brand').textContent = name;
  const repository = $('#project-repository');
  repository.hidden = !state.app.repository_url;
  if (state.app.repository_url) repository.href = state.app.repository_url;
}

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, signal: options.signal || AbortSignal.timeout(30000), headers: { 'X-API-Key': apiKey, ...options.headers } });
  if (!response.ok) {
    let message = `请求失败（${response.status}），请稍后重试。`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : (body.detail?.length ? '提交的参数有误，请检查图片、服装类别、步数和随机种子。' : message); } catch { /* Non-JSON proxy error. */ }
    if (response.status === 401) message = '此工作空间需要 API 密钥，请点击右上角 T 按钮配置连接。';
    throw new Error(zhMessage(message));
  }
  return response;
}

function remember(job) {
  const history = storage.get('thread-sessions', []);
  storage.set('thread-sessions', [job.id, ...history.filter(id => id !== job.id)].slice(0, 30));
}

function replaceURL(key, blob) {
  if (state.urls[key]) URL.revokeObjectURL(state.urls[key]);
  state.urls[key] = URL.createObjectURL(blob);
  return state.urls[key];
}

function updateButton() {
  const hasImages = Boolean(state.files.model && state.files.garment);
  const publicMode = state.provider?.mode === 'public';
  const needsConsent = publicMode && !$('#public-consent').checked;
  $('#generate').disabled = state.busy || !hasImages || !state.provider?.ready || needsConsent;
  $('#generate span').textContent = state.busy ? '正在生成穿搭…' : '开始试衣';
  $('#generate-hint').textContent = state.busy ? '生成期间可以保持此页面打开，请耐心等待。' : !hasImages ? '上传人物和服装两张图片，即可开始。' : !state.provider?.ready ? '图片已就绪，请在“模型与设置”中连接模型。' : needsConsent ? '请先勾选上方的在线服务上传同意选项。' : publicMode ? '在线演示 · 受公共 GPU 可用性与额度限制。' : '图片将发送到你配置的推理服务器。';
  $('#reset').disabled = state.busy;
  $('#tryon-form').classList.toggle('locked', state.busy);
  $('#tryon-form').querySelectorAll('input, select').forEach(el => { el.disabled = state.busy; });
  $('#preserve').disabled = state.busy || state.provider?.supports_preservation === false;
  if (state.provider?.supports_preservation === false) $('#preserve').checked = false;
  ['sample-model', 'sample-garment', 'load-samples'].forEach(id => { $(`#${id}`).disabled = state.busy; });
}

async function checkHealth() {
  try {
    const response = await request('/api/health');
    const health = await response.json();
    applyBrand(health.app);
    state.provider = health.provider;
    const publicMode = health.provider.mode === 'public';
    $('#public-consent-panel').hidden = !publicMode;
    if (health.provider.supports_preservation === false) $('#preserve').checked = false;
    $('#preserve-title').textContent = publicMode ? '由模型保持人物特征' : '保留你的独特模样';
    $('#preserve-description').textContent = publicMode ? '额外的像素保护需要本地 GPU 推理服务' : '保护面部、头发与周围场景';
    $('#identity-caption').textContent = publicMode ? '模型保持人物特征' : '人物保护';
    const label = $('#engine-label');
    label.replaceChildren();
    const dot = document.createElement('span'); dot.className = 'status-dot';
    if (health.provider.ready) dot.style.background = '#7a9969';
    label.append(dot, `${providerName(health.provider)} · ${health.provider.ready ? '已配置' : '待配置'}`);
    $('#setup-status').textContent = zhMessage(health.provider.message);
    $('#retention-note').textContent = `图片将在 ${health.retention_hours} 小时后自动清理，请及时下载喜欢的作品。`;
  } catch (error) {
    state.provider = null;
    $('#engine-label').textContent = '工作空间尚未连接';
    $('#setup-status').textContent = zhMessage(error.message);
    notify(error.message, true);
  }
  updateButton();
}

function clearResult() {
  state.result = null;
  state.job = null;
  $('#result-preview').hidden = true;
  $('#empty-preview').hidden = false;
  $('#download').disabled = $('#download-top').disabled = true;
  $('[data-mode="compare"]').disabled = true;
  $('#preview-status').textContent = '准备迎接新穿搭';
  $('#result-meta').textContent = '换个风格，每处细节都值得期待。';
  setMode('result');
}

async function selectFile(kind, file, invalidate = true) {
  if (!file) return;
  if (file.size > 15 * 1024 * 1024 || file.size === 0) throw new Error('请选择非空且不超过 15 MB 的图片。');
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('请使用 JPG、PNG 或 WebP 格式的图片。');
  let bitmap;
  try { bitmap = await createImageBitmap(file); } catch { throw new Error('无法读取这张图片，请选择有效的 JPG、PNG 或 WebP 文件。'); }
  const { width, height } = bitmap; bitmap.close();
  if (width < 128 || height < 128 || width * height > 24000000) throw new Error('图片至少为 128 × 128 像素，且总像素不超过 2400 万。');
  if (invalidate) clearResult();
  state.files[kind] = file;
  $('#public-consent').checked = false;
  $(`#${kind}-thumb`).src = replaceURL(kind, file);
  $(`#${kind}-thumb`).hidden = false;
  $(`#${kind}-drop`).classList.add('has-image');
  $(`#${kind}-caption`).textContent = `${file.name} · ${width} × ${height}`;
  updateButton();
}

for (const kind of ['model', 'garment']) {
  $(`#${kind}-input`).addEventListener('change', async event => {
    try { await selectFile(kind, event.target.files[0]); } catch (error) { notify(error.message, true); }
    event.target.value = '';
  });
  const drop = $(`#${kind}-drop`);
  for (const type of ['dragenter', 'dragover']) drop.addEventListener(type, event => { event.preventDefault(); if (!state.busy) drop.classList.add('dragover'); });
  for (const type of ['dragleave', 'drop']) drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove('dragover'); });
  drop.addEventListener('drop', async event => {
    if (state.busy) return;
    try { await selectFile(kind, event.dataTransfer.files[0]); } catch (error) { notify(error.message, true); }
  });
  $(`#sample-${kind}`).addEventListener('click', () => loadSample(kind).catch(error => notify(error.message, true)));
}

async function loadSample(kind) {
  const version = 3;
  const response = await fetch(`/sample-${kind}.webp?v=${version}`);
  if (!response.ok) throw new Error('示例图片加载失败，请稍后重试。');
  await selectFile(kind, new File([await response.blob()], `sample-${kind}.webp`, { type: 'image/webp' }));
  if (kind === 'garment') {
    $('#photo-type').value = 'model';
    $('[name="category"][value="top"]').checked = true;
  }
}
$('#load-samples').addEventListener('click', async () => {
  try { await Promise.all([loadSample('model'), loadSample('garment')]); notify('示例图片已加载，服装图片类型已设为“模特穿着图”。'); }
  catch (error) { notify(error.message, true); }
});

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('selected', button.dataset.mode === mode));
  for (const selector of ['#before-layer', '#compare-line', '#compare-range', '#before-label']) $(selector).hidden = mode !== 'compare';
}
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => setMode(button.dataset.mode)));
$('#compare-range').addEventListener('input', event => {
  $('#before-layer').style.clipPath = `inset(0 ${100 - event.target.value}% 0 0)`;
  $('#compare-line').style.left = `${event.target.value}%`;
});

function setBusy(busy) {
  state.busy = busy;
  $('#working').hidden = !busy;
  clearInterval(state.timer);
  if (busy) {
    state.started = Date.now();
    $('#elapsed').textContent = '已用时 0 秒';
    state.timer = setInterval(() => { $('#elapsed').textContent = `已用时 ${Math.floor((Date.now() - state.started) / 1000)} 秒`; }, 1000);
  }
  updateButton();
}

async function showResult(job) {
  const [result, model] = await Promise.all([request(`/api/jobs/${job.id}/result`), request(`/api/jobs/${job.id}/model`)]);
  state.result = await result.blob();
  $('#result-image').src = replaceURL('result', state.result);
  $('#before-image').src = replaceURL('before', await model.blob());
  $('#result-preview').hidden = false;
  $('#empty-preview').hidden = true;
  $('#download').disabled = $('#download-top').disabled = false;
  $('[data-mode="compare"]').disabled = false;
  $('#preview-status').textContent = '试衣效果已生成';
  $('#result-meta').textContent = `${job.width} × ${job.height} · PNG · ${job.duration_seconds ?? '—'} 秒`;
  state.job = job;
}

async function followJob(job) {
  state.job = job;
  remember(job);
  setBusy(true);
  let errors = 0;
  try {
    while (true) {
      let next;
      try { next = await (await request(`/api/jobs/${job.id}`)).json(); errors = 0; }
      catch (error) { if (++errors >= 3) throw error; await new Promise(resolve => setTimeout(resolve, 2000)); continue; }
      state.job = next;
      if (next.status === 'completed') { await showResult(next); notify('新穿搭已生成，可以与原图对比了。'); break; }
      if (next.status === 'failed') throw new Error(zhMessage(next.error) || '生成失败，请稍后重试。');
      $('#preview-status').textContent = next.status === 'queued' ? '排队中' : '生成中';
      $('#working-title').textContent = next.status === 'queued' ? '你的穿搭正在排队' : '正在为你生成新穿搭';
      $('#working-description').textContent = next.status === 'queued' ? '图片已就绪，正在等待模型处理。' : '模型正在为人物换装，首次运行需要加载模型。';
      await new Promise(resolve => setTimeout(resolve, 1800));
    }
  } catch (error) {
    $('#preview-status').textContent = '任务需要处理';
    notify(`${zhMessage(error.message)} 你可以从“最近记录”中重新打开此任务。`, true);
  } finally { setBusy(false); }
}

$('#tryon-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (state.busy || !state.files.model || !state.files.garment || !state.provider?.ready) return;
  const form = new FormData();
  form.append('model_image', state.files.model);
  form.append('garment_image', state.files.garment);
  form.append('category', $('[name="category"]:checked').value);
  form.append('steps', $('#steps').value);
  form.append('seed', $('#seed').value);
  form.append('garment_photo_type', $('#photo-type').value);
  form.append('preserve', String($('#preserve').checked));
  form.append('allow_public_upload', String($('#public-consent').checked));
  clearResult();
  setBusy(true);
  try { const job = await (await request('/api/try-on', { method: 'POST', body: form })).json(); await followJob(job); }
  catch (error) { notify(error.message, true); setBusy(false); }
});

function download() {
  if (!state.result || !state.job) return;
  const link = document.createElement('a');
  const prefix = state.app.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'try-on';
  link.href = state.urls.result; link.download = `${prefix}-${state.job.options.category}-${state.job.id}.png`;
  document.body.append(link); link.click(); link.remove();
}
$('#download').addEventListener('click', download);
$('#download-top').addEventListener('click', download);
$('#reset').addEventListener('click', () => {
  if (state.busy) return;
  clearResult();
  state.files = {};
  for (const kind of ['model', 'garment']) { $(`#${kind}-thumb`).hidden = true; $(`#${kind}-thumb`).removeAttribute('src'); $(`#${kind}-drop`).classList.remove('has-image'); }
  for (const url of Object.values(state.urls)) URL.revokeObjectURL(url);
  state.urls = {};
  $('#tryon-form').reset();
  if (state.provider?.supports_preservation === false) $('#preserve').checked = false;
  $('#model-caption').textContent = '单人照片，姿态清晰，光线充足。';
  $('#garment-caption').textContent = '尽量让服装完整、清晰地呈现。';
  updateButton();
});

let sessionURLs = [];
async function openSession(job) {
  if (state.busy) return;
  switchView('studio'); clearResult();
  try {
    const [source, clothing] = await Promise.all([request(`/api/jobs/${job.id}/model`), request(`/api/jobs/${job.id}/garment`)]);
    await selectFile('model', new File([await source.blob()], 'model.png', { type: 'image/png' }), false);
    await selectFile('garment', new File([await clothing.blob()], 'garment.png', { type: 'image/png' }), false);
    $(`[name="category"][value="${job.options.category}"]`).checked = true;
    $('#steps').value = job.options.steps; $('#seed').value = job.options.seed;
    $('#photo-type').value = job.options.garment_photo_type; $('#preserve').checked = job.options.preserve;
    await followJob(job);
  } catch (error) { notify(error.message, true); }
}

async function showSessions() {
  const container = $('#sessions-list');
  container.replaceChildren();
  for (const url of sessionURLs) URL.revokeObjectURL(url);
  sessionURLs = [];
  const ids = storage.get('thread-sessions', []);
  if (!ids.length) { const empty = document.createElement('div'); empty.className = 'sessions-empty'; empty.textContent = '还没有试衣记录，去工作台生成你的第一套穿搭吧。'; container.append(empty); return; }
  for (const id of ids) {
    if (!/^[0-9a-f-]{36}$/.test(id)) continue;
    const card = document.createElement('article'); card.className = 'session-card';
    container.append(card);
    try {
      const job = await (await request(`/api/jobs/${id}`)).json();
      const imageResponse = await request(`/api/jobs/${id}/${job.status === 'completed' ? 'result' : 'model'}`);
      const img = document.createElement('img'); img.src = URL.createObjectURL(await imageResponse.blob()); img.alt = `${categoryName(job.options.category)}试衣记录`; sessionURLs.push(img.src); card.append(img);
      const body = document.createElement('div');
      const title = document.createElement('strong'); title.textContent = `${categoryName(job.options.category)} · ${statusName(job.status)}`;
      const date = document.createElement('p'); date.textContent = new Date(job.created_at * 1000).toLocaleString('zh-CN', { hour12: false });
      const actions = document.createElement('div'); actions.className = 'session-actions';
      const open = document.createElement('button'); open.textContent = '查看记录 ↗'; open.disabled = state.busy;
      open.onclick = () => openSession(job);
      const remove = document.createElement('button'); remove.textContent = '删除'; remove.disabled = ['queued', 'running'].includes(job.status);
      remove.onclick = async () => {
        try { await request(`/api/jobs/${id}`, { method: 'DELETE' }); storage.set('thread-sessions', storage.get('thread-sessions', []).filter(item => item !== id)); card.remove(); if (state.job?.id === id) clearResult(); notify('试衣记录及图片已删除。'); }
        catch (error) { notify(error.message, true); }
      };
      actions.append(open, remove); body.append(title, date, actions); card.append(body);
    } catch (error) {
      const body = document.createElement('div'); const description = document.createElement('p'); description.textContent = zhMessage(error.message);
      const forget = document.createElement('button'); forget.textContent = '从历史记录中移除'; forget.onclick = () => { storage.set('thread-sessions', storage.get('thread-sessions', []).filter(item => item !== id)); card.remove(); };
      body.append(description, forget); card.append(body);
    }
  }
}

function switchView(view) {
  $('#studio-view').hidden = view !== 'studio'; $('#sessions-view').hidden = view !== 'sessions';
  $('#breadcrumb').textContent = view === 'studio' ? '试衣工作台' : '最近记录';
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  if (view === 'sessions') showSessions();
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));
document.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => $(`#${button.dataset.open}-dialog`).showModal()));
document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$('#refresh-health').addEventListener('click', async () => { await checkHealth(); if (state.provider?.ready) { $('#setup-dialog').close(); notify('模型已配置，试衣间已就绪。'); } });
$('#connection-form').addEventListener('submit', async event => {
  event.preventDefault(); apiKey = $('#api-key').value.trim();
  try { sessionStorage.setItem('thread-api-key', apiKey); } catch { /* Session-only memory fallback. */ }
  $('#connection-dialog').close(); await checkHealth();
  if (state.provider) notify('工作空间已连接。');
});
$('#public-consent').addEventListener('change', updateButton);
checkHealth().then(async () => {
  const query = new URLSearchParams(location.search);
  const session = query.get('session');
  if (session && /^[0-9a-f-]{36}$/.test(session)) {
    try { await openSession(await (await request(`/api/jobs/${session}`)).json()); }
    catch (error) { notify(error.message, true); }
  } else if (['model', 'garment', 'all'].includes(query.get('sample'))) {
    try {
      const sample = query.get('sample');
      if (sample === 'all') await Promise.all([loadSample('model'), loadSample('garment')]);
      else await loadSample(sample);
    }
    catch (error) { notify(error.message, true); }
  }
});
