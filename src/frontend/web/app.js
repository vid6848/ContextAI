/* ============================================================================
   ContextAI — Frontend Application Logic
   Talks to the existing FastAPI backend over the same REST API.
   ============================================================================ */
"use strict";

/* ---------------------------------------------------------------- config */
const BACKEND_URL = (window.CONTEXTAI_BACKEND_URL || "").replace(/\/$/, "");
const API = `${BACKEND_URL}/api/v1`;
const USER_ID = "default_user";
const STORAGE_KEY = "contextai_conversations_v1";
const THEME_STORAGE_KEY = "contextai_accent_theme";
const SIDEBAR_STORAGE_KEY = "contextai_sidebar_collapsed";

/* ---------------------------------------------------------------- state */
let conversations = {}; // id -> { id, title, createdAt, messages: [{role, content, details}] }
let currentId = null;
let sending = false;

/* ---------------------------------------------------------------- dom */
const $ = (sel) => document.querySelector(sel);
const appShell = $("#app-shell") || $(".app-shell");
const sidebar = $("#sidebar");
const scrim = $("#scrim");
const convList = $("#conversation-list");
const searchInput = $("#search-input");
const chatScroll = $("#chat-scroll");
const messagesEl = $("#messages");
const heroEl = $("#hero");
const topbarTitle = $("#topbar-title");
const composerInput = $("#composer-input");
const sendBtn = $("#composer-send");
const dueBanner = $("#due-banner");
const toastEl = $("#toast");

const isMobile = () => window.matchMedia("(max-width: 860px)").matches;

/* ---------------------------------------------------------------- utils */
function uid() {
  return "chat_" + Math.random().toString(16).slice(2, 10);
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
  if (window.marked && window.DOMPurify) {
    marked.setOptions({ breaks: true, gfm: true });
    return DOMPurify.sanitize(marked.parse(text || ""));
  }
  return `<p>${escapeHtml(text || "")}</p>`;
}

let toastTimer = null;
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.hidden = true), 2600);
}

/* ------------------------------------------------------------ theme / accent */
function applyAccentTheme(theme) {
  const validThemes = ["blue", "purple", "cyan", "green", "pink"];
  const selected = validThemes.includes(theme) ? theme : "blue";
  document.documentElement.setAttribute("data-accent", selected);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, selected);
  } catch (_) {}

  // Update active button state
  document.querySelectorAll(".theme-option").forEach((opt) => {
    opt.classList.toggle("active", opt.dataset.theme === selected);
  });
}

function loadAccentTheme() {
  let saved = "blue";
  try {
    saved = localStorage.getItem(THEME_STORAGE_KEY) || "blue";
  } catch (_) {}
  applyAccentTheme(saved);
}

document.querySelectorAll(".theme-option").forEach((btn) => {
  btn.addEventListener("click", () => {
    applyAccentTheme(btn.dataset.theme);
    toast(`Theme accent: ${btn.dataset.theme}`);
  });
});

/* ------------------------------------------------------------ persistence */
function saveConversations() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ conversations, currentId }));
  } catch (_) { /* storage full/blocked — non-fatal */ }
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data && data.conversations && Object.keys(data.conversations).length) {
      conversations = data.conversations;
      currentId = data.currentId;
    }
  } catch (_) { /* corrupted storage — start fresh */ }
}

function createConversation() {
  const id = uid();
  conversations[id] = { id, title: "New conversation", createdAt: Date.now(), messages: [] };
  currentId = id;
  saveConversations();
  return id;
}

function currentChat() {
  return conversations[currentId];
}

/* ---------------------------------------------------------------- sidebar */
function openSidebar() {
  sidebar.classList.remove("collapsed");
  if (appShell) appShell.classList.remove("sidebar-collapsed");
  if (isMobile()) {
    scrim.hidden = false;
  } else {
    try { localStorage.setItem(SIDEBAR_STORAGE_KEY, "false"); } catch (_) {}
  }
}

function closeSidebar() {
  sidebar.classList.add("collapsed");
  if (appShell) appShell.classList.add("sidebar-collapsed");
  scrim.hidden = true;
  if (!isMobile()) {
    try { localStorage.setItem(SIDEBAR_STORAGE_KEY, "true"); } catch (_) {}
  }
}

