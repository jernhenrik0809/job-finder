// ---------- state ----------
let cvId = null;
let llmAvailable = false;
let STATUSES = ["saved", "drafting", "ready", "applied", "screening", "interview", "offer", "rejected", "withdrawn"];
const selected = new Map();      // jobId -> job (roles ticked for drafting)
const jobsById = new Map();      // jobId -> job (all rendered matches)
const savedJobIds = new Set();   // job ids already saved to the pipeline this session
const appsById = new Map();      // application id -> application
let dragId = null;
let currentNewIds = new Set();   // job ids flagged NEW from the last saved-search run

const $ = (sel) => document.querySelector(sel);
const el = {
  dropzone: $('#dropzone'), fileInput: $('#fileInput'), browseBtn: $('#browseBtn'),
  pasteToggle: $('#pasteToggle'), pasteArea: $('#pasteArea'), cvText: $('#cvText'), usePaste: $('#usePaste'),
  profileCard: $('#profileCard'), pTitle: $('#pTitle'), pSeniority: $('#pSeniority'),
  pYears: $('#pYears'), pSkills: $('#pSkills'),
  keywords: $('#keywords'), location: $('#location'), days: $('#days'), limit: $('#limit'),
  remote: $('#remote'), semantic: $('#semantic'), minScore: $('#minScore'), minScoreVal: $('#minScoreVal'),
  searchBtn: $('#searchBtn'), hint: $('#hint'),
  saveSearchBtn: $('#saveSearchBtn'), savedBox: $('#savedBox'), savedList: $('#savedList'), checkNew: $('#checkNew'),
  resultMeta: $('#resultMeta'), warnings: $('#warnings'),
  loading: $('#loading'), empty: $('#empty'), jobs: $('#jobs'), jsearchChk: $('#jsearchChk'),
  tabMatches: $('#tabMatches'), tabPipeline: $('#tabPipeline'), tabInsights: $('#tabInsights'), pipelineCount: $('#pipelineCount'),
  viewMatches: $('#view-matches'), viewPipeline: $('#view-pipeline'), viewInsights: $('#view-insights'),
  insightsEmpty: $('#insightsEmpty'), insightsBody: $('#insightsBody'),
  selbar: $('#selbar'), selCount: $('#selCount'), clearSel: $('#clearSel'), genDrafts: $('#genDrafts'),
  examples: $('#examples'), addExample: $('#addExample'), exampleFile: $('#exampleFile'),
  tone: $('#tone'), length: $('#length'), useLlm: $('#useLlm'), llmHint: $('#llmHint'), useLlmWrap: $('#useLlmWrap'),
  board: $('#board'), boardEmpty: $('#boardEmpty'), draftLoading: $('#draftLoading'),
  drawer: $('#drawer'), drawerPanel: $('#drawerPanel'), drawerBackdrop: $('#drawerBackdrop'),
};

// ---------- init ----------
fetch('/api/sources').then(r => r.json()).then(d => {
  if (!d.jsearch_key_present) {
    el.jsearchChk.querySelector('input').disabled = true;
    el.jsearchChk.title = 'Set RAPIDAPI_KEY in your environment to enable JSearch';
    el.jsearchChk.style.opacity = .55;
  }
}).catch(() => {});

fetch('/api/draft-config').then(r => r.json()).then(d => {
  llmAvailable = !!d.llm_available;
  if (Array.isArray(d.statuses) && d.statuses.length) STATUSES = d.statuses;
  if (llmAvailable) {
    el.llmHint.textContent = `(${d.model})`;
  } else {
    el.useLlm.checked = false;
    el.useLlm.disabled = true;
    el.useLlmWrap.style.opacity = .55;
    el.llmHint.textContent = '(set ANTHROPIC_API_KEY to enable — using offline template)';
  }
}).catch(() => {});

el.minScore.addEventListener('input', () => { el.minScoreVal.textContent = el.minScore.value; });

