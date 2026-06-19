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
const tailoringById = new Map(); // app id -> last tailor result (survives drawer re-render)

const $ = (sel) => document.querySelector(sel);
const el = {
  dropzone: $('#dropzone'), fileInput: $('#fileInput'), browseBtn: $('#browseBtn'),
  pasteToggle: $('#pasteToggle'), pasteArea: $('#pasteArea'), cvText: $('#cvText'), usePaste: $('#usePaste'),
  profileCard: $('#profileCard'), pTitle: $('#pTitle'), pSeniority: $('#pSeniority'),
  pYears: $('#pYears'), pSkills: $('#pSkills'),
  editProfileBtn: $('#editProfileBtn'), profileEdit: $('#profileEdit'),
  keywords: $('#keywords'), location: $('#location'), days: $('#days'), limit: $('#limit'),
  remote: $('#remote'), semantic: $('#semantic'), gigsOnly: $('#gigsOnly'), minScore: $('#minScore'), minScoreVal: $('#minScoreVal'),
  searchBtn: $('#searchBtn'), hint: $('#hint'),
  saveSearchBtn: $('#saveSearchBtn'), savedBox: $('#savedBox'), savedList: $('#savedList'), checkNew: $('#checkNew'),
  resultMeta: $('#resultMeta'), warnings: $('#warnings'),
  loading: $('#loading'), empty: $('#empty'), jobs: $('#jobs'),
  tabMatches: $('#tabMatches'), tabPipeline: $('#tabPipeline'), tabInsights: $('#tabInsights'), pipelineCount: $('#pipelineCount'),
  tabSettings: $('#tabSettings'), viewSettings: $('#view-settings'), settingsBody: $('#settingsBody'),
  tabBench: $('#tabBench'), viewBench: $('#view-bench'),
  consultantForm: $('#consultantForm'), consultantList: $('#consultantList'), benchAddToggle: $('#benchAddToggle'),
  clientForm: $('#clientForm'), clientList: $('#clientList'), clientAddToggle: $('#clientAddToggle'),
  houseForm: $('#houseForm'), gigForm: $('#gigForm'), rankLoading: $('#rankLoading'), rankResults: $('#rankResults'),
  propBar: $('#propBar'), propSelCount: $('#propSelCount'), propClearSel: $('#propClearSel'), genProposalBtn: $('#genProposalBtn'),
  pursueGigBtn: $('#pursueGigBtn'),
  propLoading: $('#propLoading'), proposalPanel: $('#proposalPanel'),
  oppLoading: $('#oppLoading'), oppList: $('#oppList'),
  viewMatches: $('#view-matches'), viewPipeline: $('#view-pipeline'), viewInsights: $('#view-insights'),
  insightsEmpty: $('#insightsEmpty'), insightsBody: $('#insightsBody'),
  selbar: $('#selbar'), selCount: $('#selCount'), clearSel: $('#clearSel'), genDrafts: $('#genDrafts'),
  examples: $('#examples'), addExample: $('#addExample'), exampleFile: $('#exampleFile'),
  tone: $('#tone'), length: $('#length'), useLlm: $('#useLlm'), llmHint: $('#llmHint'), useLlmWrap: $('#useLlmWrap'),
  egressNote: $('#egressNote'), egressText: $('#egressText'), redactPii: $('#redactPii'),
  board: $('#board'), boardEmpty: $('#boardEmpty'), draftLoading: $('#draftLoading'),
  drawer: $('#drawer'), drawerPanel: $('#drawerPanel'), drawerBackdrop: $('#drawerBackdrop'),
  bellBtn: $('#bellBtn'), bellBadge: $('#bellBadge'), notifPanel: $('#notifPanel'),
};

// ---------- init ----------
function applySources(d) {
  // Enable/disable each keyed source by whether its API key is configured.
  Object.entries(d.keyed || {}).forEach(([src, present]) => {
    const input = document.querySelector(`#sources input[value="${src}"]`);
    if (!input) return;
    const lab = input.closest('.chk');
    input.disabled = !present;
    if (!present) input.checked = false;
    if (lab) { lab.style.opacity = present ? '' : .55; lab.title = present ? '' : `Set the ${src} API key in ⚙ Settings to enable it`; }
  });
}

function applyDraftConfig(d) {
  llmAvailable = !!d.llm_available;
  if (Array.isArray(d.statuses) && d.statuses.length) STATUSES = d.statuses;
  el.useLlm.disabled = !llmAvailable;
  el.useLlmWrap.style.opacity = llmAvailable ? '' : .55;
  if (llmAvailable) {
    el.llmHint.textContent = `(${d.model})`;
    if (d.llm_egress && el.egressNote && el.redactPii) {
      el.egressText.textContent = `With Claude on, ${d.llm_egress.sends} are sent to ${d.llm_egress.provider}.`;
      el.redactPii.checked = d.llm_egress.redact_default !== false;
      el.egressNote.classList.remove('hidden');
    }
  } else {
    el.useLlm.checked = false;
    el.llmHint.textContent = '(add an Anthropic key in ⚙ Settings to enable — using offline template)';
    if (el.egressNote) el.egressNote.classList.add('hidden');
  }
}

function refreshKeyGating() {
  fetch('/api/sources').then(r => r.json()).then(applySources).catch(() => {});
  fetch('/api/draft-config').then(r => r.json()).then(applyDraftConfig).catch(() => {});
}
refreshKeyGating();

// ---------- notifications (alerts inbox) ----------
let _notifs = [];

async function loadNotifications() {
  try {
    const d = await (await fetch('/api/notifications')).json();
    _notifs = d.notifications || [];
    const unread = d.unread || 0;
    el.bellBadge.textContent = unread > 99 ? '99+' : String(unread);
    el.bellBadge.classList.toggle('hidden', unread === 0);
    if (!el.notifPanel.classList.contains('hidden')) renderNotifPanel();
  } catch { /* ignore — notifications are best-effort */ }
}

function renderNotifPanel() {
  if (!_notifs.length) {
    el.notifPanel.innerHTML = `<div class="notif-head"><span>Notifications</span></div>
      <div class="notif-empty">No notifications yet. Turn on background checks in ⚙ Settings to get alerted about new matches.</div>`;
    return;
  }
  const items = _notifs.map(n => {
    const icon = n.kind === 'new_matches' ? '🔎' : n.kind === 'bench_fit' ? '🎯' : '⏰';
    const meta = n.kind === 'new_matches' ? `${n.count} new`
      : n.kind === 'bench_fit' ? `${n.count} fit${n.count === 1 ? '' : 's'}` : 'reminder';
    return `<div class="notif-item${n.read ? '' : ' unread'}" data-id="${esc(n.id)}" data-kind="${esc(n.kind)}" data-ref="${esc(n.ref_id)}">
        <span class="notif-ic">${icon}</span>
        <div class="notif-bd"><div class="notif-title">${esc(n.title)} <i class="muted small">${esc(meta)}</i></div>
          <div class="muted small">${esc(n.body)}</div></div>
        <button class="notif-x" data-id="${esc(n.id)}" title="Dismiss" aria-label="Dismiss">✕</button>
      </div>`;
  }).join('');
  el.notifPanel.innerHTML = `<div class="notif-head"><span>Notifications</span>
      <button id="notifReadAll" class="link-btn small" type="button">Mark all read</button></div>
    <div class="notif-list">${items}</div>`;
  el.notifPanel.querySelector('#notifReadAll').addEventListener('click', markAllNotifsRead);
  el.notifPanel.querySelectorAll('.notif-x').forEach(b =>
    b.addEventListener('click', (e) => { e.stopPropagation(); dismissNotif(b.dataset.id); }));
  el.notifPanel.querySelectorAll('.notif-item').forEach(it =>
    it.addEventListener('click', () => openNotif(it.dataset.kind, it.dataset.ref, it.dataset.id)));
}

async function openNotif(kind, ref, id) {
  toggleNotifPanel(false);
  await fetch(`/api/notifications/${id}/read`, { method: 'POST' }).catch(() => {});
  if (kind === 'new_matches' && ref) {
    runSavedSearch(ref);
  } else if (kind === 'bench_fit') {
    switchTab('bench');                 // take the operator to the bench to staff/pursue the fit
  } else if (kind === 'reminder' && ref) {
    switchTab('pipeline');
    await loadPipeline();
    openDrawer(ref);
  }
  loadNotifications();
}

async function markAllNotifsRead() {
  await fetch('/api/notifications/read', { method: 'POST' }).catch(() => {});
  loadNotifications();
}

async function dismissNotif(id) {
  await fetch(`/api/notifications/${id}`, { method: 'DELETE' }).catch(() => {});
  loadNotifications();
}

function toggleNotifPanel(show) {
  const open = show === undefined ? el.notifPanel.classList.contains('hidden') : show;
  el.notifPanel.classList.toggle('hidden', !open);
  if (open) renderNotifPanel();
}

el.bellBtn.addEventListener('click', (e) => { e.stopPropagation(); toggleNotifPanel(); });
document.addEventListener('click', (e) => {
  if (!el.notifPanel.classList.contains('hidden') && !e.target.closest('.notif-wrap')) toggleNotifPanel(false);
});
loadNotifications();

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

let currentProfile = null;

function renderProfile(p) {
  currentProfile = p;
  el.profileCard.classList.remove('hidden');
  el.pTitle.textContent = (p.titles && p.titles[0]) || (p.name || 'CV loaded');
  el.pSeniority.textContent = p.seniority || '';
  el.pSeniority.classList.toggle('hidden', !p.seniority);
  el.pYears.textContent = p.years_experience ? `${p.years_experience} yrs exp` : '';
  el.pYears.classList.toggle('hidden', !p.years_experience);
  el.pSkills.innerHTML = '';
  (p.skills || []).slice(0, 30).forEach(s => {
    const c = document.createElement('span'); c.className = 'chip'; c.textContent = s;
    el.pSkills.appendChild(c);
  });
  if (!el.keywords.value && p.suggested_keywords) el.keywords.value = p.suggested_keywords;
  if (!el.location.value && p.location) el.location.value = p.location;
  closeProfileEdit();
}