function toggleSidebar() {
  if (sidebar.classList.contains("collapsed")) {
    openSidebar();
  } else {
    closeSidebar();
  }
}

$("#sidebar-open").addEventListener("click", openSidebar);
$("#sidebar-close").addEventListener("click", closeSidebar);
scrim.addEventListener("click", closeSidebar);

// Keyboard shortcut (Cmd/Ctrl + B) for sidebar toggle
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
    e.preventDefault();
    toggleSidebar();
  }
});

function renderConversationList() {
  const q = searchInput.value.trim().toLowerCase();
  const items = Object.values(conversations)
    .sort((a, b) => b.createdAt - a.createdAt)
    .filter((c) => !q || c.title.toLowerCase().includes(q));

  convList.innerHTML = "";
  if (!items.length) {
    convList.innerHTML = `<div class="conv-empty">${q ? "No conversations match your search." : "No conversations yet."}</div>`;
    return;
  }

  for (const c of items) {
    const row = document.createElement("div");
    row.className = "conv-row" + (c.id === currentId ? " active" : "");

    const titleBtn = document.createElement("button");
    titleBtn.className = "conv-title-btn";
    titleBtn.textContent = c.title;
    titleBtn.title = c.title;
    titleBtn.addEventListener("click", () => {
      currentId = c.id;
      saveConversations();
      renderAll();
      if (isMobile()) closeSidebar();
    });

    const menuBtn = document.createElement("button");
    menuBtn.className = "conv-menu-btn";
    menuBtn.textContent = "⋮";
    menuBtn.setAttribute("aria-label", "Conversation actions");

    const menu = document.createElement("div");
    menu.className = "conv-menu";
    menu.hidden = true;

    const renameInput = document.createElement("input");
    renameInput.type = "text";
    renameInput.value = c.title;
    renameInput.placeholder = "Rename conversation";

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save name";
    saveBtn.addEventListener("click", () => {
      const v = renameInput.value.trim();
      if (v) {
        c.title = v;
        saveConversations();
        renderAll();
      }
    });

    const delBtn = document.createElement("button");
    delBtn.textContent = "Delete";
    delBtn.className = "danger";
    delBtn.addEventListener("click", () => {
      delete conversations[c.id];
      if (!Object.keys(conversations).length) createConversation();
      else if (currentId === c.id) {
        currentId = Object.values(conversations).sort((a, b) => b.createdAt - a.createdAt)[0].id;
      }
      saveConversations();
      renderAll();
    });

    menu.append(renameInput, saveBtn, delBtn);

    menuBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      document.querySelectorAll(".conv-menu").forEach((m) => { if (m !== menu) m.hidden = true; });
      menu.hidden = !menu.hidden;
    });

    row.append(titleBtn, menuBtn, menu);
    convList.appendChild(row);
  }
}

document.addEventListener("click", () => {
  document.querySelectorAll(".conv-menu").forEach((m) => (m.hidden = true));
});

$("#btn-new-chat").addEventListener("click", () => {
  createConversation();
  renderAll();
  composerInput.focus();
  if (isMobile()) closeSidebar();
});

searchInput.addEventListener("input", renderConversationList);

/* ------------------------------------------------------------ live tool items */
document.querySelectorAll(".tool-item[data-tool]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tool = btn.dataset.tool;
    let template = "";
    if (tool === "search") template = "Search the web for ";
    else if (tool === "weather") template = "What is the weather in ";
    else if (tool === "crypto") template = "What is the price of Bitcoin?";
    else if (tool === "calc") template = "Calculate ";

    composerInput.value = template;
    autogrow();
    composerInput.focus();
    composerInput.setSelectionRange(template.length, template.length);
    sendBtn.disabled = composerInput.value.trim() === "";
    if (isMobile()) closeSidebar();
  });
});