// ---------- CV upload ----------
el.browseBtn.addEventListener('click', () => el.fileInput.click());
el.dropzone.addEventListener('click', (e) => { if (e.target === el.dropzone || e.target.closest('.dz-inner')) el.fileInput.click(); });
el.fileInput.addEventListener('change', () => { if (el.fileInput.files[0]) uploadFile(el.fileInput.files[0]); });
['dragenter', 'dragover'].forEach(ev => el.dropzone.addEventListener(ev, e => { e.preventDefault(); el.dropzone.classList.add('drag'); }));
['dragleave', 'drop'].forEach(ev => el.dropzone.addEventListener(ev, e => { e.preventDefault(); el.dropzone.classList.remove('drag'); }));
el.dropzone.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) uploadFile(f); });
el.pasteToggle.addEventListener('click', () => el.pasteArea.classList.toggle('hidden'));
el.usePaste.addEventListener('click', () => {
  const text = el.cvText.value.trim();
  if (!text) return;
  const fd = new FormData(); fd.append('text', text);
  postProfile('/api/upload-text', fd);
});

async function uploadFile(file) {
  el.hint.textContent = `Reading ${file.name}…`;
  const fd = new FormData(); fd.append('file', file);
  postProfile('/api/upload', fd);
}

async function postProfile(url, fd) {
  try {
    const resp = await fetch(url, { method: 'POST', body: fd });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Upload failed');
    cvId = data.cv_id;
    renderProfile(data.profile);
    if (data.warning) showWarnings([data.warning]);
    el.searchBtn.disabled = false;
    el.saveSearchBtn.classList.remove('hidden');
    loadSavedSearches();
    el.hint.textContent = 'CV loaded. Adjust the search and hit “Find matching jobs”.';
  } catch (err) {
    el.hint.textContent = '⚠ ' + err.message;
  }
}

function renderProfile(p) {
  el.profileCard.classList.remove('hidden');
  el.pTitle.textContent = (p.titles && p.titles[0]) || (p.name || 'CV loaded');
  el.pSeniority.textContent = p.seniority || '';
  el.pSeniority.classList.toggle('hidden', !p.seniority);
  el.pYears.textContent = p.years_experience ? `${p.years_experience} yrs exp` : '';
  el.pYears.classList.toggle('hidden', !p.years_experience);
  el.pSkills.innerHTML = '';
  (p.skills || []).slice(0, 20).forEach(s => {
    const c = document.createElement('span'); c.className = 'chip'; c.textContent = s;
    el.pSkills.appendChild(c);
  });
  if (!el.keywords.value && p.suggested_keywords) el.keywords.value = p.suggested_keywords;
  if (!el.location.value && p.location) el.location.value = p.location;
}

// ---------- tabs ----------
el.tabMatches.addEventListener('click', () => switchTab('matches'));
el.tabPipeline.addEventListener('click', () => { switchTab('pipeline'); loadPipeline(); });
el.tabInsights.addEventListener('click', () => { switchTab('insights'); loadInsights(); });

function switchTab(name) {
  const map = {
    matches: [el.tabMatches, el.viewMatches],
    pipeline: [el.tabPipeline, el.viewPipeline],
    insights: [el.tabInsights, el.viewInsights],
  };
  for (const [k, [tab, view]] of Object.entries(map)) {
    tab.classList.toggle('active', k === name);
    view.classList.toggle('hidden', k !== name);
  }
}

// ---------- search ----------
el.searchBtn.addEventListener('click', runSearch);
function selectedSources() { return [...document.querySelectorAll('#sources input:checked')].map(i => i.value); }

