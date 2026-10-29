"use strict";

const FIELDS = [
  "emotional_tone", "emotional_intensity", "background_noise_present", "background_noise_type",
  "background_noise_severity", "audio_quality", "speaker_overlap_present", "long_silence_present", "confidence",
];
const PREDICTION_FIELDS = [
  ["emotional_tone", "Tone"],
  ["emotional_intensity", "Intensity"],
  ["background_noise_present", "Background noise"],
  ["background_noise_type", "Noise type"],
  ["audio_quality", "Audio quality"],
  ["speaker_overlap_present", "Speaker overlap"],
];
const CONFIDENCE_BINS = [
  { label: "0–39%", min: 0, max: 0.4 },
  { label: "40–59%", min: 0.4, max: 0.6 },
  { label: "60–79%", min: 0.6, max: 0.8 },
  { label: "80–100%", min: 0.8, max: 1.01 },
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

function costInputs() {
  const hourlyPrice = Number($("hourly-price").value);
  const utilization = Number($("utilization").value);
  if (!Number.isFinite(hourlyPrice) || hourlyPrice <= 0 || hourlyPrice > 10000 ||
      !Number.isFinite(utilization) || utilization <= 0 || utilization > 1) return null;
  return { hourlyPrice, utilization };
}

function itemCost(item, inputs) {
  if (!inputs || item.status !== "done" || !Number.isFinite(item.processing_s) ||
      !Number.isFinite(item.duration_s) || item.processing_s < 0 || item.duration_s <= 0) return null;
  return {
    amount: inputs.hourlyPrice * item.processing_s / (3600 * inputs.utilization),
    audioMinutes: item.duration_s / 60,
  };
}

function money(value) {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "$0.00";
  if (value >= 0.01) return `$${value.toFixed(2)}`;
  if (value < 0.000001) return "$<0.000001";
  return `$${value.toFixed(6)}`;
}

function renderMetrics(job) {
  const inputs = costInputs();
  const measured = job.items.map((item) => ({ item, cost: itemCost(item, inputs) }))
    .filter((entry) => entry.cost);
  const timed = job.items.filter((item) => item.status === "done" && Number.isFinite(item.processing_s) &&
    Number.isFinite(item.duration_s) && item.processing_s >= 0 && item.duration_s > 0);
  const totalCost = measured.reduce((sum, entry) => sum + entry.cost.amount, 0);
  const audioMinutes = measured.reduce((sum, entry) => sum + entry.cost.audioMinutes, 0);
  const timedAudioMinutes = timed.reduce((sum, item) => sum + item.duration_s / 60, 0);
  const summary = job.summary || {};
  $("metric-completed").textContent = `${summary.done || 0}/${summary.total || 0}`;
  $("metric-completion-note").textContent = `${summary.failed || 0} failed`;
  $("metric-audio").textContent = timedAudioMinutes ? timedAudioMinutes.toFixed(2) : "—";
  $("metric-processing").textContent = timed.length
    ? timed.reduce((sum, item) => sum + item.processing_s, 0).toFixed(2)
    : "—";
  $("metric-cost").textContent = inputs ? money(totalCost) : "—";
  $("metric-cost-minute").textContent = inputs && audioMinutes ? money(totalCost / audioMinutes) : "—";
  $("metric-cost-note").textContent = inputs
    ? `${measured.length} file(s) with measured processing`
    : "Correct assumptions to calculate";
  $("cost-input-error").hidden = inputs !== null;
  $("score-note").textContent = job.score
    ? "Labels are only used for comparison, never as model input. Small batches are not a reliable accuracy estimate."
    : "No scored labels are available for this batch.";
}

function renderPredictionCharts(job) {
  const container = $("prediction-charts");
  container.replaceChildren();
  const completed = job.items.filter((item) => item.status === "done" && item.prediction);
  if (!completed.length) {
    container.append(el("p", "Predictions will appear when files finish processing.", "muted small"));
    return;
  }
  for (const [field, title] of PREDICTION_FIELDS) {
    const counts = new Map();
    for (const item of completed) {
      const value = item.prediction[field];
      if (value !== undefined && value !== null && value !== "") {
        const label = String(fmt(value));
        counts.set(label, (counts.get(label) || 0) + 1);
      }
    }
    if (!counts.size) continue;
    const group = el("div", null, "bar-group");
    group.append(el("h4", title));
    const max = Math.max(...counts.values());
    for (const [label, count] of [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))) {
      const row = el("div", null, "bar-row");
      const text = el("span", label, "bar-label");
      const track = el("span", null, "bar-track");
      const bar = el("span", null, "bar-fill");
      bar.style.width = `${100 * count / max}%`;
      track.append(bar);
      row.append(text, track, el("strong", count, "bar-count"));
      group.append(row);
    }
    container.append(group);
  }
}