/* ---------------------------------------------------------------- messages */
function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function buildAgentDetails(details) {
  if (!details || (!details.intent && !details.tool_used)) return null;
  const wrap = document.createElement("div");
  wrap.className = "agent-details";

  const toggle = document.createElement("button");
  toggle.className = "agent-details-toggle";
  toggle.innerHTML = `<svg class="chevron" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m9 6 6 6-6 6"/></svg> Agent details`;
  toggle.addEventListener("click", () => wrap.classList.toggle("open"));

  const body = document.createElement("div");
  body.className = "agent-details-body";
  const conf = typeof details.confidence === "number" ? details.confidence.toFixed(2) : "0.00";
  let html = `
    <span class="tag">Intent: <b>${escapeHtml(details.intent || "GENERAL")}</b></span>
    <span class="tag">Confidence: <b>${conf}</b></span>
    <span class="tag">Tool: <b>${escapeHtml(details.tool_used || "None")}</b></span>`;
  if (Array.isArray(details.sources) && details.sources.length) {
    html += `<div class="source-list"><b>Document sources:</b><ul>`;
    for (const s of details.sources) {
      html += `<li><code>${escapeHtml(s.document || "Document")}</code> — Page ${escapeHtml(String(s.page ?? 1))}</li>`;
    }
    html += `</ul></div>`;
  }
  body.innerHTML = html;

  wrap.append(toggle, body);
  return wrap;
}

function buildSuggestions(msg, isLast) {
  if (!isLast || msg.role !== "assistant" || msg.error) return null;
  const lastUser = [...currentChat().messages].reverse().find((m) => m.role === "user");
  const suggestions = getSuggestedFollowups(
    lastUser ? lastUser.content : "",
    msg.details?.intent || "GENERAL",
    msg.details?.tool_used || null
  );
  if (!suggestions.length) return null;

  const wrap = document.createElement("div");
  wrap.className = "suggestions";
  const label = document.createElement("div");
  label.className = "suggestions-label";
  label.textContent = "Suggested questions";
  const row = document.createElement("div");
  row.className = "suggestions-row";
  for (const s of suggestions) {
    const chip = document.createElement("button");
    chip.className = "suggestion-chip";
    chip.textContent = s;
    chip.addEventListener("click", () => sendMessage(s));
    row.appendChild(chip);
  }
  wrap.append(label, row);
  return wrap;
}

function renderMessages() {
  const chat = currentChat();
  messagesEl.innerHTML = "";
  const hasMessages = chat && chat.messages.length > 0;
  heroEl.style.display = hasMessages ? "none" : "";
  topbarTitle.textContent = chat ? chat.title : "New conversation";
  if (!hasMessages) return;

  chat.messages.forEach((msg, idx) => {
    if (msg.role === "user") {
      const el = document.createElement("div");
      el.className = "msg-user";
      el.textContent = msg.content;
      messagesEl.appendChild(el);
    } else {
      const el = document.createElement("div");
      el.className = "msg-assistant";
      const body = document.createElement("div");
      body.innerHTML = renderMarkdown(msg.content);
      el.appendChild(body);
      const details = buildAgentDetails(msg.details);
      if (details) el.appendChild(details);
      if (msg.errorDetail) {
        const err = document.createElement("div");
        err.className = "error-note";
        err.innerHTML = `<b>Service notice</b>${escapeHtml(msg.errorDetail)}`;
        el.appendChild(err);
      }
      const sugs = buildSuggestions(msg, idx === chat.messages.length - 1);
      if (sugs) el.appendChild(sugs);
      messagesEl.appendChild(el);
    }
  });
  scrollToBottom();
}

function renderAll() {
  renderConversationList();
  renderMessages();
}

/* ---------------------------------------------------------------- chat API */
async function apiChat(message) {
  try {
    const resp = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, user_id: USER_ID }),
    });
    if (resp.ok) return await resp.json();
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (_) {}
    return { _error: true, _status: resp.status, _detail: String(detail) };
  } catch (err) {
    return { _error: true, _status: 0, _detail: `Unable to connect to the ContextAI backend. ${err.message || err}` };
  }
}