async function runSearch() {
  if (!cvId) return;
  const sources = selectedSources();
  if (sources.length === 0) { showWarnings(['Pick at least one job source.']); return; }
  currentNewIds = new Set();          // a manual search has no "new since last check" context
  switchTab('matches');
  el.warnings.classList.add('hidden');
  el.empty.classList.add('hidden');
  el.jobs.innerHTML = '';
  selected.clear(); jobsById.clear(); updateSelbar();
  el.loading.classList.remove('hidden');
  el.searchBtn.disabled = true;
  el.resultMeta.textContent = '';
  const body = {
    cv_id: cvId, keywords: el.keywords.value.trim(), location: el.location.value.trim(), sources,
    limit_per_source: parseInt(el.limit.value, 10), remote: el.remote.checked,
    days: el.days.value ? parseInt(el.days.value, 10) : null,
    semantic: el.semantic.checked, min_score: parseFloat(el.minScore.value),
  };
  try {
    const resp = await fetch('/api/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Search failed');
    renderJobs(data);
  } catch (err) {
    showWarnings(['Search error: ' + err.message]);
  } finally {
    el.loading.classList.add('hidden');
    el.searchBtn.disabled = false;
  }
}

function renderJobs(data) {
  const jobs = data.jobs || [];
  const counts = Object.entries(data.counts || {}).map(([k, v]) => `${k}: ${v}`).join(' · ');
  el.resultMeta.textContent = [`${jobs.length} matches`, data.query ? `“${data.query}”` : '', counts].filter(Boolean).join('  •  ');
  if (data.warnings && data.warnings.length) showWarnings(data.warnings);
  if (jobs.length === 0) {
    el.empty.classList.remove('hidden');
    el.empty.querySelector('p').textContent = 'No jobs matched. Try different keywords, a broader location, or more sources.';
    return;
  }
  el.empty.classList.add('hidden');
  el.jobs.innerHTML = '';
  jobs.forEach(j => { jobsById.set(j.id, j); el.jobs.appendChild(jobCard(j)); });
}

function jobCard(j) {
  const card = document.createElement('div');
  card.className = 'job';
  card.dataset.jobId = j.id;
  const cls = j.score >= 70 ? 'high' : j.score >= 45 ? 'mid' : 'low';
  const url = safeUrl(j.url);
  const matched = (j.matched_skills || []).slice(0, 8).map(s => `<span class="chip matched">${esc(s)}</span>`).join('');
  const missing = (j.missing_skills || []).slice(0, 6).map(s => `<span class="chip missing">${esc(s)}</span>`).join('');
  const sub = [
    j.company ? `<b>${esc(j.company)}</b>` : '', j.location ? esc(j.location) : '',
    j.salary ? `💰 ${esc(j.salary)}` : '', j.posted ? `🕑 ${esc(j.posted)}` : '',
    `<span class="src">${esc(j.source)}</span>`,
  ].filter(Boolean).join('<span> · </span>');
  const desc = j.description ? `<p class="job-desc">${esc(j.description.slice(0, 280))}${j.description.length > 280 ? '…' : ''}</p>` : '';
  const isSaved = savedJobIds.has(j.id);
  card.innerHTML = `
    <div class="job-pick"><input type="checkbox" aria-label="Select for drafting" /></div>
    <div class="score ${cls}">${Math.round(j.score)}<small>match</small></div>
    <div class="job-main">
      <h3>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : esc(j.title)}${currentNewIds.has(j.id) ? '<span class="new-flag">NEW</span>' : ''}</h3>
      <div class="job-sub">${sub}</div>
      ${desc}
      ${matched ? `<div class="skill-row"><span class="lbl">✓ you have</span>${matched}</div>` : ''}
      ${missing ? `<div class="skill-row" style="margin-top:6px"><span class="lbl">gaps</span>${missing}</div>` : ''}
      <button class="save-pipeline${isSaved ? ' saved' : ''}" type="button">${isSaved ? '✓ Saved' : '＋ Save to pipeline'}</button>
      ${url ? ` <a class="apply-link" href="${esc(url)}" target="_blank" rel="noopener" style="margin-left:8px;font-size:13px">View ↗</a>` : ''}
    </div>`;
  const cb = card.querySelector('.job-pick input');
  cb.addEventListener('change', () => { if (cb.checked) selected.set(j.id, j); else selected.delete(j.id); updateSelbar(); });
  const saveBtn = card.querySelector('.save-pipeline');
  saveBtn.addEventListener('click', () => saveToPipeline(j, saveBtn));
  return card;
}