// ---------- confirm / edit the parsed profile ----------
// The whole funnel rests on the CV parser's guesses — let the user fix them.
function closeProfileEdit() {
  el.profileEdit.classList.add('hidden');
  el.profileEdit.innerHTML = '';
  el.profileCard.classList.remove('editing');
}

function openProfileEdit() {
  if (!currentProfile) return;
  const p = currentProfile;
  let editSkills = [...(p.skills || [])];
  const box = el.profileEdit;
  box.innerHTML = `
    <div class="pe-grid">
      <label>Name<input id="peName" type="text"></label>
      <label>Target title(s)<input id="peTitles" type="text" placeholder="comma-separated"></label>
      <label>Location<input id="peLocation" type="text"></label>
      <label>Years exp<input id="peYears" type="number" min="0" max="80"></label>
      <label>Level<select id="peSeniority">
        <option value="">(unknown)</option><option value="junior">junior</option><option value="mid">mid</option><option value="senior">senior</option><option value="lead">lead</option>
      </select></label>
    </div>
    <p class="muted small" style="margin:.6rem 0 .2rem">Skills — click × to remove</p>
    <div id="peSkills" class="chips"></div>
    <div class="pe-add"><input id="peSkillInput" type="text" placeholder="add a skill"><button id="peAddSkill" type="button">＋ Add</button></div>
    <div class="pe-actions"><button id="peSave" type="button" class="primary">Save profile</button><button id="peCancel" type="button">Cancel</button></div>`;
  box.classList.remove('hidden');
  el.profileCard.classList.add('editing');
  box.querySelector('#peName').value = p.name || '';
  box.querySelector('#peTitles').value = (p.titles || []).join(', ');
  box.querySelector('#peLocation').value = p.location || '';
  box.querySelector('#peYears').value = p.years_experience || '';
  box.querySelector('#peSeniority').value = p.seniority || '';

  const skillsBox = box.querySelector('#peSkills');
  function renderEditSkills() {
    skillsBox.innerHTML = '';
    editSkills.forEach((s, i) => {
      const c = document.createElement('span'); c.className = 'chip removable'; c.textContent = s;
      const x = document.createElement('button');
      x.type = 'button'; x.className = 'chip-x'; x.textContent = '×';
      x.setAttribute('aria-label', `remove ${s}`);
      x.addEventListener('click', () => { editSkills.splice(i, 1); renderEditSkills(); });
      c.appendChild(x); skillsBox.appendChild(c);
    });
  }
  renderEditSkills();
  function addSkill() {
    const inp = box.querySelector('#peSkillInput');
    const v = inp.value.trim();
    if (v && !editSkills.some(s => s.toLowerCase() === v.toLowerCase())) editSkills.push(v);
    inp.value = ''; inp.focus(); renderEditSkills();
  }
  box.querySelector('#peAddSkill').addEventListener('click', addSkill);
  box.querySelector('#peSkillInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addSkill(); }
  });
  box.querySelector('#peCancel').addEventListener('click', closeProfileEdit);
  box.querySelector('#peSave').addEventListener('click', () => saveProfile(editSkills, box));
}