async function sendMessage(text) {
  const clean = (text || "").trim();
  if (!clean || sending) return;
  sending = true;
  sendBtn.disabled = true;

  const chat = currentChat();
  if (!chat.messages.length || chat.title === "New conversation") {
    chat.title = clean.length > 32 ? clean.slice(0, 32) + "…" : clean;
  }
  chat.messages.push({ role: "user", content: clean });
  saveConversations();
  renderAll();

  // Thinking indicator
  const thinking = document.createElement("div");
  thinking.className = "msg-assistant";
  thinking.innerHTML = `<span class="thinking"><span class="thinking-dots"><span></span><span></span><span></span></span>Thinking…</span>`;
  messagesEl.appendChild(thinking);
  scrollToBottom();

  const data = await apiChat(clean);
  thinking.remove();

  if (data && data._error) {
    const transient = data._status === 503 || /temporarily unavailable/i.test(data._detail);
    const userMsg = transient
      ? "Gemini is temporarily unavailable. Please try again in a moment."
      : "Something went wrong while processing that request. Please try again.";
    chat.messages.push({ role: "assistant", content: userMsg, error: true, errorDetail: data._detail });
  } else if (data) {
    chat.messages.push({
      role: "assistant",
      content: data.response || "I could not generate a response.",
      details: {
        intent: data.intent || "GENERAL",
        confidence: typeof data.confidence === "number" ? data.confidence : 0,
        tool_used: data.tool_used || null,
        sources: data.sources || null,
      },
    });
  } else {
    chat.messages.push({
      role: "assistant",
      content: "I am currently unable to reach the ContextAI reasoning engine. Please ensure the FastAPI backend is running.",
      error: true,
    });
  }

  saveConversations();
  sending = false;
  sendBtn.disabled = composerInput.value.trim() === "";
  renderAll();
}

/* ---------------------------------------------------------------- composer */
function autogrow() {
  composerInput.style.height = "auto";
  composerInput.style.height = Math.min(composerInput.scrollHeight, 200) + "px";
}

composerInput.addEventListener("input", () => {
  autogrow();
  sendBtn.disabled = sending || composerInput.value.trim() === "";
});
composerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = composerInput.value;
  composerInput.value = "";
  autogrow();
  sendMessage(v);
});

document.querySelectorAll(".starter-card").forEach((btn) => {
  btn.addEventListener("click", () => sendMessage(btn.dataset.prompt));
});

/* ---------------------------------------------------------------- dialogs */
const dialogs = {
  documents: $("#dialog-documents"),
  memory: $("#dialog-memory"),
  reminders: $("#dialog-reminders"),
  settings: $("#dialog-settings"),
};

document.querySelectorAll(".tool-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const d = dialogs[btn.dataset.dialog];
    if (!d) return;
    if (btn.dataset.dialog === "documents") refreshDocCount();
    if (btn.dataset.dialog === "reminders") refreshReminders();
    if (btn.dataset.dialog === "settings") refreshSettings();
    if (isMobile()) closeSidebar();
    d.showModal();
  });
});
document.querySelectorAll("[data-close]").forEach((btn) => {
  btn.addEventListener("click", () => btn.closest("dialog").close());
});
document.querySelectorAll("dialog").forEach((d) => {
  d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
});

/* ---- Documents & RAG ---- */
const pdfInput = $("#pdf-input");
const pdfBtn = $("#pdf-upload-btn");
const pdfStatus = $("#pdf-status");

pdfInput.addEventListener("change", () => { pdfBtn.disabled = !pdfInput.files.length; });

async function refreshDocCount() {
  try {
    const resp = await fetch(`${API}/documents`);
    const data = resp.ok ? await resp.json() : null;
    const count = data ? data.total_chunks ?? 0 : 0;
    $("#doc-chunk-count").textContent = count;
    const badge = $("#sidebar-docs-badge");
    if (badge) badge.textContent = `${count} chunks`;
  } catch (_) {
    $("#doc-chunk-count").textContent = "0";
  }
}

pdfBtn.addEventListener("click", async () => {
  const file = pdfInput.files[0];
  if (!file) return;
  pdfBtn.disabled = true;
  pdfStatus.hidden = false;
  pdfStatus.className = "modal-status";
  pdfStatus.textContent = "Extracting text with PyMuPDF and embedding into ChromaDB…";
  try {
    const fd = new FormData();
    fd.append("file", file);
    const resp = await fetch(`${API}/documents/upload`, { method: "POST", body: fd });
    const data = await resp.json();
    if (resp.ok && data.success) {
      pdfStatus.className = "modal-status ok";
      pdfStatus.textContent = `Indexed ${data.document_name}: ${data.total_pages} pages, ${data.total_chunks} chunks.`;
      refreshDocCount();
    } else {
      pdfStatus.className = "modal-status err";
      pdfStatus.textContent = `Upload failed: ${data.detail || resp.statusText}`;
    }
  } catch (err) {
    pdfStatus.className = "modal-status err";
    pdfStatus.textContent = `Document upload error: ${err.message || err}`;
  }
  pdfBtn.disabled = false;
});

