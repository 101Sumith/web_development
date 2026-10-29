const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const state = { jobs: [], candidates: [], selected: new Set(), activeView: "overview", searchTimer: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const initials = name => String(name || "?").trim().split(/\s+/).slice(0, 2).map(part => part[0] || "").join("").toUpperCase();
const avatarClass = id => ["avatar-indigo", "avatar-mint", "avatar-peach", "avatar-blue"][Number(id) % 4];

async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) throw new Error(body?.error || `Request failed (${response.status}).`);
  return body;
}

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.textContent = message;
  $("#toastRegion").append(node);
  window.setTimeout(() => node.remove(), 3700);
}

function setView(name) {
  state.activeView = name;
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.view === name));
  const titles = { overview: "Overview", applicants: "Applicants", jobs: "Job descriptions", compare: "Compare candidates", reports: "Reports" };
  $("#pageTitle").textContent = titles[name] || "Overview";
  $("#sidebar").classList.remove("open");
  if (name === "applicants") loadCandidates();
  if (name === "jobs") renderJobs();
  if (name === "reports") updateReportLink();
}

function fillJobSelects() {
  const options = state.jobs.map(job => `<option value="${job.id}">${escapeHtml(job.title)}</option>`).join("");
  const applicant = $("#applicantJobFilter");
  const current = applicant.value;
  applicant.innerHTML = `<option value="">All roles</option>${options}`;
  if (state.jobs.some(job => String(job.id) === current)) applicant.value = current;
  for (const id of ["compareJobSelect", "reportJobSelect"]) {
    const select = $(`#${id}`);
    select.innerHTML = options || `<option value="">Add a role to get started</option>`;
  }
  $("#compareCandidateSelect").innerHTML = state.candidates.map(person => `<option value="${person.id}">${escapeHtml(person.name)} — ${escapeHtml(person.skills.slice(0, 3).join(", ") || "Skills not identified")}</option>`).join("");
  updateReportLink();
}

async function loadWorkspace() {
  try {
    const [dashboard, jobs, candidates] = await Promise.all([api("/api/dashboard"), api("/api/jobs"), api("/api/candidates")]);
    state.jobs = jobs;
    state.candidates = candidates;
    $("#statApplicants").textContent = dashboard.candidate_count;
    $("#statJobs").textContent = dashboard.job_count;
    $("#statMatch").textContent = dashboard.average_match;
    $("#statShortlist").textContent = dashboard.shortlist_count;
    $("#navApplicantCount").textContent = dashboard.candidate_count;
    renderTopMatches(dashboard.top_matches);
    renderRolePreview(jobs);
    fillJobSelects();
    if (state.activeView === "applicants") await loadCandidates();
    if (state.activeView === "jobs") renderJobs();
  } catch (error) {
    toast(error.message, true);
  }
}

function renderTopMatches(items) {
  const target = $("#topMatches");
  if (!items.length) {
    target.innerHTML = `<div class="loading-state">Add a role and an applicant to see matches.</div>`;
    return;
  }
  target.innerHTML = items.map(({ candidate, job }) => {
    const score = candidate.match.score;
    return `<div class="match-row">
      <div class="candidate-identity"><div class="avatar ${avatarClass(candidate.id)}">${escapeHtml(initials(candidate.name))}</div><div><strong>${escapeHtml(candidate.name)}</strong><small>${escapeHtml(job.title)}</small></div></div>
      <div class="match-meter" aria-label="${score}% match"><span style="width:${score}%"></span></div>
      <div class="match-score">${score}%</div><button class="match-open" aria-label="View ${escapeHtml(candidate.name)}" data-profile="${candidate.id}" data-job="${job.id}">↗</button>
    </div>`;
  }).join("");
}

function renderRolePreview(jobs) {
  const target = $("#rolePreview");
  target.innerHTML = jobs.length ? jobs.slice(0, 4).map(job => `<div class="role-preview"><span class="role-bullet">▤</span><div><strong>${escapeHtml(job.title)}</strong><small>${escapeHtml(job.department || "Open position")}</small></div><span class="role-pills">${job.required.length} essentials</span></div>`).join("") : `<div class="loading-state">Create a job description to get started.</div>`;
}