async function saveToPipeline(job, btn) {
  if (savedJobIds.has(job.id)) { switchTab('pipeline'); loadPipeline(); return; }
  btn.disabled = true;
  try {
    const resp = await fetch('/api/applications', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv_id: cvId || '', job }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Save failed'); }
    savedJobIds.add(job.id);
    btn.classList.add('saved'); btn.textContent = '✓ Saved';
    bumpPipelineCount(1);
  } catch (err) { showWarnings(['Save: ' + err.message]); }
  finally { btn.disabled = false; }
}

// ---------- saved searches ----------
function currentSearchPayload() {
  const kw = el.keywords.value.trim();
  const loc = el.location.value.trim();
  return {
    name: (kw || 'Saved search') + (loc ? ' · ' + loc : ''),
    cv_id: cvId || '', keywords: kw, location: loc, sources: selectedSources(),
    limit_per_source: parseInt(el.limit.value, 10), remote: el.remote.checked,
    days: el.days.value ? parseInt(el.days.value, 10) : null,
    semantic: el.semantic.checked, min_score: parseFloat(el.minScore.value),
  };
}

el.saveSearchBtn.addEventListener('click', async () => {
  if (!cvId) return;
  try {
    const resp = await fetch('/api/saved-searches', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentSearchPayload()) });
    if (!resp.ok) throw new Error('save failed');
    el.saveSearchBtn.textContent = '★ Saved!';
    setTimeout(() => { el.saveSearchBtn.textContent = '★ Save this search'; }, 1400);
    loadSavedSearches();
  } catch (e) { showWarnings(['Save search: ' + e.message]); }
});

el.checkNew.addEventListener('click', async () => {
  el.checkNew.textContent = 'checking…'; el.checkNew.disabled = true;
  try {
    const data = await (await fetch('/api/saved-searches/run-all', { method: 'POST' })).json();
    const total = (data.searches || []).reduce((n, s) => n + (s.new_count || 0), 0);
    await loadSavedSearches();      // repaint from full summaries (keeps the location/source sub-line)
    el.checkNew.textContent = total ? `${total} new ✓` : 'no new';
  } catch { el.checkNew.textContent = 'check for new'; }
  finally { setTimeout(() => { el.checkNew.textContent = 'check for new'; el.checkNew.disabled = false; }, 2500); }
});

async function loadSavedSearches() {
  try { renderSavedList((await (await fetch('/api/saved-searches')).json()).searches || []); }
  catch { /* ignore */ }
}

function renderSavedList(searches) {
  el.savedBox.classList.toggle('hidden', searches.length === 0);
  el.savedList.innerHTML = '';
  searches.forEach(s => {
    const row = document.createElement('div');
    row.className = 'saved-row';
    const sub = [s.location, (s.sources || []).join(', ')].filter(Boolean).join(' · ');
    row.innerHTML = `<span class="s-name">${esc(s.name)}${sub ? `<div class="s-sub">${esc(sub)}</div>` : ''}</span>
      ${s.new_count ? `<span class="new-badge">${s.new_count} new</span>` : ''}
      <button class="s-del" title="Delete">✕</button>`;
    row.addEventListener('click', (e) => { if (!e.target.closest('.s-del')) runSavedSearch(s.id); });
    row.querySelector('.s-del').addEventListener('click', async (e) => {
      e.stopPropagation();
      await fetch(`/api/saved-searches/${s.id}`, { method: 'DELETE' });
      loadSavedSearches();
    });
    el.savedList.appendChild(row);
  });
}