/* ---- Memory ---- */
$("#clear-memory-btn").addEventListener("click", async () => {
  const status = $("#memory-status");
  status.hidden = false;
  try {
    const resp = await fetch(`${API}/memory/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID }),
    });
    if (resp.ok) {
      status.className = "modal-status ok";
      status.textContent = "Your conversation memory has been cleared successfully.";
      toast("Conversation memory cleared");
    } else {
      status.className = "modal-status err";
      status.textContent = "Failed to clear conversation memory.";
    }
  } catch (_) {
    status.className = "modal-status err";
    status.textContent = "Failed to clear conversation memory — backend unreachable.";
  }
});

/* ---- Reminders ---- */
function updateRemindersBadge(pendingCount) {
  const badge = $("#sidebar-reminders-badge");
  if (!badge) return;
  if (pendingCount > 0) {
    badge.textContent = pendingCount > 99 ? "99+" : String(pendingCount);
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function fetchReminders(status) {
  try {
    const params = new URLSearchParams({ user_id: USER_ID });
    if (status) params.set("status", status);
    const resp = await fetch(`${API}/reminders?${params}`);
    if (resp.ok) return (await resp.json()).reminders || [];
  } catch (_) {}
  return [];
}

function reminderRow(r, done) {
  const row = document.createElement("div");
  row.className = "reminder-row";
  const left = document.createElement("div");
  left.innerHTML = `<div class="reminder-text${done ? " done" : ""}">${escapeHtml(r.reminder_text)}</div>
    <div class="reminder-due">${done ? "Completed · Was due: " : "Due: "}${escapeHtml(r.scheduled_time)}</div>`;
  const actions = document.createElement("div");
  actions.className = "reminder-actions";
  if (!done) {
    const okBtn = document.createElement("button");
    okBtn.textContent = "✓";
    okBtn.title = "Mark completed";
    okBtn.addEventListener("click", async () => {
      await fetch(`${API}/reminders/${r.id}/complete?user_id=${USER_ID}`, { method: "PATCH" });
      refreshReminders();
      checkDueReminders();
    });
    actions.appendChild(okBtn);
  }
  const delBtn = document.createElement("button");
  delBtn.textContent = "🗑";
  delBtn.title = "Delete";
  delBtn.addEventListener("click", async () => {
    await fetch(`${API}/reminders/${r.id}?user_id=${USER_ID}`, { method: "DELETE" });
    refreshReminders();
    checkDueReminders();
  });
  actions.appendChild(delBtn);
  row.append(left, actions);
  return row;
}

async function refreshReminders() {
  const activeEl = $("#tab-active");
  const compEl = $("#tab-completed");
  const [pending, completed] = await Promise.all([fetchReminders("pending"), fetchReminders("completed")]);
  activeEl.innerHTML = pending.length ? "" : `<p class="modal-caption">You have no pending reminders.</p>`;
  pending.forEach((r) => activeEl.appendChild(reminderRow(r, false)));
  compEl.innerHTML = completed.length ? "" : `<p class="modal-caption">No completed reminders recorded.</p>`;
  completed.forEach((r) => compEl.appendChild(reminderRow(r, true)));
  updateRemindersBadge(pending.length);
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.id !== `tab-${tab.dataset.tab}`));
  });
});

$("#reminder-create-btn").addEventListener("click", async () => {
  const text = $("#reminder-text").value.trim();
  const date = $("#reminder-date").value;
  const time = $("#reminder-time").value || "12:00";
  const status = $("#reminder-status");
  status.hidden = false;
  if (!text) {
    status.className = "modal-status err";
    status.textContent = "Please provide reminder text.";
    return;
  }
  if (!date) {
    status.className = "modal-status err";
    status.textContent = "Please choose a date.";
    return;
  }
  try {
    const resp = await fetch(`${API}/reminders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reminder_text: text, scheduled_time: `${date} ${time}`, user_id: USER_ID }),
    });
    if (resp.ok) {
      status.className = "modal-status ok";
      status.textContent = "Reminder scheduled.";
      $("#reminder-text").value = "";
      toast("Reminder scheduled");
      refreshReminders();
      checkDueReminders();
    } else {
      const data = await resp.json().catch(() => ({}));
      status.className = "modal-status err";
      status.textContent = `Could not schedule reminder: ${data.detail || resp.statusText}`;
    }
  } catch (_) {
    status.className = "modal-status err";
    status.textContent = "Could not schedule reminder — backend unreachable.";
  }
});

