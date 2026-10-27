"use strict";

const FIELDS = [
  "emotional_tone", "emotional_intensity", "background_noise_present", "background_noise_type",
  "background_noise_severity", "audio_quality", "speaker_overlap_present", "long_silence_present", "confidence",
];
const $ = (id) => document.getElementById(id);
let csrf = "";
let selection = [];
let currentJob = null;
let pollTimer = null;

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}

async function api(path, options = {}) {
  const headers = Object.assign({ "X-CSRF-Token": csrf }, options.headers || {});
  const res = await fetch(path, Object.assign({}, options, { headers }));
  if (res.status === 401) { window.location.href = "/login"; throw new Error("login required"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `request failed (${res.status})`);
  return body;
}

function setSelection(files, useRelative) {
  selection = Array.from(files).map((f) => ({ file: f, path: (useRelative && f.webkitRelativePath) || f.name }));
  const audio = selection.filter((s) => !/\.(csv|zip)$/i.test(s.path)).length;
  const zips = selection.filter((s) => /\.zip$/i.test(s.path)).length;
  const csvs = selection.filter((s) => /\.csv$/i.test(s.path)).length;
  $("selection").textContent = selection.length
    ? `${selection.length} file(s): ${zips} ZIP, ${csvs} CSV, ${audio} other`
    : "Nothing selected";
  $("start").disabled = selection.length === 0;
}

function upload() {
  $("upload-error").textContent = "";
  const form = new FormData();
  for (const s of selection) {
    form.append("files", s.file, s.file.name);
    form.append("paths", s.path);
  }
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/jobs");
  xhr.setRequestHeader("X-CSRF-Token", csrf);
  const bar = $("upload-progress");
  bar.hidden = false;
  bar.value = 0;
  $("start").disabled = true;
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) bar.value = (100 * e.loaded) / e.total; };
  xhr.onload = () => {
    bar.hidden = true;
    let body = {};
    try { body = JSON.parse(xhr.responseText); } catch (_) { /* non-JSON error */ }
    if (xhr.status === 401) { window.location.href = "/login"; return; }
    if (xhr.status >= 400) {
      $("upload-error").textContent = body.detail || `Upload failed (${xhr.status})`;
      $("start").disabled = false;
      return;
    }
    setSelection([], false);
    showJob(body);
    loadJobs();
  };
  xhr.onerror = () => {
    bar.hidden = true;
    $("start").disabled = false;
    $("upload-error").textContent = "Network error during upload";
  };
  xhr.send(form);
}

function fmt(value) {
  if (value === true) return "yes";
  if (value === false) return "no";
  if (value === "" ) return "-";
  return value;
}

function mismatch(item) {
  if (!item.label || !item.prediction) return false;
  return FIELDS.some((f) => f !== "confidence" && f in item.label && item.label[f] !== item.prediction[f]);
}

function renderItems(job) {
  const tbody = document.querySelector("#results tbody");
  tbody.replaceChildren();
  const filter = $("filter").value;
  for (const item of job.items) {
    if (filter === "failed" && item.status !== "failed") continue;
    if (filter === "done" && item.status !== "done") continue;
    if (filter === "mismatch" && !mismatch(item)) continue;
    if (filter === "warn" && !(item.warnings || []).length) continue;
    const tr = el("tr");
    const name = el("td");
    name.append(el("div", item.name, "filename"));
    for (const w of item.warnings || []) name.append(el("div", w, "warn small"));
    tr.append(name);
    const status = el("td");
    status.append(el("span", item.status, `badge ${item.status}`));
    if (item.error) status.append(el("div", item.error, "error small"));
    tr.append(status);
    for (const f of FIELDS) {
      const td = el("td");
      if (item.prediction) {
        td.append(el("div", fmt(item.prediction[f])));
        if (item.label && f in item.label && f !== "confidence" && item.label[f] !== item.prediction[f]) {
          td.classList.add("mismatch");
          td.append(el("div", `expected: ${fmt(item.label[f])}`, "small"));
        }
      }
      tr.append(td);
    }
    tbody.append(tr);
  }
}