async function runSavedSearch(id) {
  switchTab('matches');
  el.warnings.classList.add('hidden');
  el.empty.classList.add('hidden');
  el.jobs.innerHTML = '';
  selected.clear(); jobsById.clear(); updateSelbar();
  el.loading.classList.remove('hidden');
  el.resultMeta.textContent = '';
  try {
    const resp = await fetch(`/api/saved-searches/${id}/run`, { method: 'POST' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Run failed');
    currentNewIds = new Set(data.new_ids || []);
    renderJobs(data);
    await fetch(`/api/saved-searches/${id}/seen`, { method: 'POST' });   // mark viewed → clears badge
    loadSavedSearches();
  } catch (err) {
    showWarnings(['Saved search: ' + err.message]);
  } finally {
    el.loading.classList.add('hidden');
  }
}

// ---------- selection → generate ----------
el.clearSel.addEventListener('click', () => {
  selected.clear();
  document.querySelectorAll('.job-pick input:checked').forEach(c => { c.checked = false; });
  updateSelbar();
});
el.genDrafts.addEventListener('click', generateApplications);
function updateSelbar() { el.selCount.textContent = selected.size; el.selbar.classList.toggle('hidden', selected.size === 0); }

async function generateApplications() {
  if (!cvId || selected.size === 0) return;
  const jobs = [...selected.values()];
  switchTab('pipeline');
  el.boardEmpty.classList.add('hidden');
  el.draftLoading.classList.remove('hidden');
  el.genDrafts.disabled = true;
  try {
    const resp = await fetch('/api/applications/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cv_id: cvId, jobs, tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Generation failed');
    jobs.forEach(j => savedJobIds.add(j.id));
    selected.clear();
    document.querySelectorAll('.job-pick input:checked').forEach(c => { c.checked = false; });
    updateSelbar();
    await loadPipeline();
  } catch (err) {
    showWarnings(['Draft error: ' + err.message]);
    switchTab('matches');
  } finally {
    el.draftLoading.classList.add('hidden');
    el.genDrafts.disabled = false;
  }
}

// ---------- pipeline / Kanban ----------
async function loadPipeline() {
  await loadExamples();
  try {
    const data = await (await fetch('/api/applications')).json();
    if (Array.isArray(data.statuses) && data.statuses.length) STATUSES = data.statuses;
    appsById.clear();
    (data.applications || []).forEach(a => appsById.set(a.id, a));
    renderBoard();
  } catch { /* ignore */ }
}

function bumpPipelineCount(delta) {
  const n = Math.max(0, (parseInt(el.pipelineCount.textContent, 10) || 0) + delta);
  el.pipelineCount.textContent = n;
}

function renderBoard() {
  const apps = [...appsById.values()];
  el.pipelineCount.textContent = apps.length;
  el.boardEmpty.classList.toggle('hidden', apps.length > 0);
  el.board.classList.toggle('hidden', apps.length === 0);
  el.board.innerHTML = '';
  STATUSES.forEach(status => {
    const inCol = apps.filter(a => a.status === status);
    const col = document.createElement('div');
    col.className = 'col';
    col.dataset.status = status;
    col.innerHTML = `<div class="col-head st-${status}"><span>${esc(status)}</span><span class="cnt">${inCol.length}</span></div><div class="col-body"></div>`;
    const body = col.querySelector('.col-body');
    inCol.forEach(a => body.appendChild(pcard(a)));
    // drop target wiring — on the whole column so header + body are one consistent zone
    col.addEventListener('dragover', e => { e.preventDefault(); col.classList.add('drop-target'); });
    col.addEventListener('dragleave', e => { if (!col.contains(e.relatedTarget)) col.classList.remove('drop-target'); });
    col.addEventListener('drop', e => { e.preventDefault(); col.classList.remove('drop-target'); onDrop(status); });
    el.board.appendChild(col);
  });
}

function pcard(a) {
  const card = document.createElement('div');
  card.className = `pcard st-${a.status}`;
  card.draggable = true;
  card.dataset.id = a.id;
  const gen = a.generator === 'llm' ? '<span class="pc-tag llm">✨ Claude letter</span>'
    : a.generator === 'template' ? '<span class="pc-tag">letter ready</span>'
      : '<span class="pc-tag">no letter yet</span>';
  card.innerHTML = `
    <h4>${esc(a.job_title)}</h4>
    <div class="pc-sub"><span>${esc(a.company || '')}</span><span class="pc-score">${Math.round(a.score || 0)}</span></div>
    ${gen}`;
  card.addEventListener('dragstart', e => { dragId = a.id; card.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; });
  card.addEventListener('dragend', () => { dragId = null; card.classList.remove('dragging'); document.querySelectorAll('.drop-target').forEach(c => c.classList.remove('drop-target')); });
  card.addEventListener('click', () => openDrawer(a.id));
  return card;
}

async function onDrop(newStatus) {
  const id = dragId;
  if (!id) return;
  const a = appsById.get(id);
  if (!a || a.status === newStatus) return;
  const updated = await patchApp(id, { status: newStatus });
  if (updated) { appsById.set(id, updated); renderBoard(); }
}

async function patchApp(id, fields) {
  try {
    const resp = await fetch(`/api/applications/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Update failed');
    return data;
  } catch (err) { showWarnings(['Update: ' + err.message]); return null; }
}

// ---------- detail drawer ----------
el.drawerBackdrop.addEventListener('click', closeDrawer);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !el.drawer.classList.contains('hidden')) closeDrawer(); });
function closeDrawer() { el.drawer.classList.add('hidden'); el.drawerPanel.innerHTML = ''; }

function openDrawer(id) {
  const a = appsById.get(id);
  if (!a) return;
  const url = safeUrl(a.job_url);
  const statusBtns = STATUSES.map(s =>
    `<button class="st-btn st-${s}${s === a.status ? ' active' : ''}" data-status="${s}">${esc(s)}</button>`).join('');
  const events = (a.events || []).slice().reverse().map(ev =>
    `<li><span class="t">${esc(ev.detail || ev.type)}</span><span>${fmtTime(ev.ts)}</span></li>`).join('');
  const genLabel = a.body ? 'Regenerate letter' : 'Generate letter';

  el.drawerPanel.innerHTML = `
    <div class="dw-head">
      <div>
        <h2>${esc(a.job_title)}</h2>
        <div class="sub">${esc(a.company || '')}${a.location ? ' · ' + esc(a.location) : ''} · score ${Math.round(a.score || 0)}
          ${url ? ` · <a class="apply-link" href="${esc(url)}" target="_blank" rel="noopener">open posting ↗</a>` : ''}</div>
      </div>
      <button class="dw-close" title="Close (Esc)">×</button>
    </div>

    <div class="dw-section">
      <span class="lbl">Status</span>
      <div class="status-pills">${statusBtns}</div>
    </div>

    <div class="dw-section">
      <span class="lbl">Notes</span>
      <textarea class="notes" placeholder="Private notes — contacts, recruiter, next steps…">${esc(a.notes || '')}</textarea>
      <div class="dw-actions"><button class="btn mini ok save-notes">Save notes</button><span class="msg copied" style="display:none">saved</span></div>
    </div>

    <div class="dw-section">
      <span class="lbl">Cover letter</span>
      <input class="subject" value="${esc(a.subject || '')}" placeholder="Subject" />
      <textarea class="body" placeholder="No letter yet — click “${esc(genLabel)}”.">${esc(a.body || '')}</textarea>
      ${a.gen_note ? `<p class="dw-note">⚠ ${esc(a.gen_note)}</p>` : ''}
      <div class="dw-actions">
        <button class="btn mini ok save-letter">Save</button>
        <button class="btn mini ghost regen">${esc(genLabel)}</button>
        <button class="btn mini ghost copy">Copy</button>
        <button class="btn mini ghost download">Download</button>
        <span class="msg copied" style="display:none">saved</span>
        <span class="spacer"></span>
        <button class="btn mini danger del">Delete</button>
      </div>
    </div>

    <div class="dw-section">
      <span class="lbl">Timeline</span>
      <ul class="timeline">${events || '<li>No events yet.</li>'}</ul>
    </div>`;

  el.drawer.classList.remove('hidden');
  wireDrawer(a.id);
}

function wireDrawer(id) {
  const panel = el.drawerPanel;
  const subjectEl = panel.querySelector('.subject');
  const bodyEl = panel.querySelector('.body');
  const notesEl = panel.querySelector('.notes');
  const flash = (sel) => { const m = panel.querySelector(sel); if (m) { m.style.display = 'inline'; setTimeout(() => { m.style.display = 'none'; }, 1400); } };

  panel.querySelector('.dw-close').addEventListener('click', closeDrawer);

  panel.querySelectorAll('.st-btn').forEach(btn => btn.addEventListener('click', async () => {
    const updated = await patchApp(id, { status: btn.dataset.status });
    if (updated) {
      appsById.set(id, updated);
      renderBoard();
      // refresh the drawer (timeline + active pill) only if it's still open on this app
      if (!el.drawer.classList.contains('hidden')) openDrawer(id);
    }
  }));

  panel.querySelector('.save-notes').addEventListener('click', async () => {
    const updated = await patchApp(id, { notes: notesEl.value });
    if (updated) { appsById.set(id, updated); flash('.dw-section .msg'); }
  });

  panel.querySelector('.save-letter').addEventListener('click', async () => {
    const updated = await patchApp(id, { subject: subjectEl.value, body: bodyEl.value });
    if (updated) { appsById.set(id, updated); renderBoard(); flash('.dw-actions .msg'); }
  });

  panel.querySelector('.regen').addEventListener('click', async () => {
    const btn = panel.querySelector('.regen'); btn.disabled = true; btn.textContent = 'Writing…';
    try {
      const resp = await fetch(`/api/applications/${id}/regenerate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_id: cvId || '', tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || 'Generation failed');
      appsById.set(id, data);
      renderBoard();
      if (!el.drawer.classList.contains('hidden')) openDrawer(id);
    } catch (err) { showWarnings(['Generate: ' + err.message]); btn.disabled = false; btn.textContent = 'Retry'; }
  });

  panel.querySelector('.copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(`Subject: ${subjectEl.value}\n\n${bodyEl.value}`); flash('.dw-actions .msg'); } catch {}
  });
  panel.querySelector('.download').addEventListener('click', () => { window.location.href = `/api/applications/${id}/export`; });
  panel.querySelector('.del').addEventListener('click', async () => {
    const a = appsById.get(id);
    const jobId = a && a.job && a.job.id;
    await fetch(`/api/applications/${id}`, { method: 'DELETE' });
    appsById.delete(id);
    if (jobId) {                       // un-mark the originating match card's Save button
      savedJobIds.delete(jobId);
      const btn = document.querySelector(`.job[data-job-id="${jobId}"] .save-pipeline`);
      if (btn) { btn.classList.remove('saved'); btn.textContent = '＋ Save to pipeline'; }
    }
    renderBoard();
    closeDrawer();
  });
}