function renderConfidenceChart(job) {
  const container = $("confidence-chart");
  container.replaceChildren();
  const values = job.items
    .filter((item) => item.status === "done" && item.prediction)
    .map((item) => Number(item.prediction.confidence))
    .filter((value) => Number.isFinite(value) && value >= 0 && value <= 1);
  if (!values.length) {
    container.append(el("p", "No confidence scores available yet.", "muted small"));
    return;
  }
  const counts = CONFIDENCE_BINS.map((bin) => values.filter((value) => value >= bin.min && value < bin.max).length);
  const max = Math.max(1, ...counts);
  for (let i = 0; i < CONFIDENCE_BINS.length; i += 1) {
    const column = el("div", null, "confidence-column");
    const count = el("strong", counts[i]);
    const track = el("span", null, "confidence-track");
    const bar = el("span", null, "confidence-fill");
    bar.style.height = `${100 * counts[i] / max}%`;
    track.append(bar);
    column.append(count, track, el("span", CONFIDENCE_BINS[i].label, "small"));
    container.append(column);
  }
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  container.append(el("p", `Average: ${(100 * average).toFixed(1)}% across ${values.length} file(s)`, "muted small confidence-average"));
}

function renderItems(job) {
  const tbody = document.querySelector("#results tbody");
  tbody.replaceChildren();
  const filter = $("filter").value;
  const inputs = costInputs();
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
    tr.append(el("td", Number.isFinite(item.duration_s) ? `${item.duration_s.toFixed(2)} s` : "—"));
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
    const cost = itemCost(item, inputs);
    tr.append(el("td", cost ? money(cost.amount) : "—"));
    tbody.append(tr);
  }
}

function renderScore(score) {
  const box = $("score");
  box.replaceChildren();
  if (!score) return;
  box.append(el("p", `${score.n_scored} file(s) scored against supplied labels.`, "muted small"));
  const table = el("table", null, "score-table");
  const head = el("tr");
  ["Field", "Accuracy", "Macro F1"].forEach((h) => head.append(el("th", h)));
  table.append(head);
  for (const [field, m] of Object.entries(score.fields)) {
    const tr = el("tr");
    tr.append(el("td", field));
    const acc = m.accuracy ?? m.normalized_match;
    const accuracy = el("td");
    if (acc === undefined || acc === null) {
      accuracy.textContent = "-";
    } else {
      accuracy.append(el("strong", `${(100 * acc).toFixed(1)}%`));
      const track = el("span", null, "agreement-track");
      const bar = el("span", null, "agreement-fill");
      bar.style.width = `${Math.max(0, Math.min(100, 100 * acc))}%`;
      track.append(bar);
      accuracy.append(track);
    }
    tr.append(accuracy);
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
  if (job.method) {
    $("method").textContent = `method: ${job.method}`;
    $("method-pill").textContent = job.method;
  }
  const msgs = $("job-messages");
  msgs.replaceChildren();
  for (const e of job.errors || []) msgs.append(el("div", e, "error"));
  for (const w of job.warnings || []) msgs.append(el("div", w, "warn"));
  if ((job.skipped || []).length) msgs.append(el("div", `Skipped: ${job.skipped.join(", ")}`, "muted small"));
  for (const [id, kind] of [["dl-csv", "predictions.csv"], ["dl-json", "results.json"], ["dl-err", "errors.csv"]]) {
    $(id).href = `/api/jobs/${encodeURIComponent(job.id)}/download/${kind}`;
  }
  $("resume").hidden = job.status !== "interrupted";
  renderMetrics(job);
  renderPredictionCharts(job);
  renderConfidenceChart(job);
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
  if (me.method) $("method-pill").textContent = me.method;
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
  for (const control of [$("hourly-price"), $("utilization")]) {
    control.addEventListener("input", () => {
      if (currentJob) {
        renderMetrics(currentJob);
        renderItems(currentJob);
      }
    });
  }
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const candidate of document.querySelectorAll(".tab")) {
        const selected = candidate === tab;
        candidate.classList.toggle("active", selected);
        candidate.setAttribute("aria-selected", String(selected));
      }
      $("overview-panel").hidden = tab.dataset.tab !== "overview";
      $("table-panel").hidden = tab.dataset.tab !== "table";
    });
  }
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