async function saveProfile(editSkills, box) {
  if (!cvId) return;
  const titles = box.querySelector('#peTitles').value.split(',').map(s => s.trim()).filter(Boolean);
  const yearsRaw = box.querySelector('#peYears').value.trim();
  const payload = {
    name: box.querySelector('#peName').value.trim(),
    titles, skills: editSkills,
    location: box.querySelector('#peLocation').value.trim(),
    seniority: box.querySelector('#peSeniority').value,
  };
  if (yearsRaw !== '') payload.years_experience = parseInt(yearsRaw, 10);
  const saveBtn = box.querySelector('#peSave'); saveBtn.disabled = true;
  try {
    const resp = await fetch(`/api/profile/${cvId}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Save failed');
    renderProfile(data.profile);     // re-render read-only view + close edit
    el.hint.textContent = 'Profile updated — your edits will be used for matching.';
  } catch (err) { showWarnings(['Profile: ' + err.message]); saveBtn.disabled = false; }
}

if (el.editProfileBtn) el.editProfileBtn.addEventListener('click', () => {
  if (el.profileEdit.classList.contains('hidden')) openProfileEdit(); else closeProfileEdit();
});

// ---------- tabs ----------
el.tabMatches.addEventListener('click', () => switchTab('matches'));
el.tabPipeline.addEventListener('click', () => { switchTab('pipeline'); loadPipeline(); });
el.tabInsights.addEventListener('click', () => { switchTab('insights'); loadInsights(); });
el.tabBench.addEventListener('click', () => { switchTab('bench'); loadBench(); });
el.tabSettings.addEventListener('click', () => { switchTab('settings'); loadSettings(); });

function switchTab(name) {
  const map = {
    matches: [el.tabMatches, el.viewMatches],
    pipeline: [el.tabPipeline, el.viewPipeline],
    insights: [el.tabInsights, el.viewInsights],
    bench: [el.tabBench, el.viewBench],
    settings: [el.tabSettings, el.viewSettings],
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
    gigs_only: !!(el.gigsOnly && el.gigsOnly.checked),
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
  // Calibrated band from the matcher (falls back to thresholds for older payloads).
  const band = (j.explanation && j.explanation.band) ||
    (j.score >= 65 ? 'strong' : j.score >= 40 ? 'good' : j.score >= 25 ? 'fair' : 'weak');
  const bandLabel = (j.explanation && j.explanation.band_label) || 'Match';
  const bandWord = bandLabel.split(' ')[0];     // "Strong" / "Good" / "Fair" / "Weak"
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
    <div class="score-wrap">
      <div class="score ${band}" title="${esc(bandLabel)}">${Math.round(j.score)}<small>${esc(bandWord)}</small></div>
      ${j.explanation && j.explanation.components && j.explanation.components.length ? `<button class="why-toggle" type="button" aria-expanded="false">Why?</button>` : ''}
    </div>
    <div class="job-main">
      <h3>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(j.title)}</a>` : esc(j.title)}${currentNewIds.has(j.id) ? '<span class="new-flag">NEW</span>' : ''}</h3>
      <div class="job-sub">${sub}</div>
      ${desc}
      ${matched ? `<div class="skill-row"><span class="lbl">✓ you have</span>${matched}</div>` : ''}
      ${missing ? `<div class="skill-row" style="margin-top:6px"><span class="lbl">gaps</span>${missing}</div>` : ''}
      ${whyPanel(j)}
      <button class="save-pipeline${isSaved ? ' saved' : ''}" type="button">${isSaved ? '✓ Saved' : '＋ Save to pipeline'}</button>
      ${url ? ` <a class="apply-link" href="${esc(url)}" target="_blank" rel="noopener" style="margin-left:8px;font-size:13px">View ↗</a>` : ''}
    </div>`;
  const cb = card.querySelector('.job-pick input');
  cb.addEventListener('change', () => { if (cb.checked) selected.set(j.id, j); else selected.delete(j.id); updateSelbar(); });
  const saveBtn = card.querySelector('.save-pipeline');
  saveBtn.addEventListener('click', () => saveToPipeline(j, saveBtn));
  const whyBtn = card.querySelector('.why-toggle');
  if (whyBtn) whyBtn.addEventListener('click', () => {
    const panel = card.querySelector('.why');
    const open = panel.hasAttribute('hidden');
    if (open) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
    whyBtn.setAttribute('aria-expanded', String(open));
  });
  return card;
}

// "Why this score?" — the matcher's explanation object rendered as a breakdown.
// Component bars show signal strength; the pts show the share each adds to the score
// (they sum to the score), tied to the published 55/30/15 formula.
function whyPanel(j) {
  const ex = j.explanation;
  if (!ex || !ex.components || !ex.components.length) return '';
  const bars = ex.components.map(c => `
    <div class="why-comp${c.bonus ? ' bonus' : ''}">
      <div class="why-row"><span class="why-lbl">${c.bonus ? '✦ ' : ''}${esc(c.label)}</span>
        <span class="why-pts">${c.bonus ? '+' : ''}${c.points} / ${c.max_points} pts</span></div>
      <div class="why-track"><div class="why-fill" style="width:${Math.max(0, Math.min(100, c.strength))}%"></div></div>
    </div>`).join('');
  const reasons = (ex.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')
    + (ex.boost_reasons || []).map(r => `<li class="boost">✦ ${esc(r)}</li>`).join('');
  const note = ex.skills_detected === false
    ? `<p class="why-note">No skills were detected in this posting, so skill overlap was left out and the score reflects text &amp; title only.</p>` : '';
  return `
    <div class="why" hidden>
      <div class="why-head">Why ${Math.round(j.score)}?${ex.band_label ? ` · <span class="why-band">${esc(ex.band_label)}</span>` : ''}</div>
      <div class="why-bars">${bars}</div>
      ${reasons ? `<ul class="why-reasons">${reasons}</ul>` : ''}
      ${note}
      <p class="why-formula">Score = 55% text similarity · 30% skill overlap · 15% title match, normalised to the signals present.</p>
    </div>`;
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
    gigs_only: !!(el.gigsOnly && el.gigsOnly.checked),
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
      body: JSON.stringify({ cv_id: cvId, jobs, tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked, redact_pii: !!(el.redactPii && el.redactPii.checked) }),
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
      ${guardrailBadges(a)}
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
      <span class="lbl">Tailor résumé</span>
      <div id="tailorOut" class="tailor-out"></div>
      <div class="dw-actions"><button class="btn mini ghost tailor">✨ Tailor résumé to this job</button></div>
    </div>

    <div class="dw-section">
      <span class="lbl">Timeline</span>
      <ul class="timeline">${events || '<li>No events yet.</li>'}</ul>
    </div>`;

  el.drawer.classList.remove('hidden');
  wireDrawer(a.id);

  // restore a previously-computed tailor result (survives status changes / regenerate)
  if (tailoringById.has(id)) {
    const out = el.drawerPanel.querySelector('#tailorOut');
    if (out) renderTailoring(out, tailoringById.get(id));
    const tb = el.drawerPanel.querySelector('.tailor');
    if (tb) tb.textContent = 'Re-tailor';
  }
}

// Offline guardrail badges — placeholders + skills claimed but not on the CV.
// Verified server-side on every letter, so "never fabricates" is checked, not just promised.
function guardrailBadges(a) {
  const g = a.guardrails || [];
  if (!g.length) return '';
  return `<div class="dw-guards">` + g.map(f => `
    <div class="guard guard-${esc(f.severity)}">
      <span class="guard-msg">${f.type === 'placeholder' ? '⚠' : '⚑'} ${esc(f.message)}</span>
      ${(f.items && f.items.length) ? `<div class="guard-items">${f.items.map(i => `<code>${esc(i)}</code>`).join(' ')}</div>` : ''}
    </div>`).join('') + `</div>`;
}

// Briefly show a "saved" indicator. Module-scope so every panel (drawer, settings) can use it.
function flash(sel) {
  const m = document.querySelector(sel);
  if (m) { m.style.display = 'inline'; setTimeout(() => { m.style.display = 'none'; }, 1400); }
}

function wireDrawer(id) {
  const panel = el.drawerPanel;
  const subjectEl = panel.querySelector('.subject');
  const bodyEl = panel.querySelector('.body');
  const notesEl = panel.querySelector('.notes');

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
    if (updated) {
      appsById.set(id, updated); renderBoard();
      if (!el.drawer.classList.contains('hidden')) openDrawer(id);   // refresh guardrail badges
    }
  });

  panel.querySelector('.regen').addEventListener('click', async () => {
    const btn = panel.querySelector('.regen'); btn.disabled = true; btn.textContent = 'Writing…';
    try {
      const resp = await fetch(`/api/applications/${id}/regenerate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_id: cvId || '', tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked, redact_pii: !!(el.redactPii && el.redactPii.checked) }),
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

  panel.querySelector('.tailor').addEventListener('click', async () => {
    const btn = panel.querySelector('.tailor'); btn.disabled = true; btn.textContent = 'Tailoring…';
    try {
      const resp = await fetch(`/api/applications/${id}/tailor`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_id: cvId || '', use_llm: el.useLlm.checked, redact_pii: !!(el.redactPii && el.redactPii.checked) }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || 'Tailoring failed');
      tailoringById.set(id, data);     // cache so a status change / regenerate doesn't wipe it
      const out = panel.querySelector('#tailorOut');
      if (out) renderTailoring(out, data);
      btn.textContent = 'Re-tailor';
    } catch (err) { showWarnings(['Tailor: ' + err.message]); btn.textContent = 'Retry'; }
    finally { btn.disabled = false; }
  });

  panel.querySelector('.del').addEventListener('click', async () => {
    const a = appsById.get(id);
    const jobId = a && a.job && a.job.id;
    await fetch(`/api/applications/${id}`, { method: 'DELETE' });
    appsById.delete(id);
    tailoringById.delete(id);
    if (jobId) {                       // un-mark the originating match card's Save button
      savedJobIds.delete(jobId);
      const btn = document.querySelector(`.job[data-job-id="${jobId}"] .save-pipeline`);
      if (btn) { btn.classList.remove('saved'); btn.textContent = '＋ Save to pipeline'; }
    }
    renderBoard();
    closeDrawer();
  });
}

function renderTailoring(box, data) {
  const skills = (data.emphasize_skills || []).map(s => `<span class="chip matched">${esc(s)}</span>`).join('');
  const gaps = (data.gaps || []).map(s => `<span class="chip missing">${esc(s)}</span>`).join('');
  const bullets = (data.bullets || []).map(b => `<li>
      ${b.rewritten ? `<div class="b-rw">${esc(b.rewritten)}</div><div class="b-src">from your CV: ${esc(b.text)}</div>` : `<div>${esc(b.text)}</div>`}
      <span class="b-score">${b.score || 0}</span></li>`).join('');
  box.innerHTML = `
    ${data.note ? `<p class="dw-note">⚠ ${esc(data.note)}</p>` : ''}
    ${skills ? `<div class="t-row"><span class="t-lbl">Emphasize</span><span class="chips">${skills}</span></div>` : ''}
    ${bullets ? `<div class="t-lbl" style="margin-top:10px">Lead with these — ranked from your real CV</div><ul class="tailor-bullets">${bullets}</ul>`
      : '<p class="muted small">No résumé bullets detected — make sure your CV includes experience lines.</p>'}
    ${gaps ? `<div class="t-row" style="margin-top:8px"><span class="t-lbl">Address gaps</span><span class="chips">${gaps}</span></div>` : ''}
    <p class="muted small">${data.generator === 'llm'
      ? '✨ Bullets rephrased by Claude — grounded in your CV; the original is shown for you to verify.'
      : 'Selected & ranked from your real CV — nothing invented.'}</p>`;
}

// ---------- settings ----------
const _KEY_FIELDS = [
  { id: 'anthropic_key', group: 'anthropic', env: 'ANTHROPIC_API_KEY', label: 'Anthropic API key', hint: 'Enables the Claude letter & résumé writer', ph: 'sk-ant-…' },
  { id: 'rapidapi_key', group: 'rapidapi', env: 'RAPIDAPI_KEY', label: 'RapidAPI key (JSearch)', hint: 'Enables the JSearch source', ph: '…' },
  { id: 'adzuna_app_id', group: 'adzuna', env: 'ADZUNA_APP_ID', label: 'Adzuna app id', hint: 'With the app key, enables the Adzuna (Denmark) source', ph: '…' },
  { id: 'adzuna_app_key', group: 'adzuna', env: 'ADZUNA_APP_KEY', label: 'Adzuna app key', hint: '', ph: '…' },
  { id: 'jooble_key', group: 'jooble', env: 'JOOBLE_API_KEY', label: 'Jooble API key', hint: 'Enables the Jooble source', ph: '…' },
  { id: 'careerjet_affid', group: 'careerjet', env: 'CAREERJET_AFFID', label: 'Careerjet affiliate id', hint: 'Enables the Careerjet (da_DK) source — free at careerjet.com/partners/api', ph: '…' },
  { id: 'freelancer_token', group: 'freelancer', env: 'FREELANCER_TOKEN', label: 'Freelancer.com token', hint: 'Enables the Freelancer.com gigs source — free OAuth token at freelancer.com/api/docs', ph: '…' },
  { id: 'findwork_token', group: 'findwork', env: 'FINDWORK_TOKEN', label: 'Findwork API token', hint: 'Enables the Findwork (tech/remote) source — free at findwork.dev/account', ph: '…' },
];

async function loadSettings() {
  try { renderSettings(await (await fetch('/api/settings')).json()); }
  catch { el.settingsBody.innerHTML = '<p class="muted">Could not load settings.</p>'; }
}

function renderSettings(s) {
  const present = s.present || {}, locked = s.env_locked || {};
  const models = (s.models || []).map(m =>
    `<option value="${esc(m.id)}"${m.id === s.model ? ' selected' : ''}>${esc(m.label)} — ${esc(m.cost)}, ${esc(m.per_letter)}/letter</option>`).join('');
  const rows = _KEY_FIELDS.map(f => {
    const has = !!present[f.group], lk = !!locked[f.id];
    const status = lk ? `<span class="set-env">set via ${esc(f.env)}</span>`
      : has ? '<span class="set-ok">✓ configured</span>' : '<span class="set-no">not set</span>';
    const ph = lk ? `controlled by ${f.env}` : (has ? 'configured — type to replace' : f.ph);
    return `<div class="set-row">
      <label>${esc(f.label)} ${status}</label>
      ${f.hint ? `<div class="muted small">${esc(f.hint)}</div>` : ''}
      <input type="password" autocomplete="off" spellcheck="false" data-key="${f.id}" placeholder="${esc(ph)}"${lk ? ' disabled' : ''} />
    </div>`;
  }).join('');
  el.settingsBody.innerHTML = `
    <p class="muted small">Keys are stored in a local file on your machine — never in the database, and never sent back in a response. An environment variable, if set, always wins.</p>
    <div class="set-section">
      <h3>Claude — AI writer</h3>
      <div class="set-row"><label>Model tier</label>
        <select id="setModel"${locked.model ? ' disabled' : ''}>${models}</select>
        <div class="muted small">Cost is per generated letter, billed to your own Anthropic key. Lower tiers are cheaper and faster.</div></div>
    </div>
    <div class="set-section"><h3>API keys</h3>${rows}</div>
    <div class="set-section" id="alertsSection">
      <h3>Background alerts</h3>
      <div class="muted small">Off by default. When on, the app re-runs your saved searches on a schedule and drops new matches (and follow-up reminders) into the 🔔 inbox. Nothing is emailed or sent anywhere — it's a local, in-app check.</div>
      <div id="alertsBody" class="muted small" style="margin-top:.5rem">Loading…</div>
    </div>
    <div class="set-section">
      <h3>Your data</h3>
      <div class="muted small">Everything is stored locally on this machine. (Note: the database is not yet encrypted at rest — see docs/PRIVACY.md.)</div>
      <div class="row" style="gap:.6rem;margin-top:.5rem">
        <button id="dataExport" class="btn ghost small" type="button">⬇ Export all my data</button>
        <button id="dataWipe" class="btn danger small" type="button">🗑 Delete all my data</button>
      </div>
      <div id="wipeConfirm" class="hidden" style="margin-top:.6rem">
        <div class="muted small">This permanently deletes your CVs, pipeline, saved searches, style examples and notifications from this machine. Your API keys are not affected. Type <b>DELETE</b> to confirm.</div>
        <div class="row" style="gap:.5rem;margin-top:.4rem;align-items:center">
          <input id="wipeText" type="text" placeholder="DELETE" autocomplete="off" style="max-width:150px" />
          <button id="wipeGo" class="btn danger small" type="button">Delete everything</button>
          <button id="wipeCancel" class="btn ghost small" type="button">Cancel</button>
        </div>
      </div>
    </div>
    <div class="set-actions"><button id="setSave" class="btn ok">Save settings</button><span class="msg copied" style="display:none">saved ✓</span></div>`;
  el.settingsBody.querySelector('#setSave').addEventListener('click', saveSettings);
  loadAlertsConfig();
  wireDataRights();
}

function wireDataRights() {
  const $$ = (s) => el.settingsBody.querySelector(s);
  $$('#dataExport').addEventListener('click', async () => {
    try {
      const resp = await fetch('/api/export');
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'jobfinder-export.json';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { showWarnings(['Export failed.']); }
  });
  $$('#dataWipe').addEventListener('click', () => $$('#wipeConfirm').classList.remove('hidden'));
  $$('#wipeCancel').addEventListener('click', () => {
    $$('#wipeConfirm').classList.add('hidden'); $$('#wipeText').value = '';
  });
  $$('#wipeGo').addEventListener('click', async () => {
    if ($$('#wipeText').value.trim() !== 'DELETE') { $$('#wipeText').focus(); return; }
    try {
      await fetch('/api/data/delete-all', { method: 'POST' });
      location.reload();      // simplest correct reset of all in-memory UI state
    } catch { showWarnings(['Delete failed.']); }
  });
}

async function loadAlertsConfig() {
  try { renderAlertsConfig(await (await fetch('/api/alerts/config')).json()); }
  catch { const b = $('#alertsBody'); if (b) b.textContent = 'Could not load alert settings.'; }
}

function renderAlertsConfig(c) {
  const body = $('#alertsBody');
  if (!body) return;
  const intervals = [6, 12, 24].map(h =>
    `<option value="${h}"${(c.interval_hours || 6) === h ? ' selected' : ''}>every ${h} hours</option>`).join('');
  const last = c.last_run ? `last checked ${fmtTime(c.last_run)}` : 'not checked yet';
  body.innerHTML = `
    <label class="chk"><input id="alertsEnabled" type="checkbox"${c.enabled ? ' checked' : ''} /> Check my saved searches in the background</label>
    <div class="row" style="margin-top:.4rem;align-items:center;gap:.6rem">
      <select id="alertsInterval"${c.enabled ? '' : ' disabled'}>${intervals}</select>
      <button id="alertsRunNow" class="btn ghost small" type="button">Check now</button>
      <span class="muted small" id="alertsLast">${esc(last)}</span>
    </div>`;
  const save = async (patch) => {
    try { renderAlertsConfig(await (await fetch('/api/alerts/config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    })).json()); } catch { /* ignore */ }
  };
  $('#alertsEnabled').addEventListener('change', e => save({ enabled: e.target.checked }));
  $('#alertsInterval').addEventListener('change', e => save({ interval_hours: parseInt(e.target.value, 10) }));
  $('#alertsRunNow').addEventListener('click', async (e) => {
    const btn = e.target; btn.disabled = true; btn.textContent = 'checking…';
    try {
      const r = await (await fetch('/api/alerts/run-now', { method: 'POST' })).json();
      btn.textContent = `${r.new_matches || 0} new ✓`;
      loadNotifications();
    } catch { btn.textContent = 'failed'; }
    finally { setTimeout(() => { btn.textContent = 'Check now'; btn.disabled = false; loadAlertsConfig(); }, 2500); }
  });
}

async function saveSettings() {
  const body = {};
  el.settingsBody.querySelectorAll('input[data-key]').forEach(inp => {
    if (!inp.disabled && inp.value.trim() !== '') body[inp.dataset.key] = inp.value.trim();
  });
  const m = el.settingsBody.querySelector('#setModel');
  if (m && !m.disabled) body.model = m.value;
  const btn = el.settingsBody.querySelector('#setSave'); btn.disabled = true;
  try {
    const resp = await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(d.detail || 'Save failed');
    renderSettings(d);                 // re-render with fresh presence; password inputs cleared
    flash('.set-actions .msg');
    refreshKeyGating();                 // newly-added keys light up sources + Claude without a restart
  } catch (err) { showWarnings(['Settings: ' + err.message]); btn.disabled = false; }
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

// ---------- bench (consulting house) ----------
// Field metadata kept from GET /api/consultants so selects always match the server's vocabulary.
let benchMeta = { engagement_types: ['employee', 'associate', 'subcontractor'], data_origins: ['direct_from_subject', 'third_party', 'public_source'], statuses: ['active', 'inactive'] };
let benchInited = false;          // wire the sub-tabs + house/gig forms once
let editingConsultantId = null;   // id when the form is editing an existing consultant
let editingConsultant = null;     // the object being edited (to diff for PATCH)
const proposalSel = new Set();    // consultant ids ticked for a house proposal
let lastGigFields = null;         // the project fields from the most recent rank (reused on generate)
let currentProposal = null;       // the last generated proposal {id, subject, body, project_title, ...}

function loadBench() {
  if (!benchInited) {
    benchInited = true;
    el.viewBench.querySelectorAll('.bench-subtab').forEach(btn =>
      btn.addEventListener('click', () => switchBenchSection(btn.dataset.bench)));
    el.benchAddToggle.addEventListener('click', () => {
      if (el.consultantForm.classList.contains('hidden')) openConsultantForm(); else closeConsultantForm();
    });
    el.clientAddToggle.addEventListener('click', () => {
      if (el.clientForm.classList.contains('hidden')) openClientForm(); else closeClientForm();
    });
    renderHouseForm();
    renderGigForm();
  }
  loadConsultants();
  loadClients();
  loadHouse();
}

function switchBenchSection(name) {
  el.viewBench.querySelectorAll('.bench-subtab').forEach(b => b.classList.toggle('active', b.dataset.bench === name));
  el.viewBench.querySelectorAll('.bench-section').forEach(s => s.classList.toggle('hidden', s.id !== `bench-${name}`));
  if (name === 'clients') loadClients();
  if (name === 'pipeline') loadOpportunities();
}

// ----- A) consultants -----
async function loadConsultants() {
  try {
    const data = await (await fetch('/api/consultants')).json();
    if (Array.isArray(data.engagement_types) && data.engagement_types.length) benchMeta.engagement_types = data.engagement_types;
    if (Array.isArray(data.data_origins) && data.data_origins.length) benchMeta.data_origins = data.data_origins;
    if (Array.isArray(data.statuses) && data.statuses.length) benchMeta.statuses = data.statuses;
    renderConsultants(data.consultants || []);
  } catch { el.consultantList.innerHTML = '<p class="muted small">Could not load the bench.</p>'; }
}

function renderConsultants(list) {
  el.consultantList.innerHTML = '';
  if (!list.length) {
    el.consultantList.innerHTML = '<p class="muted small">No consultants on the bench yet — add one to start staffing gigs.</p>';
    return;
  }
  list.forEach(c => el.consultantList.appendChild(consultantCard(c)));
}

function consultantCard(c) {
  const card = document.createElement('div');
  card.className = 'consultant';
  card.dataset.id = c.id;
  const skills = (c.skills || []).slice(0, 10).map(s => `<span class="chip">${esc(s)}</span>`).join('');
  const avail = [
    c.available_from ? `from ${esc(c.available_from)}` : '',
    c.available_until ? `until ${esc(c.available_until)}` : '',
  ].filter(Boolean).join(' · ');
  const rate = c.sell_rate != null && c.sell_rate !== '' ? `${esc(c.sell_rate)} ${esc(c.currency || '')}`.trim() : '';
  const sub = [
    c.title ? `<b>${esc(c.title)}</b>` : '',
    c.seniority ? esc(c.seniority) : '',
    c.engagement_type ? esc(c.engagement_type) : '',
    rate ? `💰 ${rate}` : '',
  ].filter(Boolean).join('<span> · </span>');
  card.innerHTML = `
    <div class="consultant-main">
      <div class="consultant-head">
        <h4>${esc(c.name || 'Unnamed')}</h4>
        <span class="cstatus st-${esc(c.status || 'active')}">${esc(c.status || 'active')}</span>
      </div>
      ${sub ? `<div class="consultant-sub">${sub}</div>` : ''}
      ${avail ? `<div class="muted small">${esc(avail)}</div>` : ''}
      ${skills ? `<div class="chips" style="margin-top:8px">${skills}</div>` : ''}
    </div>
    <div class="consultant-actions">
      <button class="btn mini ghost c-edit" type="button">Edit</button>
      <button class="btn mini danger c-del" type="button">Delete</button>
    </div>`;
  card.querySelector('.c-edit').addEventListener('click', () => openConsultantForm(c));
  card.querySelector('.c-del').addEventListener('click', () => deleteConsultant(c));
  return card;
}

// Build the add/edit form. Pass a consultant to edit (PATCH only changed fields), or nothing to add.
function openConsultantForm(c) {
  editingConsultantId = c ? c.id : null;
  editingConsultant = c || null;
  const v = c || {};
  const engOpts = benchMeta.engagement_types.map(o =>
    `<option value="${esc(o)}"${o === v.engagement_type ? ' selected' : ''}>${esc(o)}</option>`).join('');
  const statusOpts = benchMeta.statuses.map(o =>
    `<option value="${esc(o)}"${o === (v.status || 'active') ? ' selected' : ''}>${esc(o)}</option>`).join('');
  const senOpts = ['', 'junior', 'mid', 'senior', 'lead', 'principal'].map(o =>
    `<option value="${esc(o)}"${o === (v.seniority || '') ? ' selected' : ''}>${o ? esc(o) : '(unknown)'}</option>`).join('');
  el.consultantForm.innerHTML = `
    <div class="bf-grid">
      <label class="full">Name<input id="cfName" type="text" /></label>
      ${c ? '' : `<label class="full">Paste CV text <i class="muted small">(optional — parsed to pre-fill fields)</i><textarea id="cfText" rows="5" placeholder="Paste the consultant's CV / resume text here…"></textarea></label>`}
      <label class="full">Title<input id="cfTitle" type="text" placeholder="e.g. Senior Cloud Engineer" /></label>
      <label class="full">Key skills <i class="muted small">(comma-separated)</i><input id="cfSkills" type="text" placeholder="e.g. AWS, Terraform, Python" /></label>
      <label>Seniority<select id="cfSeniority">${senOpts}</select></label>
      <label>Engagement<select id="cfEngagement">${engOpts}</select></label>
      <label>Available from<input id="cfFrom" type="date" /></label>
      <label>Available until<input id="cfUntil" type="date" /></label>
      <label>Sell rate<input id="cfRate" type="number" min="0" step="any" placeholder="e.g. 900" /></label>
      <label>Currency<input id="cfCurrency" type="text" placeholder="e.g. DKK" /></label>
      <label>Status<select id="cfStatus">${statusOpts}</select></label>
      <label class="chk full"><input id="cfPresent" type="checkbox" /> Right to present to clients</label>
    </div>
    <div class="bf-actions">
      <button id="cfSave" class="btn primary small" type="button">${c ? 'Save changes' : 'Add to bench'}</button>
      <button id="cfCancel" class="btn ghost small" type="button">Cancel</button>
      <span class="msg copied" style="display:none">saved ✓</span>
    </div>`;
  el.consultantForm.classList.remove('hidden');
  const q = (s) => el.consultantForm.querySelector(s);
  q('#cfName').value = v.name || '';
  q('#cfTitle').value = v.title || '';
  q('#cfSkills').value = (v.skills || []).join(', ');
  q('#cfFrom').value = v.available_from || '';
  q('#cfUntil').value = v.available_until || '';
  q('#cfRate').value = v.sell_rate != null ? v.sell_rate : '';
  q('#cfCurrency').value = v.currency || '';
  q('#cfPresent').checked = c ? !!v.right_to_present : true;   // new consultants are presentable by default
  q('#cfCancel').addEventListener('click', closeConsultantForm);
  q('#cfSave').addEventListener('click', saveConsultant);
}

function closeConsultantForm() {
  el.consultantForm.classList.add('hidden');
  el.consultantForm.innerHTML = '';
  editingConsultantId = null;
  editingConsultant = null;
}

function splitCsv(s) { return (s || '').split(',').map(x => x.trim()).filter(Boolean); }

async function saveConsultant() {
  const q = (s) => el.consultantForm.querySelector(s);
  const fields = {
    name: q('#cfName').value.trim(),
    title: q('#cfTitle').value.trim(),
    skills: splitCsv(q('#cfSkills').value),
    seniority: q('#cfSeniority').value,
    available_from: q('#cfFrom').value || null,
    available_until: q('#cfUntil').value || null,
    sell_rate: q('#cfRate').value.trim() !== '' ? parseFloat(q('#cfRate').value) : null,
    currency: q('#cfCurrency').value.trim(),
    engagement_type: q('#cfEngagement').value,
    status: q('#cfStatus').value,
    right_to_present: q('#cfPresent').checked,
  };
  const btn = q('#cfSave'); btn.disabled = true;
  try {
    if (editingConsultantId) {
      // PATCH only the fields that actually changed.
      const before = editingConsultant || {};
      const patch = {};
      for (const [k, val] of Object.entries(fields)) {
        const old = k === 'skills' ? (before.skills || []).join('|') : (before[k] == null ? '' : before[k]);
        const now = k === 'skills' ? val.join('|') : (val == null ? '' : val);
        if (String(old) !== String(now)) patch[k] = val;
      }
      if (Object.keys(patch).length === 0) { closeConsultantForm(); return; }
      const resp = await fetch(`/api/consultants/${editingConsultantId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Save failed'); }
    } else {
      const text = (q('#cfText') && q('#cfText').value.trim()) || '';
      const body = { ...fields };
      if (text) body.text = text;            // optional CV text the server parses
      const resp = await fetch('/api/consultants', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Add failed'); }
    }
    closeConsultantForm();
    loadConsultants();
  } catch (err) { showWarnings(['Consultant: ' + err.message]); btn.disabled = false; }
}

async function deleteConsultant(c) {
  if (!confirm(`Remove ${c.name || 'this consultant'} from the bench?`)) return;
  try {
    const resp = await fetch(`/api/consultants/${c.id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Delete failed');
    loadConsultants();
  } catch (err) { showWarnings(['Delete: ' + err.message]); }
}

// ----- A2) clients (direct/warm relationships) -----
const clientsById = new Map();        // client id -> ClientObj (also used by opp cards for do_not_bid)
let editingClientId = null;
let editingClient = null;

async function loadClients() {
  try {
    const data = await (await fetch('/api/clients')).json();
    const list = data.clients || [];
    clientsById.clear();
    list.forEach(c => clientsById.set(c.id, c));
    renderClients(list);
    // keep any visible opportunity cards' do-not-bid warnings + selects in sync
    if (oppsById.size && !document.getElementById('bench-pipeline').classList.contains('hidden')) renderOpportunities();
  } catch { el.clientList.innerHTML = '<p class="muted small">Could not load your clients.</p>'; }
}

function renderClients(list) {
  el.clientList.innerHTML = '';
  if (!list.length) {
    el.clientList.innerHTML = '<p class="muted small">No clients yet — add one to track your direct relationships and link them to opportunities.</p>';
    return;
  }
  list.forEach(c => el.clientList.appendChild(clientCard(c)));
}

function clientCard(c) {
  const card = document.createElement('div');
  card.className = 'consultant';        // reuse the bench-list card styling
  card.dataset.id = c.id;
  const contacts = Array.isArray(c.contacts) ? c.contacts : [];
  const projects = Array.isArray(c.past_projects) ? c.past_projects : [];
  const sub = [
    c.sector ? esc(c.sector) : '',
    `${contacts.length} contact${contacts.length === 1 ? '' : 's'}`,
  ].filter(Boolean).join('<span> · </span>');
  const projChips = projects.slice(0, 8).map(p => `<span class="chip">${esc(p)}</span>`).join('');
  const contactLines = contacts.map(ct => {
    const bits = [
      ct.name ? `<b>${esc(ct.name)}</b>` : '',
      ct.role ? esc(ct.role) : '',
      ct.email ? esc(ct.email) : '',
      ct.phone ? esc(ct.phone) : '',
    ].filter(Boolean).join(' · ');
    return bits ? `<div class="client-contact muted small">${bits}</div>` : '';
  }).filter(Boolean).join('');
  card.innerHTML = `
    <div class="consultant-main">
      <div class="consultant-head">
        <h4>${esc(c.name || 'Unnamed client')}</h4>
        ${c.do_not_bid ? '<span class="cstatus dnb-badge">⛔ do not bid</span>' : ''}
      </div>
      ${sub ? `<div class="consultant-sub">${sub}</div>` : ''}
      ${contactLines ? `<div class="client-contacts">${contactLines}</div>` : ''}
      ${projChips ? `<div class="chips" style="margin-top:8px">${projChips}</div>` : ''}
      ${c.notes ? `<div class="muted small" style="margin-top:8px">${esc(c.notes)}</div>` : ''}
    </div>
    <div class="consultant-actions">
      <button class="btn mini ghost cl-edit" type="button">Edit</button>
      <button class="btn mini danger cl-del" type="button">Delete</button>
    </div>`;
  card.querySelector('.cl-edit').addEventListener('click', () => openClientForm(c));
  card.querySelector('.cl-del').addEventListener('click', () => deleteClient(c));
  return card;
}

// One contact row (name / role / email / phone). Used both for existing contacts and blank rows.
function clientContactRow(ct) {
  ct = ct || {};
  return `<div class="client-contact-row">
      <input class="ccName" type="text" placeholder="Contact name" value="${esc(ct.name || '')}" />
      <input class="ccRole" type="text" placeholder="Role" value="${esc(ct.role || '')}" />
      <input class="ccEmail" type="text" placeholder="Email" value="${esc(ct.email || '')}" />
      <input class="ccPhone" type="text" placeholder="Phone" value="${esc(ct.phone || '')}" />
    </div>`;
}

// Build the add/edit form. Pass a client to edit (PATCH only changed fields), or nothing to add.
function openClientForm(c) {
  editingClientId = c ? c.id : null;
  editingClient = c || null;
  const v = c || {};
  const contacts = (Array.isArray(v.contacts) && v.contacts.length) ? v.contacts : [{}];
  el.clientForm.innerHTML = `
    <div class="bf-grid">
      <label class="full">Name<input id="clName" type="text" placeholder="e.g. Novo Nordisk" /></label>
      <label class="full">Sector<input id="clSector" type="text" placeholder="e.g. Pharma" /></label>
      <label class="chk full"><input id="clDnb" type="checkbox" /> Do not bid <i class="muted small">(warn me off this client on opportunities)</i></label>
      <div class="full">
        <span class="bf-sublabel">Contacts <i class="muted small">(name / role / email / phone)</i></span>
        <div id="clContacts">${contacts.map(clientContactRow).join('')}</div>
        <button id="clAddContact" class="link-btn small" type="button">+ add contact</button>
      </div>
      <label class="full">Past projects <i class="muted small">(comma-separated)</i><input id="clProjects" type="text" placeholder="e.g. Cloud migration, Data platform" /></label>
      <label class="full">Notes<textarea id="clNotes" rows="3" placeholder="Anything worth remembering about this relationship…"></textarea></label>
    </div>
    <div class="bf-actions">
      <button id="clSave" class="btn primary small" type="button">${c ? 'Save changes' : 'Add client'}</button>
      <button id="clCancel" class="btn ghost small" type="button">Cancel</button>
      <span class="msg copied" style="display:none">saved ✓</span>
    </div>`;
  el.clientForm.classList.remove('hidden');
  const q = (s) => el.clientForm.querySelector(s);
  q('#clName').value = v.name || '';
  q('#clSector').value = v.sector || '';
  q('#clDnb').checked = !!v.do_not_bid;
  q('#clProjects').value = (Array.isArray(v.past_projects) ? v.past_projects : []).join(', ');
  q('#clNotes').value = v.notes || '';
  q('#clAddContact').addEventListener('click', () => {
    q('#clContacts').insertAdjacentHTML('beforeend', clientContactRow());
  });
  q('#clCancel').addEventListener('click', closeClientForm);
  q('#clSave').addEventListener('click', saveClient);
}

function closeClientForm() {
  el.clientForm.classList.add('hidden');
  el.clientForm.innerHTML = '';
  editingClientId = null;
  editingClient = null;
}

// Read contact rows → drop fully-empty rows.
function readClientContacts() {
  const rows = [...el.clientForm.querySelectorAll('.client-contact-row')];
  return rows.map(r => ({
    name: r.querySelector('.ccName').value.trim(),
    role: r.querySelector('.ccRole').value.trim(),
    email: r.querySelector('.ccEmail').value.trim(),
    phone: r.querySelector('.ccPhone').value.trim(),
  })).filter(ct => ct.name || ct.role || ct.email || ct.phone);
}

async function saveClient() {
  const q = (s) => el.clientForm.querySelector(s);
  const fields = {
    name: q('#clName').value.trim(),
    sector: q('#clSector').value.trim(),
    do_not_bid: q('#clDnb').checked,
    contacts: readClientContacts(),
    past_projects: splitCsv(q('#clProjects').value),
    notes: q('#clNotes').value.trim(),
  };
  if (!fields.name) { showWarnings(['Client: a name is required.']); return; }
  const btn = q('#clSave'); btn.disabled = true;
  try {
    if (editingClientId) {
      // PATCH only the fields that actually changed.
      const before = editingClient || {};
      const patch = {};
      for (const [k, val] of Object.entries(fields)) {
        let old, now;
        if (k === 'past_projects') { old = (before.past_projects || []).join('|'); now = val.join('|'); }
        else if (k === 'contacts') { old = JSON.stringify(before.contacts || []); now = JSON.stringify(val); }
        else if (k === 'do_not_bid') { old = !!before.do_not_bid; now = !!val; }
        else { old = before[k] == null ? '' : before[k]; now = val == null ? '' : val; }
        if (String(old) !== String(now)) patch[k] = val;
      }
      if (Object.keys(patch).length === 0) { closeClientForm(); return; }
      const resp = await fetch(`/api/clients/${editingClientId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Save failed'); }
    } else {
      const resp = await fetch('/api/clients', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields),
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Add failed'); }
    }
    closeClientForm();
    loadClients();
  } catch (err) { showWarnings(['Client: ' + err.message]); btn.disabled = false; }
}

async function deleteClient(c) {
  if (!confirm(`Delete the client “${c.name || 'this client'}”?`)) return;
  try {
    const resp = await fetch(`/api/clients/${c.id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Delete failed');
    loadClients();
  } catch (err) { showWarnings(['Delete: ' + err.message]); }
}

// ----- B) house identity -----
const _HOUSE_FIELDS = [
  { id: 'name', label: 'House name', ph: 'e.g. Northbridge Consulting' },
  { id: 'tagline', label: 'Tagline', ph: 'e.g. Senior engineers, on demand' },
  { id: 'voice', label: 'Voice / tone', ph: 'e.g. pragmatic, warm, no fluff', area: true },
  { id: 'signatory', label: 'Signatory', ph: 'e.g. Henrik Andersen, Partner' },
  { id: 'boilerplate', label: 'Boilerplate', ph: 'Standard blurb about your house…', area: true },
  { id: 'contact', label: 'Contact', ph: 'e.g. henrik@northbridge.dk · +45 …' },
  { id: 'website', label: 'Website', ph: 'e.g. https://northbridge.dk' },
];

function renderHouseForm() {
  const rows = _HOUSE_FIELDS.map(f => `
    <label class="full">${esc(f.label)}
      ${f.area ? `<textarea data-house="${f.id}" rows="3" placeholder="${esc(f.ph)}"></textarea>`
        : `<input data-house="${f.id}" type="text" placeholder="${esc(f.ph)}" />`}
    </label>`).join('');
  el.houseForm.innerHTML = `
    <div class="bf-grid">${rows}</div>
    <div class="bf-actions">
      <button id="houseSave" class="btn primary small" type="button">Save house identity</button>
      <span class="msg copied" style="display:none">saved ✓</span>
    </div>`;
  el.houseForm.querySelector('#houseSave').addEventListener('click', saveHouse);
}

async function loadHouse() {
  try {
    const h = await (await fetch('/api/house')).json();
    _HOUSE_FIELDS.forEach(f => {
      const inp = el.houseForm.querySelector(`[data-house="${f.id}"]`);
      if (inp) inp.value = h[f.id] || '';
    });
  } catch { /* default/empty house is fine */ }
}

async function saveHouse() {
  const body = {};
  _HOUSE_FIELDS.forEach(f => {
    const inp = el.houseForm.querySelector(`[data-house="${f.id}"]`);
    if (inp) body[f.id] = inp.value.trim();
  });
  const btn = el.houseForm.querySelector('#houseSave'); btn.disabled = true;
  try {
    const resp = await fetch('/api/house', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || 'Save failed'); }
    flash('#houseForm .msg');
  } catch (err) { showWarnings(['House: ' + err.message]); }
  finally { btn.disabled = false; }
}

// ----- C) staff a gig -----
function renderGigForm() {
  el.gigForm.innerHTML = `
    <div class="bf-grid">
      <label class="full">Title<input id="gigTitle" type="text" placeholder="e.g. Cloud platform lead, 6 months" /></label>
      <label class="full">Gig / brief<textarea id="gigDesc" rows="6" placeholder="Paste the gig description or brief here…"></textarea></label>
      <label class="full">Required skills <i class="muted small">(comma-separated)</i><input id="gigSkills" type="text" placeholder="e.g. AWS, Kubernetes, Go" /></label>
      <label>Location<input id="gigLocation" type="text" placeholder="e.g. Copenhagen" /></label>
      <label>Rate ceiling<input id="gigRate" type="number" min="0" step="any" placeholder="e.g. 1100" /></label>
      <label>Currency<input id="gigCurrency" type="text" placeholder="e.g. DKK" /></label>
      <label>Start date<input id="gigStart" type="date" /></label>
      <label class="chk full"><input id="gigRemote" type="checkbox" /> Remote OK</label>
    </div>
    <div class="bf-actions">
      <button id="rankBtn" class="btn primary small" type="button">Rank bench</button>
    </div>`;
  el.gigForm.querySelector('#rankBtn').addEventListener('click', rankBench);
}

async function rankBench() {
  const q = (s) => el.gigForm.querySelector(s);
  const title = q('#gigTitle').value.trim();
  const description = q('#gigDesc').value.trim();
  if (!title && !description) { showWarnings(['Add a title or paste a gig brief to rank the bench.']); return; }
  const body = {
    title, description,
    skills: splitCsv(q('#gigSkills').value),
    location: q('#gigLocation').value.trim(),
    remote: q('#gigRemote').checked,
    rate_ceiling: q('#gigRate').value.trim() !== '' ? parseFloat(q('#gigRate').value) : null,
    currency: q('#gigCurrency').value.trim(),
    start_date: q('#gigStart').value || null,
  };
  lastGigFields = body;             // reused verbatim when generating a proposal
  el.rankResults.innerHTML = '';
  // a fresh rank invalidates any in-progress proposal selection
  proposalSel.clear(); currentProposal = null;
  el.proposalPanel.classList.add('hidden'); el.proposalPanel.innerHTML = '';
  updatePropBar();
  el.rankLoading.classList.remove('hidden');
  const btn = q('#rankBtn'); btn.disabled = true;
  try {
    const resp = await fetch('/api/bench/rank', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Ranking failed');
    renderRankResults(data);
  } catch (err) { showWarnings(['Rank: ' + err.message]); }
  finally { el.rankLoading.classList.add('hidden'); btn.disabled = false; }
}

function renderRankResults(data) {
  const matches = data.matches || [];
  const meta = [`bench of ${data.bench_size != null ? data.bench_size : matches.length}`,
    `${matches.length} ranked`].join(' · ');
  if (!matches.length) {
    el.rankResults.innerHTML = `<p class="muted small">No consultants to rank — add some to your bench first.</p>`;
    return;
  }
  el.rankResults.innerHTML = `<div class="muted small rank-meta">${esc(meta)}</div>` +
    matches.map(rankCard).join('');
  // wire the per-card "add to proposal" checkboxes (eligible cards only carry one)
  el.rankResults.querySelectorAll('.rank-pick input').forEach(cb => {
    const id = cb.closest('.rank-card').dataset.cid;
    cb.checked = proposalSel.has(id);
    cb.addEventListener('change', () => {
      if (cb.checked) proposalSel.add(id); else proposalSel.delete(id);
      updatePropBar();
    });
  });
  // show the proposal bar as soon as there's at least one eligible consultant to pick
  const hasEligible = matches.some(m => m.eligible && m.consultant && m.consultant.id);
  el.propBar.classList.toggle('hidden', !hasEligible);
  updatePropBar();
}

function rankCard(m) {
  const c = m.consultant || {};
  const cid = c.id || '';
  const score = Math.round(m.score || 0);
  const band = m.eligible ? (score >= 65 ? 'strong' : score >= 40 ? 'good' : 'fair') : 'weak';
  const badge = m.eligible
    ? '<span class="elig-badge ok">eligible</span>'
    : '<span class="elig-badge no">ineligible</span>';
  // only eligible consultants (with an id) can be added to a proposal
  const pick = (m.eligible && cid)
    ? `<label class="rank-pick" title="Add to proposal"><input type="checkbox" aria-label="Add ${esc(c.name || 'consultant')} to proposal" /></label>` : '';
  const dq = (m.disqualifiers || []).length
    ? `<div class="rank-dq"><span class="lbl">✕ disqualifiers</span><ul>${m.disqualifiers.map(d => `<li>${esc(d)}</li>`).join('')}</ul></div>` : '';
  const matched = (m.matched_skills || []).map(s => `<span class="chip matched">${esc(s)}</span>`).join('');
  const missing = (m.missing_skills || []).map(s => `<span class="chip missing">${esc(s)}</span>`).join('');
  const reasons = (m.reasons || []).length
    ? `<ul class="rank-reasons">${m.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : '';
  const notes = (m.notes || []).length
    ? `<div class="rank-notes muted small">${m.notes.map(n => esc(n)).join(' · ')}</div>` : '';
  const sub = [c.title ? `<b>${esc(c.title)}</b>` : '', c.seniority ? esc(c.seniority) : '', c.engagement_type ? esc(c.engagement_type) : '']
    .filter(Boolean).join('<span> · </span>');
  return `
    <div class="rank-card${m.eligible ? '' : ' ineligible'}" data-cid="${esc(cid)}">
      <div class="score-wrap">
        <div class="score ${band}">${score}<small>${m.eligible ? 'fit' : '—'}</small></div>
        ${pick}
      </div>
      <div class="rank-main">
        <div class="rank-head"><h4>${esc(c.name || 'Unnamed')}</h4>${badge}</div>
        ${sub ? `<div class="consultant-sub">${sub}</div>` : ''}
        ${dq}
        ${matched ? `<div class="skill-row"><span class="lbl">✓ has</span>${matched}</div>` : ''}
        ${missing ? `<div class="skill-row" style="margin-top:6px"><span class="lbl">missing</span>${missing}</div>` : ''}
        ${reasons}
        ${notes}
      </div>
    </div>`;
}

// ----- C2) house proposal (generate → review/QA → export) -----
function updatePropBar() {
  el.propSelCount.textContent = proposalSel.size;
  el.genProposalBtn.disabled = proposalSel.size === 0;
}

el.propClearSel.addEventListener('click', () => {
  proposalSel.clear();
  el.rankResults.querySelectorAll('.rank-pick input:checked').forEach(cb => { cb.checked = false; });
  updatePropBar();
});
el.genProposalBtn.addEventListener('click', generateProposal);
if (el.pursueGigBtn) el.pursueGigBtn.addEventListener('click', pursueGig);

async function generateProposal() {
  if (proposalSel.size === 0) return;
  const ids = [...proposalSel];
  const g = lastGigFields || {};
  const body = {
    title: g.title || '',
    description: g.description || '',
    skills: g.skills || [],
    location: g.location || '',
    remote: !!g.remote,
    rate_ceiling: g.rate_ceiling != null ? g.rate_ceiling : null,
    currency: g.currency || '',
    start_date: g.start_date || null,
    consultant_ids: ids,
  };
  el.proposalPanel.classList.add('hidden');
  el.propLoading.classList.remove('hidden');
  el.genProposalBtn.disabled = true;
  try {
    const resp = await fetch('/api/proposals/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Proposal generation failed');
    currentProposal = data.proposal || {};
    renderProposal(data);
  } catch (err) {
    showWarnings(['Proposal: ' + err.message]);
  } finally {
    el.propLoading.classList.add('hidden');
    el.genProposalBtn.disabled = proposalSel.size === 0;
  }
}

// Render the generated proposal into the review panel: editable subject + body,
// the QA (fabrication) findings, and an Export button gated by the QA result.
function renderProposal(data) {
  const p = data.proposal || {};
  const names = (p.consultant_names || []).map(n => `<span class="chip">${esc(n)}</span>`).join('');
  el.proposalPanel.innerHTML = `
    <div class="prop-head">
      <h3>Proposal${p.project_title ? ` — ${esc(p.project_title)}` : ''}</h3>
      ${p.generator ? `<span class="prop-gen">${p.generator === 'llm' ? '✨ Claude' : 'template'}</span>` : ''}
    </div>
    ${names ? `<div class="prop-team"><span class="lbl">Team</span><span class="chips">${names}</span></div>` : ''}
    ${p.note ? `<p class="dw-note">⚠ ${esc(p.note)}</p>` : ''}
    <div id="propQa" class="prop-qa"></div>
    <label class="prop-field">Subject<input id="propSubject" type="text" value="${esc(p.subject || '')}" placeholder="Subject" /></label>
    <label class="prop-field">Proposal body<textarea id="propBody" rows="16" placeholder="The generated proposal will appear here…">${esc(p.body || '')}</textarea></label>
    <div class="prop-actions">
      <button id="propExportBtn" class="btn primary small" type="button">⬇ Export</button>
      <span class="msg copied" style="display:none">exported ✓</span>
    </div>`;
  el.proposalPanel.classList.remove('hidden');
  renderProposalQa(data.qa || [], !!data.blocking);
  el.proposalPanel.querySelector('#propExportBtn').addEventListener('click', exportProposal);
}

// Shared QA renderer — used after generate and again after a refused (409) export.
function renderProposalQa(findings, blocking) {
  const box = el.proposalPanel.querySelector('#propQa');
  if (!box) return;
  if (!findings.length) {
    box.innerHTML = `<div class="prop-qa-ok">✓ Passed fabrication checks — nothing flagged.</div>`;
    return;
  }
  const items = findings.map(f => `
    <div class="guard guard-${f.blocking ? 'high' : 'medium'}">
      <span class="guard-msg">${f.blocking ? '⛔' : '⚑'} ${esc(f.message)}</span>
      ${(f.items && f.items.length) ? `<div class="guard-items">${f.items.map(i => `<code>${esc(i)}</code>`).join(' ')}</div>` : ''}
    </div>`).join('');
  box.innerHTML = `
    <div class="prop-qa-banner ${blocking ? 'blocking' : 'warn'}">
      ${blocking ? '⛔ Export is blocked until these are resolved' : '⚑ Review these before sending'}
    </div>
    <div class="dw-guards">${items}</div>`;
}

async function exportProposal() {
  if (!currentProposal) return;
  const subjectEl = el.proposalPanel.querySelector('#propSubject');
  const bodyEl = el.proposalPanel.querySelector('#propBody');
  const body = bodyEl ? bodyEl.value : '';
  if (!body.trim()) { showWarnings(['Proposal: add some body text before exporting.']); return; }
  const payload = {
    subject: subjectEl ? subjectEl.value : (currentProposal.subject || ''),
    body,
    project_title: (lastGigFields && lastGigFields.title) || currentProposal.project_title || '',
    consultant_ids: [...proposalSel],
  };
  const btn = el.proposalPanel.querySelector('#propExportBtn'); btn.disabled = true;
  try {
    const r = await fetch('/api/proposals/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    if (r.ok) {
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `proposal-${(payload.project_title || 'house').replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 40) || 'house'}.txt`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      flash('.prop-actions .msg');
    } else if (r.status === 409) {
      // QA gate still blocks — surface the blocking findings so the user can fix the text and retry
      const detail = (await r.json().catch(() => ({}))).detail || {};
      renderProposalQa(detail.findings || [], true);
      showWarnings([detail.message || 'Export refused — the proposal still has blocking findings.']);
      el.proposalPanel.querySelector('#propQa').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || `Export failed (${r.status})`);
    }
  } catch (err) {
    showWarnings(['Export: ' + err.message]);
  } finally {
    btn.disabled = false;
  }
}

// ----- D) opportunities (pipeline: pursue → track status + proposal + audit trail) -----
let OPP_STATUSES = ['open', 'proposed', 'won', 'lost', 'shelved'];   // replaced by the server's vocabulary
const oppsById = new Map();          // opportunity id -> OpportunityObj
const oppExpanded = new Set();       // ids whose audit trail is expanded (survives re-render)

async function loadOpportunities() {
  el.oppLoading.classList.remove('hidden');
  if (!clientsById.size) loadClients();   // populate the client select + do-not-bid warnings (re-renders on arrival)
  try {
    const data = await (await fetch('/api/opportunities')).json();
    if (Array.isArray(data.statuses) && data.statuses.length) OPP_STATUSES = data.statuses;
    oppsById.clear();
    (data.opportunities || []).forEach(o => oppsById.set(o.id, o));
    renderOpportunities();
  } catch { el.oppList.innerHTML = '<p class="muted small">Could not load your pipeline.</p>'; }
  finally { el.oppLoading.classList.add('hidden'); }
}

function renderOpportunities() {
  const opps = [...oppsById.values()];
  el.oppList.innerHTML = '';
  if (!opps.length) {
    el.oppList.innerHTML = '<p class="muted small">No opportunities yet — rank your bench against a gig in <b>Staff a gig</b>, then hit <b>★ Pursue this gig</b>.</p>';
    return;
  }
  opps.forEach(o => el.oppList.appendChild(oppCard(o)));
}

function oppCard(o) {
  const card = document.createElement('div');
  card.className = 'opp-card';
  card.dataset.id = o.id;
  const statusOpts = OPP_STATUSES.map(s =>
    `<option value="${esc(s)}"${s === o.status ? ' selected' : ''}>${esc(s)}</option>`).join('');
  const url = safeUrl(o.url);
  const sub = [
    o.source ? `<span class="src">${esc(o.source)}</span>` : '',
    o.location ? esc(o.location) : '',
    o.start_date ? `🗓 ${esc(o.start_date)}` : '',
    (o.rate_ceiling != null && o.rate_ceiling !== '') ? `💰 ≤ ${esc(o.rate_ceiling)} ${esc(o.currency || '')}`.trim() : '',
  ].filter(Boolean).join('<span> · </span>');
  const cur = o.margin_currency || '';
  const team = (o.staffed || []).map(s => {
    const nm = s.consultant_name || s.consultant_id || '';
    const m = (s.margin != null && s.margin !== '') ? ` <span class="opp-margin">margin ${esc(fmtNum(s.margin))} ${esc(cur)}</span>`.trimEnd() : '';
    return `<span class="chip">${esc(nm)}${m}</span>`;
  }).join('');
  const totalMargin = (o.total_margin != null && o.total_margin !== '')
    ? `<div class="opp-total-margin">Total margin: <b>${esc(fmtNum(o.total_margin))} ${esc(cur)}</b></div>`.trimEnd()
    : ((o.staffed || []).some(s => s.margin != null) ? '<div class="opp-total-margin muted">Total margin: —</div>' : '');
  const hasProposal = !!(o.proposal_body && o.proposal_body.trim());
  const propTag = hasProposal
    ? (o.blocking
      ? '<span class="opp-prop blocking">⛔ proposal blocked by QA</span>'
      : '<span class="opp-prop ok">✓ proposal drafted</span>')
    : '<span class="opp-prop none">no proposal yet</span>';
  const qa = (o.qa || []).length ? oppQaHtml(o.qa, !!o.blocking) : '';
  // Client link: a lightweight select populated from the loaded clients, plus a do-not-bid warning.
  const clientList = [...clientsById.values()];
  const linkedClient = o.client_id ? clientsById.get(o.client_id) : null;
  const clientOpts = ['<option value="">— no client —</option>']
    .concat(clientList.map(cl =>
      `<option value="${esc(cl.id)}"${cl.id === o.client_id ? ' selected' : ''}>${esc(cl.name || 'Unnamed')}${cl.do_not_bid ? ' ⛔' : ''}</option>`))
    .join('');
  const clientRow = `
    <div class="opp-client">
      <label class="opp-client-pick"><span class="lbl">Client</span>
        <select class="opp-client-sel">${clientOpts}</select></label>
      ${linkedClient && linkedClient.do_not_bid ? '<span class="opp-dnb-warn">⛔ This client is flagged <b>do not bid</b>.</span>' : ''}
    </div>`;
  const events = (o.events || []).slice().reverse();
  const expanded = oppExpanded.has(o.id);
  const trail = events.length
    ? `<button class="opp-trail-toggle link-btn small" type="button" aria-expanded="${expanded}">${expanded ? 'Hide' : 'Show'} audit trail (${events.length})</button>
       <ul class="timeline opp-trail"${expanded ? '' : ' hidden'}>${events.map(ev =>
        `<li><span class="t">${esc(ev.type || '')}</span><span class="opp-ev-detail">${esc(ev.detail || '')}</span><span class="opp-ev-ts">${esc(fmtOppTime(ev.ts))}</span></li>`).join('')}</ul>`
    : '<p class="muted small">No events yet.</p>';
  card.innerHTML = `
    <div class="opp-head">
      <h4>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(o.title || 'Untitled')}</a>` : esc(o.title || 'Untitled')}</h4>
      <label class="opp-status"><span class="muted small">Status</span>
        <select class="opp-status-sel">${statusOpts}</select></label>
    </div>
    ${sub ? `<div class="opp-sub">${sub}</div>` : ''}
    <div class="opp-tags">${propTag}</div>
    ${team ? `<div class="opp-team"><span class="lbl">Team</span><span class="chips">${team}</span></div>` : ''}
    ${totalMargin}
    ${clientRow}
    ${qa ? `<div class="opp-qa">${qa}</div>` : ''}
    <div class="opp-actions">
      <button class="btn mini ghost opp-gen" type="button">${hasProposal ? 'Regenerate proposal' : 'Generate proposal'}</button>
      <button class="btn mini ghost opp-export" type="button">⬇ Export</button>
      <span class="spacer"></span>
      <button class="btn mini danger opp-del" type="button">Delete</button>
    </div>
    <div class="opp-trail-wrap">${trail}</div>`;

  card.querySelector('.opp-status-sel').addEventListener('change', (e) => changeOppStatus(o.id, e.target.value));
  card.querySelector('.opp-client-sel').addEventListener('change', (e) => linkOppClient(o.id, e.target.value));
  card.querySelector('.opp-gen').addEventListener('click', (e) => generateOppProposal(o.id, e.target));
  card.querySelector('.opp-export').addEventListener('click', (e) => exportOpportunity(o.id, e.target));
  card.querySelector('.opp-del').addEventListener('click', () => deleteOpportunity(o.id));
  const tt = card.querySelector('.opp-trail-toggle');
  if (tt) tt.addEventListener('click', () => {
    const open = !oppExpanded.has(o.id);
    if (open) oppExpanded.add(o.id); else oppExpanded.delete(o.id);
    const ul = card.querySelector('.opp-trail');
    if (ul) ul.toggleAttribute('hidden', !open);
    tt.setAttribute('aria-expanded', String(open));
    tt.textContent = `${open ? 'Hide' : 'Show'} audit trail (${events.length})`;
  });
  return card;
}

// QA findings rendered inside an opportunity card (reuses the proposal guard styles).
function oppQaHtml(findings, blocking) {
  const items = findings.map(f => `
    <div class="guard guard-${f.blocking ? 'high' : 'medium'}">
      <span class="guard-msg">${f.blocking ? '⛔' : '⚑'} ${esc(f.message)}</span>
      ${(f.items && f.items.length) ? `<div class="guard-items">${f.items.map(i => `<code>${esc(i)}</code>`).join(' ')}</div>` : ''}
    </div>`).join('');
  return `<div class="prop-qa-banner ${blocking ? 'blocking' : 'warn'}">
      ${blocking ? '⛔ Export is blocked until these are resolved' : '⚑ Review these before sending'}
    </div><div class="dw-guards">${items}</div>`;
}

async function changeOppStatus(id, status) {
  try {
    const resp = await fetch(`/api/opportunities/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Update failed');
    oppsById.set(id, data);
    renderOpportunities();
  } catch (err) {
    showWarnings(['Opportunity: ' + err.message]);
    renderOpportunities();      // snap the select back to the stored value
  }
}

async function linkOppClient(id, clientId) {
  try {
    const resp = await fetch(`/api/opportunities/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId || null }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Update failed');
    oppsById.set(id, data);
    renderOpportunities();      // re-renders the card → shows/hides the do-not-bid warning
  } catch (err) {
    showWarnings(['Opportunity: ' + err.message]);
    renderOpportunities();      // snap the select back to the stored value
  }
}

async function generateOppProposal(id, btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Drafting…'; }
  try {
    const resp = await fetch(`/api/opportunities/${id}/proposal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tone: el.tone.value, length: el.length.value, use_llm: el.useLlm.checked, redact_pii: !!(el.redactPii && el.redactPii.checked) }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Proposal generation failed');
    if (data.opportunity) oppsById.set(id, data.opportunity);
    renderOpportunities();
    if (data.blocking) showWarnings(['Proposal drafted but blocked by QA — resolve the flagged findings before exporting.']);
  } catch (err) {
    showWarnings(['Proposal: ' + err.message]);
    if (btn) { btn.disabled = false; btn.textContent = 'Retry'; }
  }
}

async function exportOpportunity(id, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await fetch(`/api/opportunities/${id}/export`);
    if (r.ok) {
      const blob = await r.blob();
      const o = oppsById.get(id) || {};
      const name = `opportunity-${(o.title || 'house').replace(/[^a-z0-9]+/gi, '-').toLowerCase().slice(0, 40) || 'house'}.txt`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } else if (r.status === 409) {
      const detail = (await r.json().catch(() => ({}))).detail || {};
      // mark the stored opp as blocking + carry the findings so the card shows them
      const o = oppsById.get(id);
      if (o) { o.blocking = true; o.qa = detail.findings || o.qa || []; oppsById.set(id, o); renderOpportunities(); }
      showWarnings([detail.message || 'Export refused — the proposal still has blocking findings.']);
    } else {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || `Export failed (${r.status})`);
    }
  } catch (err) {
    showWarnings(['Export: ' + err.message]);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deleteOpportunity(id) {
  const o = oppsById.get(id) || {};
  if (!confirm(`Delete the opportunity “${o.title || 'this gig'}” and its audit trail?`)) return;
  try {
    const resp = await fetch(`/api/opportunities/${id}`, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Delete failed');
    oppsById.delete(id);
    oppExpanded.delete(id);
    renderOpportunities();
  } catch (err) { showWarnings(['Delete: ' + err.message]); }
}

// "Pursue this gig" — turn the most recent rank (gig fields + selected consultants) into a tracked opportunity.
// Idempotent on a posting's source uid, so pursuing the same posting twice just surfaces the existing one.
async function pursueGig() {
  const g = lastGigFields || {};
  if (!g.title && !g.description) { showWarnings(['Rank a gig first — pursue needs a title or brief.']); return; }
  const body = {
    title: g.title || '',
    description: g.description || '',
    skills: g.skills || [],
    location: g.location || '',
    remote: !!g.remote,
    rate_ceiling: g.rate_ceiling != null ? g.rate_ceiling : null,
    currency: g.currency || '',
    start_date: g.start_date || null,
    consultant_ids: [...proposalSel],
  };
  if (g.job) { body.job = g.job; body.kind = 'posting'; }    // carries source/source_uid for idempotent create
  const btn = el.pursueGigBtn; if (btn) btn.disabled = true;
  try {
    const resp = await fetch('/api/opportunities', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.detail || 'Could not pursue this gig');
    if (data.id) { oppsById.set(data.id, data); oppExpanded.add(data.id); }
    switchBenchSection('pipeline');     // reveal the pipeline (also reloads from the server)
  } catch (err) {
    showWarnings(['Pursue: ' + err.message]);
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Audit-trail timestamps: accept epoch seconds (like application events) or an ISO string.
function fmtOppTime(ts) {
  if (ts == null || ts === '') return '';
  try {
    const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return String(ts); }
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
// Format a margin/number for display: thousands-separated, no trailing ".00", falls back to raw on non-numeric.
function fmtNum(n) {
  const x = Number(n);
  if (!isFinite(x)) return String(n == null ? '' : n);
  return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function safeUrl(u) {
  if (!u) return '';
  try { const url = new URL(u); return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : ''; }
  catch { return ''; }
}