// ---------- insights ----------
async function loadInsights() {
  try { renderInsights(await (await fetch('/api/insights')).json()); }
  catch { /* ignore */ }
}

function renderInsights(r) {
  const empty = (r.total || 0) === 0;
  el.insightsEmpty.classList.toggle('hidden', !empty);
  el.insightsBody.classList.toggle('hidden', empty);
  if (empty) { el.insightsBody.innerHTML = ''; return; }

  const fn = Object.fromEntries(r.funnel.map(f => [f.stage, f.count]));
  const ttr = r.avg_time_to_response_days == null ? '—' : r.avg_time_to_response_days;

  const metrics = `<div class="metrics">
    <div class="metric-card"><div class="v">${r.total}</div><div class="k">in pipeline</div></div>
    <div class="metric-card"><div class="v">${fn.applied || 0}</div><div class="k">applied</div></div>
    <div class="metric-card"><div class="v">${r.response_rate}<small>%</small></div><div class="k">response rate</div></div>
    <div class="metric-card"><div class="v">${r.offers}</div><div class="k">offers</div></div>
    <div class="metric-card"><div class="v">${ttr}${ttr === '—' ? '' : '<small> d</small>'}</div><div class="k">avg. response time</div></div>
  </div>`;

  const maxv = Math.max(1, r.funnel[0].count);
  const funnel = `<div class="insights-section"><h3>Funnel</h3>${r.funnel.map((f, i) => {
    const w = Math.max(3, Math.round(f.count / maxv * 100));
    const prev = i > 0 ? r.funnel[i - 1].count : null;
    const conv = (i > 0 && prev > 0) ? `${Math.round(f.count / prev * 100)}%` : '';
    return `<div class="funnel-row"><span class="name">${esc(f.stage)}</span>
      <div class="funnel-bar"><div class="funnel-fill" style="width:${w}%">${f.count}</div></div>
      <span class="conv">${conv}</span></div>`;
  }).join('')}</div>`;

  const nudges = (r.nudges && r.nudges.length) ? `<div class="insights-section"><h3>Needs attention</h3>
    <div class="nudges-list">${r.nudges.map(n => `
      <div class="nudge" data-id="${esc(n.id)}">
        <span class="n-main"><b>${esc(n.title)}</b>${n.company ? ' · ' + esc(n.company) : ''}<div class="n-msg">${esc(n.message)}</div></span>
        <span class="go">open ↗</span></div>`).join('')}</div></div>` : '';

  const bySource = (r.by_source && r.by_source.length) ? `<div class="insights-section"><h3>Applications by source</h3>
    <table class="src-table">${r.by_source.map(s => `<tr><td>${esc(s.source)}</td><td class="n">${s.applied}</td></tr>`).join('')}</table></div>` : '';

  const ot = r.over_time || [];
  const omax = Math.max(1, ...ot.map(b => b.count));
  const spark = ot.length ? `<div class="insights-section"><h3>Added per week</h3>
    <div class="spark">${ot.map(b => `<div class="bar" style="height:${Math.round(b.count / omax * 100)}%" title="${esc(b.label)}: ${b.count}"></div>`).join('')}</div>
    <div class="spark-labels">${ot.map(b => `<span>${esc(b.label)}</span>`).join('')}</div></div>` : '';

  el.insightsBody.innerHTML = metrics + funnel + nudges + bySource + spark;

  el.insightsBody.querySelectorAll('.nudge').forEach(nd => nd.addEventListener('click', async () => {
    const id = nd.dataset.id;
    switchTab('pipeline');
    await loadPipeline();
    openDrawer(id);
  }));
}