/* ---- Settings ---- */
async function refreshSettings() {
  $("#settings-backend-url").textContent = BACKEND_URL || "(same origin)";
  const el = $("#settings-health");
  el.hidden = false;
  try {
    const resp = await fetch(`${BACKEND_URL}/health`);
    if (resp.ok) {
      el.className = "modal-status ok";
      el.textContent = "● Connected to FastAPI reasoning engine";
      return;
    }
    throw new Error();
  } catch (_) {
    el.className = "modal-status err";
    el.textContent = "● Backend offline or unreachable";
  }
}

/* ---- Due reminders banner ---- */
async function checkDueReminders() {
  const pending = await fetchReminders("pending");
  updateRemindersBadge(pending.length);
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const nowStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const due = pending.filter((r) => (r.scheduled_time || "") <= nowStr);
  if (due.length) {
    dueBanner.hidden = false;
    dueBanner.innerHTML = due
      .map((r) => `<b>Reminder due:</b> ${escapeHtml(r.reminder_text)} <span style="color:var(--text-faint)">(${escapeHtml(r.scheduled_time)})</span>`)
      .join("<br/>");
  } else {
    dueBanner.hidden = true;
  }
}

/* ---------------------------------------------------------------- suggestions */
function getSuggestedFollowups(query, intent, toolUsed) {
  const q = (query || "").toLowerCase();
  const t = (toolUsed || "").toLowerCase();
  const i = (intent || "").toUpperCase();

  if (t.includes("crypto") || i === "CRYPTO" || /bitcoin|btc|eth|crypto|solana/.test(q)) {
    if (q.includes("eth")) return ["How has Ethereum changed in 24 hours?", "What's Bitcoin's current price?", "Compare Ethereum and Solana"];
    if (q.includes("sol")) return ["How has Solana changed in 24 hours?", "What's Bitcoin's current price?", "Compare Solana and Ethereum"];
    return ["How has Bitcoin changed in 24 hours?", "What's Ethereum's current price?", "Compare Bitcoin and Ethereum"];
  }
  if (t.includes("weather") || i === "WEATHER" || q.includes("weather") || q.includes("temperature")) {
    return ["What is the forecast for tomorrow?", "What's the weather in Tokyo right now?", "What should I wear today?"];
  }
  if (t.includes("calculator") || i === "CALCULATOR" || /calculate|\+|\*|\//.test(q)) {
    return ["Convert this result to a percentage", "What is this amount divided by 12?", "Calculate 15% tip on this amount"];
  }
  if (t.includes("rag") || i === "RAG" || /document|pdf|file|page/.test(q)) {
    return ["Summarize the key points from this document", "What other topics are covered in this document?", "List any statistics or data points mentioned"];
  }
  if (t.includes("search") || i === "SEARCH" || q.includes("search")) {
    return ["Tell me more about recent developments on this", "What are the main pros and cons?", "Give me a bullet-point summary"];
  }
  if (i === "REMINDER" || q.includes("remind")) {
    return ["Show all my pending reminders", "Remind me tomorrow at 9 AM", "How do I mark a reminder as completed?"];
  }
  return ["Can you explain this in simpler terms?", "Give me a practical real-world example", "What are the key takeaways?"];
}

/* ---------------------------------------------------------------- init */
loadConversations();
if (!Object.keys(conversations).length) createConversation();
if (!conversations[currentId]) currentId = Object.keys(conversations)[0];

loadAccentTheme();

if (isMobile()) {
  closeSidebar();
} else {
  const savedCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY);
  if (savedCollapsed === "true") closeSidebar();
  else openSidebar();
}

window.addEventListener("resize", () => {
  if (!isMobile()) scrim.hidden = true;
});

renderAll();
refreshDocCount();
checkDueReminders();
composerInput.focus();