async function loadCandidates() {
  const search = $("#candidateSearch").value.trim();
  const jobId = $("#applicantJobFilter").value;
  const query = new URLSearchParams();
  if (search) query.set("search", search);
  if (jobId) query.set("job_id", jobId);
  try {
    const candidates = await api(`/api/candidates?${query}`);
    state.candidates = candidates.map(candidate => ({ ...candidate, id: Number(candidate.id) }));
    state.selected = new Set([...state.selected].filter(id => state.candidates.some(person => person.id === id)));
    renderCandidates();
    fillJobSelects();
  } catch (error) {
    toast(error.message, true);
  }
}

function renderCandidates() {
  const target = $("#applicantList");
  const empty = $("#applicantEmpty");
  if (!state.candidates.length) {
    target.innerHTML = "";
    empty.classList.remove("hidden");
    updateSelection();
    return;
  }
  empty.classList.add("hidden");
  const hasJob = Boolean($("#applicantJobFilter").value);
  target.innerHTML = state.candidates.map(candidate => {
    const skillPills = candidate.skills.slice(0, 4).map(skill => `<span class="skill-pill${candidate.unverified.includes(skill) ? " skill-unverified" : ""}">${escapeHtml(skill)}${candidate.unverified.includes(skill) ? " · check" : ""}</span>`).join("");
    const match = candidate.match?.score;
    return `<article class="applicant-card panel${hasJob ? " has-job" : ""}">
      <input class="candidate-check" type="checkbox" aria-label="Select ${escapeHtml(candidate.name)}" value="${candidate.id}" ${state.selected.has(candidate.id) ? "checked" : ""}>
      <div class="candidate-identity"><div class="avatar ${avatarClass(candidate.id)}">${escapeHtml(initials(candidate.name))}</div><div><strong>${escapeHtml(candidate.name)}</strong><small>${escapeHtml(candidate.email || candidate.education)}</small></div></div>
      <div class="applicant-skills">${skillPills || `<span class="skill-pill">Review skills</span>`}</div>
      ${hasJob ? `<div class="score-ring" style="--score:${match}%"><span>${match}%</span></div>` : `<span class="field-hint">Profile ready</span>`}
      <button class="button button-outline" data-profile="${candidate.id}" ${hasJob ? `data-job="${escapeHtml($("#applicantJobFilter").value)}"` : ""}>View profile <span>↗</span></button>
    </article>`;
  }).join("");
  updateSelection();
}

function updateSelection() {
  $("#selectionCount").textContent = `${state.selected.size} selected`;
  $("#compareSelected").disabled = state.selected.size < 2 || state.selected.size > 4;
  $$(".candidate-check").forEach(check => { check.checked = state.selected.has(Number(check.value)); });
}

function renderJobs() {
  const target = $("#jobsList");
  if (!state.jobs.length) {
    target.innerHTML = `<div class="panel loading-state">No roles yet. Add a job description to begin matching applicants.</div>`;
    return;
  }
  target.innerHTML = state.jobs.map((job, index) => `<article class="job-card panel">
    <div class="job-card-head"><span class="job-symbol">${["⌘", "▥", "✧", "◈"][index % 4]}</span><div><h3>${escapeHtml(job.title)}</h3><p>${escapeHtml(job.department || "Open position")} · ${job.required.length} essential skills</p></div></div>
    <p class="job-description">${escapeHtml(job.description || "No role overview provided.")}</p>
    <div class="skill-group required"><div class="skill-label">Essential skills</div>${job.required.map(skill => `<span class="skill-pill">${escapeHtml(skill)}</span>`).join("")}</div>
    <div class="skill-group"><div class="skill-label">Preferred skills</div>${job.preferred.length ? job.preferred.map(skill => `<span class="skill-pill">${escapeHtml(skill)}</span>`).join("") : `<span class="field-hint">No preferred skills set</span>`}</div>
    <div class="job-card-foot"><span>Created ${new Date(job.created_at).toLocaleDateString()}</span><button class="text-button" data-view="applicants" data-filter-job="${job.id}">Find matches →</button></div>
  </article>`).join("");
}

function updateReportLink() {
  const job = $("#reportJobSelect").value;
  $("#downloadReport").href = job ? `/api/reports.csv?job_id=${encodeURIComponent(job)}` : "/api/reports.csv";
  $("#downloadReport").setAttribute("aria-disabled", job ? "false" : "true");
}

async function openProfile(candidateId, jobId = "") {
  const modal = $("#profileModal");
  const content = $("#profileContent");
  modal.classList.remove("hidden");
  content.innerHTML = `<div class="loading-state">Loading applicant profile…</div>`;
  try {
    const candidate = await api(`/api/candidates/${candidateId}${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`);
    const match = candidate.match;
    const job = state.jobs.find(item => String(item.id) === String(jobId));
    const matched = match?.requirements?.filter(item => item.status === "matched") || [];
    const missing = match?.requirements?.filter(item => item.status === "missing") || [];
    content.innerHTML = `<header class="profile-header"><div class="profile-header-top"><div class="profile-title"><div class="avatar ${avatarClass(candidate.id)}">${escapeHtml(initials(candidate.name))}</div><div><h2 id="profileName">${escapeHtml(candidate.name)}</h2><p>${escapeHtml(candidate.email || "Email not provided")} · ${escapeHtml(candidate.education)}</p></div></div><button class="icon-button" data-action="close-profile" aria-label="Close dialog">×</button></div>
      ${match ? `<div class="profile-score-line"><strong>${match.score}%</strong><span>match for ${escapeHtml(job?.title || "selected role")}</span><span class="field-hint">${escapeHtml(match.explanation)}</span></div>` : ""}</header>
      <div class="profile-body">
        <section class="profile-section"><h3>${candidate.ai_summary ? "AI resume summary" : "Resume summary · local demo"}</h3><p>${escapeHtml(candidate.ai_summary || candidate.summary)}</p></section>
        <section class="profile-section"><h3>Education, experience & projects</h3><p><strong>Education:</strong> ${escapeHtml(candidate.education)}<br><strong>Experience:</strong> ${escapeHtml(candidate.experience)}<br><strong>Projects:</strong> ${escapeHtml(candidate.projects)}</p></section>
        <section class="profile-section"><h3>Skills & strengths</h3><p><strong>Technical:</strong> ${escapeHtml(candidate.technical_skills.filter(skill => !candidate.unverified.includes(skill)).join(" · ") || "Not identified")}</p><p style="margin-top:5px"><strong>Soft skills:</strong> ${escapeHtml(candidate.soft_skills.filter(skill => !candidate.unverified.includes(skill)).join(" · ") || "Not identified")}</p>${candidate.unverified.length ? `<p style="margin-top:5px"><strong>Unverified mentions:</strong> ${escapeHtml(candidate.unverified.join(" · "))}</p>` : ""}<p style="margin-top:5px"><strong>Strengths:</strong> ${escapeHtml(candidate.strengths)}</p></section>
        ${match ? `<section class="profile-section"><h3>Role requirements</h3><p style="margin-bottom:9px">Matched skills appear in the resume; missing skills were not found; unverified mentions use tentative wording. Verify all evidence with the applicant.</p><div class="requirement-list">${matched.map(item => `<span class="requirement-item matched">✓ ${escapeHtml(item.skill)} · ${escapeHtml(item.type)}</span>`).join("")}${candidate.unverified.filter(skill => job && [...job.required, ...job.preferred].includes(skill)).map(skill => `<span class="requirement-item unverified">? ${escapeHtml(skill)} · Unverified</span>`).join("")}${missing.filter(item => !candidate.unverified.includes(item.skill)).map(item => `<span class="requirement-item missing">+ ${escapeHtml(item.skill)} · ${escapeHtml(item.type)}</span>`).join("")}</div></section>` : ""}
        ${candidate.recommendations?.length ? `<section class="profile-section"><h3>Suggested roles</h3>${candidate.recommendations.map(item => `<div class="recommendation-row"><div>${escapeHtml(item.title)}<small>${escapeHtml(item.department || "Open position")} · ${item.matched.length} skills matched</small></div><strong>${item.score}%</strong></div>`).join("")}</section>` : ""}
        ${candidate.learning?.length ? `<section class="profile-section"><h3>Learning ideas for missing skills</h3>${candidate.learning.map(item => `<div class="learning-card"><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(item.skill)} · ${escapeHtml(item.course)} ↗</strong></a><p>${escapeHtml(item.project)}</p><small>Resource: ${escapeHtml(item.provider)}</small></div>`).join("")}</section>` : ""}
        ${candidate.improvements?.length ? `<section class="profile-section"><h3>Resume improvement suggestions</h3><div class="requirement-list">${candidate.improvements.map(tip => `<span class="requirement-item missing">${escapeHtml(tip)}</span>`).join("")}</div></section>` : ""}
        <div class="profile-actions">${jobId ? `<button class="button ${candidate.shortlisted ? "button-outline" : "button-primary"}" data-shortlist="${candidate.id}" data-job="${escapeHtml(jobId)}">${candidate.shortlisted ? "✓ Shortlisted" : "＋ Add to shortlist"}</button>` : ""}<button class="button button-outline" data-action="close-profile">Close</button></div>
      </div>`;
  } catch (error) {
    content.innerHTML = `<div class="loading-state">${escapeHtml(error.message)} <button class="button button-outline" data-action="close-profile">Close</button></div>`;
  }
}

async function createJob(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  const message = $("#jobMessage");
  message.textContent = "";
  try {
    await api("/api/jobs", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    $("#jobFormPanel").classList.add("hidden");
    await loadWorkspace();
    toast("Job description created.");
  } catch (error) {
    message.textContent = error.message;
  }
}

async function uploadApplicant(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = $("#uploadSubmit");
  const message = $("#uploadMessage");
  message.textContent = "";
  submit.disabled = true;
  submit.innerHTML = "Analyzing…";
  try {
    await api("/api/candidates", { method: "POST", body: new FormData(form) });
    form.reset();
    $("#uploadModal").classList.add("hidden");
    await loadWorkspace();
    toast("Resume analyzed and profile created.");
    setView("applicants");
  } catch (error) {
    message.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.innerHTML = "Analyze resume <span>✦</span>";
  }
}

async function compareSelected() {
  const ids = [...state.selected];
  const jobId = Number($("#compareJobSelect").value || $("#applicantJobFilter").value || state.jobs[0]?.id);
  if (ids.length < 2 || ids.length > 4 || !jobId) {
    toast("Select 2–4 applicants and a role to compare.", true);
    return;
  }
  $("#compareJobSelect").value = String(jobId);
  setView("compare");
  $("#compareCandidateSelect").selectedIndex = -1;
  $$("#compareCandidateSelect option").forEach(option => { option.selected = ids.includes(Number(option.value)); });
  await runComparison();
}

async function runComparison() {
  const ids = $$("#compareCandidateSelect option:checked").map(option => Number(option.value));
  const jobId = Number($("#compareJobSelect").value);
  try {
    const result = await api("/api/compare", { method: "POST", body: JSON.stringify({ job_id: jobId, candidate_ids: ids }) });
    $("#comparisonResult").innerHTML = `<div class="comparison-table-wrap panel"><div class="panel-heading"><div><p class="eyebrow">ROLE: ${escapeHtml(result.job.title)}</p><h2>Candidate comparison</h2></div></div><table class="comparison-table"><thead><tr><th>Applicant</th><th>Match</th><th>Essential coverage</th><th>Matched skills</th><th>Unverified</th><th>Missing</th><th>Decision support</th></tr></thead><tbody>${result.candidates.map((candidate, index) => `<tr><td><div class="candidate-identity"><div class="avatar ${avatarClass(candidate.id)}">${escapeHtml(initials(candidate.name))}</div><div><strong>${escapeHtml(candidate.name)}</strong><small>${escapeHtml(candidate.email || candidate.education)}</small></div></div></td><td><span class="comparison-score">${candidate.match.score}%</span></td><td>${candidate.match.required_matched.length}/${result.job.required.length} essential</td><td>${escapeHtml(candidate.match.matched.join(", ") || "—")}</td><td>${escapeHtml(candidate.match.required_unverified.join(", ") || "—")}</td><td>${escapeHtml(candidate.match.required_missing.join(", ") || "—")}</td><td>${index === 0 ? `<span class="requirement-item matched">Highest score</span>` : `<span class="field-hint">${escapeHtml(candidate.match.explanation)}</span>`}</td></tr>`).join("")}</tbody></table><p class="privacy-copy">Scores are based only on the entered skill requirements and extracted resume text. They are not a recommendation to hire; verify credentials and assess candidates consistently.</p></div>`;
  } catch (error) {
    toast(error.message, true);
  }
}

document.addEventListener("click", async event => {
  const viewButton = event.target.closest("[data-view]");
  if (viewButton) {
    if (viewButton.dataset.filterJob) {
      $("#applicantJobFilter").value = viewButton.dataset.filterJob;
      state.selected.clear();
    }
    setView(viewButton.dataset.view);
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "open-upload") $("#uploadModal").classList.remove("hidden");
  if (action === "close-upload") $("#uploadModal").classList.add("hidden");
  if (action === "show-job-form") $("#jobFormPanel").classList.remove("hidden");
  if (action === "hide-job-form") $("#jobFormPanel").classList.add("hidden");
  if (action === "close-profile") $("#profileModal").classList.add("hidden");
  if (event.target.closest(".strip-close")) event.target.closest(".privacy-strip").remove();
  const profile = event.target.closest("[data-profile]");
  if (profile) await openProfile(profile.dataset.profile, profile.dataset.job || "");
  const shortlist = event.target.closest("[data-shortlist]");
  if (shortlist) {
    try {
      const result = await api("/api/shortlist", { method: "POST", body: JSON.stringify({ candidate_id: Number(shortlist.dataset.shortlist), job_id: Number(shortlist.dataset.job) }) });
      toast(result.shortlisted ? "Applicant added to shortlist." : "Applicant removed from shortlist.");
      await openProfile(shortlist.dataset.shortlist, shortlist.dataset.job);
      await loadWorkspace();
    } catch (error) {
      toast(error.message, true);
    }
  }
});

document.addEventListener("change", event => {
  if (event.target.matches(".candidate-check")) {
    const id = Number(event.target.value);
    if (event.target.checked) state.selected.add(id); else state.selected.delete(id);
    updateSelection();
  }
  if (event.target.id === "applicantJobFilter") {
    state.selected.clear();
    loadCandidates();
  }
  if (event.target.id === "reportJobSelect") updateReportLink();
  if (event.target.id === "dropzone input") {
    const file = event.target.files[0];
    if (file) $("#dropzone strong").textContent = file.name;
  }
});

document.addEventListener("input", event => {
  if (event.target.id === "candidateSearch") {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(loadCandidates, 180);
  }
});

$("#jobForm").addEventListener("submit", createJob);
$("#uploadForm").addEventListener("submit", uploadApplicant);
$("#compareSelected").addEventListener("click", compareSelected);
$("#runCompare").addEventListener("click", runComparison);
$("#mobileMenu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#reportJobSelect").addEventListener("change", updateReportLink);
$("#uploadModal").addEventListener("click", event => { if (event.target.id === "uploadModal") event.currentTarget.classList.add("hidden"); });
$("#profileModal").addEventListener("click", event => { if (event.target.id === "profileModal") event.currentTarget.classList.add("hidden"); });
$("#dropzone").addEventListener("dragover", event => { event.preventDefault(); event.currentTarget.classList.add("drag-over"); });
$("#dropzone").addEventListener("dragleave", event => event.currentTarget.classList.remove("drag-over"));
$("#dropzone").addEventListener("drop", event => {
  event.preventDefault();
  event.currentTarget.classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (!file) return;
  const input = $('input[type="file"]', event.currentTarget);
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  $("strong", event.currentTarget).textContent = file.name;
});

loadWorkspace();