// ---------- style examples ----------
el.addExample.addEventListener('click', () => el.exampleFile.click());
el.exampleFile.addEventListener('change', async () => {
  const f = el.exampleFile.files[0];
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try {
    const resp = await fetch('/api/examples', { method: 'POST', body: fd });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
    loadExamples();
  } catch (err) { showWarnings(['Example upload: ' + err.message]); }
  el.exampleFile.value = '';
});

async function loadExamples() {
  try {
    const data = await (await fetch('/api/examples')).json();
    el.examples.innerHTML = '';
    if (!(data.examples || []).length) {
      el.examples.innerHTML = '<span class="muted small">No examples yet — Claude will write from your CV alone.</span>';
      return;
    }
    data.examples.forEach(ex => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.innerHTML = `📄 ${esc(ex.name)} <a href="#" title="remove" style="color:var(--muted);margin-left:4px">✕</a>`;
      chip.querySelector('a').addEventListener('click', async (e) => {
        e.preventDefault();
        await fetch(`/api/examples/${ex.id}`, { method: 'DELETE' });
        loadExamples();
      });
      el.examples.appendChild(chip);
    });
  } catch { /* ignore */ }
}

// ---------- helpers ----------
function showWarnings(list) {
  el.warnings.classList.remove('hidden');
  el.warnings.innerHTML = '<strong>Heads up</strong><ul>' + list.map(w => `<li>${esc(w)}</li>`).join('') + '</ul>';
}
function fmtTime(ts) {
  if (!ts) return '';
  try { return new Date(ts * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return ''; }
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function safeUrl(u) {
  if (!u) return '';
  try { const url = new URL(u); return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : ''; }
  catch { return ''; }
}