function renderScore(score) {
  const box = $("score");
  box.replaceChildren();
  if (!score) return;
  box.append(el("h3", `Agreement with supplied labels (${score.n_scored} files)`));
  box.append(el("p", "Labels are only used for this comparison, never as model input. Small batches are not a reliable accuracy estimate.", "muted small"));
  const table = el("table", null, "score-table");
  const head = el("tr");
  ["Field", "Accuracy", "Macro F1"].forEach((h) => head.append(el("th", h)));
  table.append(head);
  for (const [field, m] of Object.entries(score.fields)) {
    const tr = el("tr");
    tr.append(el("td", field));
    const acc = m.accuracy ?? m.normalized_match;
    tr.append(el("td", acc === undefined || acc === null ? "-" : `${(100 * acc).toFixed(1)}%`));
    tr.append(el("td", m.macro_f1 === undefined || m.macro_f1 === null ? "-" : m.macro_f1.toFixed(3)));
    table.append(tr);
  }
  box.append(table);
}

function showJob(job) {
  currentJob = job;
  $("job-card").hidden = false;
  $("job-id").textContent = job.id;
  const status = $("job-status");
  status.textContent = job.status.replaceAll("_", " ");
  status.className = `badge ${job.status}`;
  const s = job.summary || {};
  const finished = (s.done || 0) + (s.failed || 0);
  $("job-progress").value = s.total ? (100 * finished) / s.total : 0;
  const parts = [`${finished}/${s.total || 0} processed`, `${s.done || 0} completed`, `${s.failed || 0} failed`];
  if (s.audio_minutes) parts.push(`${s.audio_minutes.toFixed(2)} audio min`);
  if (s.real_time_factor) parts.push(`real-time factor ${s.real_time_factor}`);
  if (job.manifest) parts.push(`manifest: ${job.manifest}`);
  $("job-summary").textContent = parts.join(" | ");
  const msgs = $("job-messages");
  msgs.replaceChildren();
  for (const e of job.errors || []) msgs.append(el("div", e, "error"));
  for (const w of job.warnings || []) msgs.append(el("div", w, "warn"));
  if ((job.skipped || []).length) msgs.append(el("div", `Skipped: ${job.skipped.join(", ")}`, "muted small"));
  for (const [id, kind] of [["dl-csv", "predictions.csv"], ["dl-json", "results.json"], ["dl-err", "errors.csv"]]) {
    $(id).href = `/api/jobs/${encodeURIComponent(job.id)}/download/${kind}`;
  }
  $("resume").hidden = job.status !== "interrupted";
  renderScore(job.score);
  renderItems(job);
  clearTimeout(pollTimer);
  if (job.status === "running" || job.status === "validating") {
    pollTimer = setTimeout(() => openJob(job.id), 1500);
  }
}

async function openJob(id) {
  try {
    showJob(await api(`/api/jobs/${encodeURIComponent(id)}`));
  } catch (err) {
    $("job-messages").replaceChildren(el("div", err.message, "error"));
  }
}

async function loadJobs() {
  const list = $("job-list");
  const jobs = await api("/api/jobs");
  list.replaceChildren();
  if (!jobs.length) list.append(el("li", "No batches yet", "muted"));
  for (const j of jobs) {
    const li = el("li");
    const btn = el("button", `${j.created} - ${j.status.replaceAll("_", " ")} - ${j.summary ? j.summary.total : 0} files`, "link");
    btn.addEventListener("click", () => openJob(j.id));
    li.append(btn);
    list.append(li);
  }
}

async function init() {
  const me = await api("/api/me");
  csrf = me.csrf;
  $("user").textContent = me.user;
  $("method").textContent = me.method ? `method: ${me.method}` : "";
  $("folder-input").addEventListener("change", (e) => setSelection(e.target.files, true));
  $("files-input").addEventListener("change", (e) => setSelection(e.target.files, false));
  const drop = $("drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    setSelection(e.dataTransfer.files, false);
  });
  $("start").addEventListener("click", upload);
  $("filter").addEventListener("change", () => currentJob && renderItems(currentJob));
  $("resume").addEventListener("click", async () => {
    showJob(await api(`/api/jobs/${encodeURIComponent(currentJob.id)}/resume`, { method: "POST" }));
  });
  $("logout").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" }).catch(() => {});
    window.location.href = "/login";
  });
  await loadJobs();
}

init().catch((err) => { $("upload-error").textContent = err.message; });
