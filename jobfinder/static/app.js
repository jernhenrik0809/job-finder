// ---------- state ----------
let cvId = null;
let llmAvailable = false;
const selected = new Map();      // jobId -> job object (roles picked for drafting)
const jobsById = new Map();      // jobId -> job object (all rendered jobs)
const draftJobs = new Map();     // draftId -> job object (for regenerate)

const $ = (sel) => document.querySelector(sel);
const el = {
  dropzone: $('#dropzone'), fileInput: $('#fileInput'), browseBtn: $('#browseBtn'),
  pasteToggle: $('#pasteToggle'), pasteArea: $('#pasteArea'), cvText: $('#cvText'), usePaste: $('#usePaste'),
  profileCard: $('#profileCard'), pTitle: $('#pTitle'), pSeniority: $('#pSeniority'),
  pYears: $('#pYears'), pSkills: $('#pSkills'),
  keywords: $('#keywords'), location: $('#location'), days: $('#days'), limit: $('#limit'),
  remote: $('#remote'), semantic: $('#semantic'), minScore: $('#minScore'), minScoreVal: $('#minScoreVal'),
  searchBtn: $('#searchBtn'), hint: $('#hint'),
  resultMeta: $('#resultMeta'), warnings: $('#warnings'),
  loading: $('#loading'), empty: $('#empty'), jobs: $('#jobs'), jsearchChk: $('#jsearchChk'),
  // tabs / views
  tabMatches: $('#tabMatches'), tabOutbox: $('#tabOutbox'), outboxCount: $('#outboxCount'),
  viewMatches: $('#view-matches'), viewOutbox: $('#view-outbox'),
  // selection
  selbar: $('#selbar'), selCount: $('#selCount'), clearSel: $('#clearSel'), genDrafts: $('#genDrafts'),
  // outbox
  examples: $('#examples'), addExample: $('#addExample'), exampleFile: $('#exampleFile'),
  tone: $('#tone'), length: $('#length'), useLlm: $('#useLlm'), llmHint: $('#llmHint'), useLlmWrap: $('#useLlmWrap'),
  drafts: $('#drafts'), draftsEmpty: $('#draftsEmpty'), draftLoading: $('#draftLoading'),
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

['dragenter', 'dragover'].forEach(ev => el.dropzone.addEventListener(ev, e => {
  e.preventDefault(); el.dropzone.classList.add('drag');
}));
['dragleave', 'drop'].forEach(ev => el.dropzone.addEventListener(ev, e => {
  e.preventDefault(); el.dropzone.classList.remove('drag');
}));
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
el.tabOutbox.addEventListener('click', () => { switchTab('outbox'); loadOutbox(); });

function switchTab(name) {
  const matches = name === 'matches';
  el.tabMatches.classList.toggle('active', matches);
  el.tabOutbox.classList.toggle('active', !matches);
  el.viewMatches.classList.toggle('hidden', !matches);
  el.viewOutbox.classList.toggle('hidden', matches);
}

// ---------- search ----------
el.searchBtn.addEventListener('click', runSearch);

function selectedSources() {
  return [...document.querySelectorAll('#sources input:checked')].map(i => i.value);
}

async function runSearch() {
  if (!cvId) return;
  const sources = selectedSources();
  if (sources.length === 0) { showWarnings(['Pick at least one job source.']); return; }

  switchTab('matches');
  el.warnings.classList.add('hidden');
  el.empty.classList.add('hidden');
  el.jobs.innerHTML = '';
  selected.clear(); jobsById.clear(); updateSelbar();
  el.loading.classList.remove('hidden');
  el.searchBtn.disabled = true;
  el.resultMeta.textContent = '';

  const body = {
    cv_id: cvId,
    keywords: el.keywords.value.trim(),
    location: el.location.value.trim(),
    sources,
    limit_per_source: parseInt(el.limit.value, 10),
    remote: el.remote.checked,
    days: el.days.value ? parseInt(el.days.value, 10) : null,
    semantic: el.semantic.checked,
    min_score: parseFloat(el.minScore.value),
  };

  try {
    const resp = await fetch('/api/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
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
  const cls = j.score >= 70 ? 'high' : j.score >= 45 ? 'mid' : 'low';
  const url = safeUrl(j.url);

  const matched = (j.matched_skills || []).slice(0, 8).map(s => `<span class="chip matched">${esc(s)}</span>`).join('');
  const missing = (j.missing_skills || []).slice(0, 6).map(s => `<span class="chip missing">${esc(s)}</span>`).join('');

  const sub = [
    j.company ? `<b>${esc(j.company)}</b>` : '',
    j.location ? esc(j.location) : '',
    j.salary ? `💰 ${esc(j.salary)}` : '',
    j.posted ? `🕑 ${esc(j.posted)}` : '',
    `<span class="src">${esc(j.source)}</span>`,
  ].filter(Boolean).join('<span> · </span>');

  const desc = j.description ? `<p class="job-desc">${esc(j.description.slice(0, 280))}${j.description.length > 280 ? '…' : ''}</p>` : '';

  card.innerHTML = `
    <div class="job-pick"><input type="checkbox" aria-label="Select for drafting" /></div>
    <div class="score ${cls}">${Math.round(j.score)}<small>match</small></div>
    <div class="job-main">
      <h3>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : esc(j.title)}</h3>
      <div class="job-sub">${sub}</div>
      ${desc}
      ${matched ? `<div class="skill-row"><span class="lbl">✓ you have</span>${matched}</div>` : ''}
      ${missing ? `<div class="skill-row" style="margin-top:6px"><span class="lbl">gaps</span>${missing}</div>` : ''}
      ${url ? `<div class="apply"><a href="${esc(url)}" target="_blank" rel="noopener">View &amp; apply ↗</a></div>` : ''}
    </div>`;

  const cb = card.querySelector('.job-pick input');
  cb.addEventListener('change', () => {
    if (cb.checked) selected.set(j.id, j); else selected.delete(j.id);
    updateSelbar();
  });
  return card;
}

// ---------- selection ----------
el.clearSel.addEventListener('click', () => {
  selected.clear();
  document.querySelectorAll('.job-pick input:checked').forEach(c => { c.checked = false; });
  updateSelbar();
});
el.genDrafts.addEventListener('click', generateDrafts);

function updateSelbar() {
  el.selCount.textContent = selected.size;
  el.selbar.classList.toggle('hidden', selected.size === 0);
}

// ---------- outbox: drafts ----------
async function generateDrafts() {
  if (!cvId || selected.size === 0) return;
  const jobs = [...selected.values()];
  switchTab('outbox');
  el.draftsEmpty.classList.add('hidden');
  el.draftLoading.classList.remove('hidden');
  el.genDrafts.disabled = true;

  try {
    const resp = await fetch('/api/drafts/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cv_id: cvId, jobs,
        tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Generation failed');
    (data.drafts || []).forEach((d, i) => { if (jobs[i]) draftJobs.set(d.id, jobs[i]); });
    await loadOutbox();
    // clear the selection now that drafts exist
    selected.clear();
    document.querySelectorAll('.job-pick input:checked').forEach(c => { c.checked = false; });
    updateSelbar();
  } catch (err) {
    showWarnings(['Draft error: ' + err.message]);
    switchTab('matches');
  } finally {
    el.draftLoading.classList.add('hidden');
    el.genDrafts.disabled = false;
  }
}

async function loadOutbox() {
  await loadExamples();
  try {
    const data = await (await fetch('/api/drafts')).json();
    renderDrafts(data.drafts || []);
  } catch { /* ignore */ }
}

function renderDrafts(drafts) {
  el.outboxCount.textContent = drafts.length;
  el.draftsEmpty.classList.toggle('hidden', drafts.length > 0);
  el.drafts.innerHTML = '';
  drafts.forEach(d => el.drafts.appendChild(draftCard(d)));
}

function draftCard(d) {
  const card = document.createElement('div');
  card.className = 'draft' + (d.status === 'ready' ? ' ready' : '');
  const url = safeUrl(d.job_url);
  const titleHtml = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(d.job_title)}</a>`
    : esc(d.job_title);
  const genTag = d.generator === 'llm'
    ? '<span class="gen-tag llm">✨ Claude</span>'
    : '<span class="gen-tag">template</span>';

  card.innerHTML = `
    <div class="draft-head">
      <h3>${titleHtml}${d.company ? ' — ' + esc(d.company) : ''}</h3>
      ${genTag}
    </div>
    <input class="subject" value="${esc(d.subject)}" />
    <textarea spellcheck="true">${esc(d.body)}</textarea>
    ${d.note ? `<p class="draft-note">⚠ ${esc(d.note)}</p>` : ''}
    <div class="draft-actions">
      <button class="btn mini ok save">Save</button>
      <button class="btn mini ghost copy">Copy</button>
      <button class="btn mini ghost download">Download</button>
      <button class="btn mini ghost regen">Regenerate</button>
      <span class="msg copied" style="display:none">saved</span>
      <span class="spacer"></span>
      <button class="btn mini ghost ready">${d.status === 'ready' ? '✓ Ready' : 'Mark ready'}</button>
      <button class="btn mini danger del">Delete</button>
    </div>`;

  const subjectEl = card.querySelector('.subject');
  const bodyEl = card.querySelector('textarea');
  const msg = card.querySelector('.msg');
  const flash = (t) => { msg.textContent = t; msg.style.display = 'inline'; setTimeout(() => { msg.style.display = 'none'; }, 1500); };

  card.querySelector('.save').addEventListener('click', async () => {
    await fetch(`/api/drafts/${d.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: subjectEl.value, body: bodyEl.value }),
    });
    flash('saved');
  });
  card.querySelector('.copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(`Subject: ${subjectEl.value}\n\n${bodyEl.value}`); flash('copied'); }
    catch { flash('copy blocked'); }
  });
  card.querySelector('.download').addEventListener('click', () => {
    window.location.href = `/api/drafts/${d.id}/export`;
  });
  card.querySelector('.regen').addEventListener('click', async () => {
    const job = draftJobs.get(d.id) || { title: d.job_title, company: d.company, url: d.job_url, source: d.job_source, score: d.score };
    await fetch(`/api/drafts/${d.id}`, { method: 'DELETE' });
    draftJobs.delete(d.id);
    el.draftLoading.classList.remove('hidden');
    try {
      const resp = await fetch('/api/drafts/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_id: cvId, jobs: [job], tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked }),
      });
      const data = await resp.json();
      (data.drafts || []).forEach(nd => draftJobs.set(nd.id, job));
    } finally {
      el.draftLoading.classList.add('hidden');
      loadOutbox();
    }
  });
  card.querySelector('.ready').addEventListener('click', async () => {
    const next = d.status === 'ready' ? 'draft' : 'ready';
    await fetch(`/api/drafts/${d.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: next }),
    });
    d.status = next;
    card.classList.toggle('ready', next === 'ready');
    card.querySelector('.ready').textContent = next === 'ready' ? '✓ Ready' : 'Mark ready';
  });
  card.querySelector('.del').addEventListener('click', async () => {
    await fetch(`/api/drafts/${d.id}`, { method: 'DELETE' });
    draftJobs.delete(d.id);
    loadOutbox();
  });
  return card;
}

// ---------- outbox: style examples ----------
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

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Only allow absolute http(s) links; block empty, relative and javascript:/data: URLs.
function safeUrl(u) {
  if (!u) return '';
  try {
    const url = new URL(u);
    return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : '';
  } catch { return ''; }
}
