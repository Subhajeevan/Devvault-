"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { sources: [], scopeId: null, scopeTitle: null };

/* Anonymous per-device vault id → your sources stay private to this browser. */
function vaultId() {
  let id = localStorage.getItem("devvault_sid");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
      "d-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("devvault_sid", id);
  }
  return id;
}

/* ------------------------------ helpers ------------------------------ */
async function api(path, opts = {}) {
  opts.headers = { "X-Vault-Id": vaultId(), ...(opts.headers || {}) };
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* no body */ }
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}

function toast(msg, kind = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast " + kind;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.hidden = true), 3800);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Small, safe-ish Markdown renderer (escapes first, then adds a few elements).
function md(src) {
  const blocks = esc(src).split(/\n{2,}/);
  const html = blocks.map((b) => {
    if (/^```/.test(b)) {
      return `<pre><code>${b.replace(/^```[a-zA-Z]*\n?/, "").replace(/```$/, "")}</code></pre>`;
    }
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) {
      return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*[-*]\s+/, ""))}</li>`).join("")}</ul>`;
    }
    if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) {
      return `<ol>${lines.map((l) => `<li>${inline(l.replace(/^\s*\d+\.\s+/, ""))}</li>`).join("")}</ol>`;
    }
    return `<p>${inline(b).replace(/\n/g, "<br>")}</p>`;
  });
  return html.join("");
}
function inline(s) {
  return s
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

/* ------------------------------ health ------------------------------ */
async function loadHealth() {
  try {
    const h = await api("/api/health");
    const s = $("#status");
    if (h.has_key) {
      s.className = "status ok";
      $("#status-text").textContent = `${h.provider} · ${h.model}`;
    } else {
      s.className = "status warn";
      const p = h.provider && h.provider !== "none" ? h.provider : "no LLM";
      $("#status-text").textContent = `${p} · no key · search only`;
    }
  } catch {
    $("#status").className = "status warn";
    $("#status-text").textContent = "offline";
  }
}

/* ------------------------------ sources ------------------------------ */
async function loadSources() {
  const { sources } = await api("/api/sources");
  state.sources = sources;
  $("#source-count").textContent = sources.length;
  $("#empty").hidden = sources.length > 0;

  const wrap = $("#sources");
  wrap.innerHTML = "";
  for (const s of sources) {
    const el = document.createElement("div");
    el.className = "source" + (s.id === state.scopeId ? " selected" : "");
    el.innerHTML = `
      <div class="source-top">
        <span class="badge ${s.source_type}">${s.source_type}</span>
        <span class="source-title" title="${esc(s.title)}">${esc(s.title)}</span>
        ${s.owned ? `<button class="source-del" title="Delete">&times;</button>`
                  : `<span class="source-sample" title="Shared sample">sample</span>`}
      </div>
      ${s.tags && s.tags.length
        ? `<div class="tags">${s.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div>`
        : ""}`;
    el.querySelector(".source-title").onclick = () => openDetail(s.id);
    el.querySelector(".badge").onclick = () => openDetail(s.id);
    const del = el.querySelector(".source-del");
    if (del) del.onclick = (e) => { e.stopPropagation(); delSource(s.id); };
    wrap.appendChild(el);
  }
}

async function delSource(id) {
  if (!confirm("Remove this source from your vault?")) return;
  try {
    await api(`/api/sources/${id}`, { method: "DELETE" });
    if (state.scopeId === id) clearScope();
    if ($("#detail").dataset.id === id) $("#detail").hidden = true;
    toast("Source removed", "ok");
    loadSources();
  } catch (e) { toast(e.message, "err"); }
}

/* ------------------------------ scope ------------------------------ */
function setScope(id, title) {
  state.scopeId = id;
  state.scopeTitle = title;
  $("#scope-value").textContent = title;
  $("#scope-clear").hidden = false;
  loadSources();
}
function clearScope() {
  state.scopeId = null;
  $("#scope-value").textContent = "all sources";
  $("#scope-clear").hidden = true;
  loadSources();
}
$("#scope-clear").onclick = clearScope;

/* ------------------------------ detail + flashcards ------------------------------ */
async function openDetail(id) {
  const s = await api(`/api/sources/${id}`);
  setScope(id, s.title);
  const d = $("#detail");
  d.dataset.id = id;
  d.hidden = false;
  d.innerHTML = `
    <div class="detail-head">
      <div>
        <span class="badge ${s.source_type}">${s.source_type}</span>
        <h3>${esc(s.title)}</h3>
        ${s.url ? `<a class="cite-src" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>` : ""}
      </div>
      <div class="detail-actions">
        <button class="btn primary" id="quiz-btn">🧠 Quiz me</button>
        <button class="btn" id="fc-btn">Flashcards</button>
      </div>
    </div>
    <div class="prose">${s.summary ? md(s.summary) : "<p class='hint'>No summary yet.</p>"}</div>
    <div id="quiz" class="quiz"></div>
    <div id="cards" class="cards-grid"></div>`;
  d.querySelector("#fc-btn").onclick = () => genFlashcards(id);
  d.querySelector("#quiz-btn").onclick = () => genQuiz(id);
  d.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function genFlashcards(id) {
  const btn = $("#fc-btn");
  const grid = $("#cards");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Generating…`;
  try {
    const { flashcards } = await api(`/api/sources/${id}/flashcards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count: 8 }),
    });
    grid.innerHTML = "";
    flashcards.forEach((c) => {
      const card = document.createElement("div");
      card.className = "flashcard";
      card.innerHTML = `
        <div class="fc-label">Q · tap to flip</div>
        <div class="fc-q">${esc(c.question)}</div>
        <div class="fc-a">${esc(c.answer)}</div>`;
      card.onclick = () => card.classList.toggle("flipped");
      grid.appendChild(card);
    });
    toast(`Generated ${flashcards.length} flashcards`, "ok");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = "Flashcards";
  }
}

/* ------------------------------ quiz ------------------------------ */
async function genQuiz(id) {
  const btn = $("#quiz-btn");
  const box = $("#quiz");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Building quiz…`;
  box.innerHTML = "";
  try {
    const { questions } = await api(`/api/sources/${id}/quiz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count: 5 }),
    });
    if (!questions.length) return toast("Couldn't build a quiz from this source", "err");
    renderQuiz(box, questions);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "🧠 Quiz me";
  }
}

function renderQuiz(box, questions) {
  const total = questions.length;
  let answered = 0, correct = 0;
  box.innerHTML = `<div class="quiz-head"><span>Quiz</span><span class="quiz-score" id="quiz-score">0 / ${total}</span></div>`;
  questions.forEach((q, qi) => {
    const card = document.createElement("div");
    card.className = "quiz-q";
    card.innerHTML = `<div class="quiz-qtext">${qi + 1}. ${esc(q.question)}</div>`;
    const opts = document.createElement("div");
    opts.className = "quiz-opts";
    q.options.forEach((opt, oi) => {
      const b = document.createElement("button");
      b.className = "quiz-opt";
      b.textContent = opt;
      b.onclick = () => {
        if (card.dataset.done) return;
        card.dataset.done = "1";
        answered++;
        const isCorrect = oi === q.correct_index;
        if (isCorrect) correct++;
        [...opts.children].forEach((c, ci) => {
          c.disabled = true;
          if (ci === q.correct_index) c.classList.add("correct");
          else if (ci === oi) c.classList.add("wrong");
        });
        const exp = document.createElement("div");
        exp.className = "quiz-exp " + (isCorrect ? "ok" : "no");
        exp.innerHTML = `<strong>${isCorrect ? "✓ Correct" : "✗ Not quite"}</strong> — ${esc(q.explanation)}`;
        card.appendChild(exp);
        $("#quiz-score").textContent = `${correct} / ${total}`;
        if (answered === total) {
          const pct = Math.round((100 * correct) / total);
          const verdict = pct >= 80 ? "🏆 Nailed it!" : pct >= 50 ? "👍 Not bad" : "📚 Keep studying";
          const done = document.createElement("div");
          done.className = "quiz-done";
          done.innerHTML = `${verdict} &nbsp; You scored <strong>${correct}/${total}</strong> (${pct}%).`;
          box.appendChild(done);
          done.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      };
      opts.appendChild(b);
    });
    card.appendChild(opts);
    box.appendChild(card);
  });
}

/* ------------------------------ ask ------------------------------ */
async function ask() {
  const q = $("#question").value.trim();
  if (!q) return;
  const box = $("#answer");
  box.hidden = false;
  box.innerHTML = `<div class="loading"><span class="spinner"></span> Searching your vault…</div>`;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const body = { question: q };
    if (state.scopeId) body.source_ids = [state.scopeId];
    const r = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    renderAnswer(r);
  } catch (e) {
    box.innerHTML = `<p class="hint">⚠ ${esc(e.message)}</p>`;
  }
}

function renderAnswer(r) {
  let html = `<div class="prose">${md(r.answer || "")}</div>`;
  if (r.citations && r.citations.length) {
    html += `<div class="cite-head">Citations</div>`;
    for (const c of r.citations) {
      const src = c.url
        ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.title)}</a>`
        : esc(c.title);
      html += `
        <div class="citation">
          <div><span class="cite-num">[${c.number}]</span><span class="cite-src">${src}</span></div>
          ${c.cited_text ? `<div class="cite-text">“${esc(c.cited_text)}”</div>` : ""}
        </div>`;
    }
  }
  $("#answer").innerHTML = html;
}

/* ------------------------------ add forms ------------------------------ */
function wireTabs() {
  document.querySelectorAll(".tab").forEach((t) => {
    t.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".add-form").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      $(`[data-form="${t.dataset.tab}"]`).classList.add("active");
    };
  });
}

async function submitForm(btn, fn) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Ingesting…`;
  try {
    const src = await fn();
    toast(`Added “${src.title}”`, "ok");
    await loadSources();
    await loadHealth();
    openDetail(src.id);
  } catch (e) {
    toast(e.message, "err");
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function wireForms() {
  // PDF
  const fileInput = $("#pdf-file");
  const drop = $("#filedrop");
  fileInput.onchange = () => {
    $("#filedrop-label").textContent = fileInput.files[0] ? fileInput.files[0].name : "Drop a PDF here or click to browse";
  };
  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => {
    if (e.dataTransfer.files[0]) { fileInput.files = e.dataTransfer.files; fileInput.onchange(); }
  });
  $("#form-pdf").onsubmit = (e) => {
    e.preventDefault();
    if (!fileInput.files[0]) return toast("Choose a PDF first", "err");
    submitForm(e.submitter, async () => {
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      const src = await api("/api/ingest/pdf", { method: "POST", body: fd });
      $("#form-pdf").reset();
      $("#filedrop-label").textContent = "Drop a PDF here or click to browse";
      return src;
    });
  };

  const urlForm = (formId, inputId, endpoint) => {
    $(formId).onsubmit = (e) => {
      e.preventDefault();
      const url = $(inputId).value.trim();
      if (!url) return;
      submitForm(e.submitter, async () => {
        const src = await api(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
        $(formId).reset();
        return src;
      });
    };
  };
  urlForm("#form-web", "#web-url", "/api/ingest/web");

  $("#form-note").onsubmit = (e) => {
    e.preventDefault();
    const title = $("#note-title").value.trim();
    const text = $("#note-text").value.trim();
    if (!title || !text) return toast("Note needs a title and text", "err");
    submitForm(e.submitter, async () => {
      const src = await api("/api/ingest/note", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, text }),
      });
      $("#form-note").reset();
      return src;
    });
  };
}

/* ------------------------------ boot ------------------------------ */
$("#ask-btn").onclick = ask;
$("#question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
});
wireTabs();
wireForms();
loadHealth();
loadSources();
