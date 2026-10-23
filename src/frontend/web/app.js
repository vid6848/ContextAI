/* ============================================================================
   ContextAI — Frontend Application Logic
   Talks to the existing FastAPI backend over the same REST API.
   ============================================================================ */
"use strict";

/* ---------------------------------------------------------------- config */
const BACKEND_URL = (window.CONTEXTAI_BACKEND_URL || "").replace(/\/$/, "");
const API = `${BACKEND_URL}/api/v1`;
// Anonymous per-browser identity until real sign-in lands (issue #17)
const USER_ID = (() => {
  const KEY = "contextai_user_id";
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch (_) {
    return crypto.randomUUID();
  }
})();
const THEME_STORAGE_KEY = "contextai_accent_theme";
const SIDEBAR_STORAGE_KEY = "contextai_sidebar_collapsed";

/* ---------------------------------------------------------------- state */
let conversations = {}; // id -> { id, title, updated_at, messages: null | [{role, content, details}] }
let currentId = null; // null = unsaved draft; the server assigns an id on first send
let draft = { id: null, title: "New conversation", messages: [] };
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
const userQuery = () => `user_id=${encodeURIComponent(USER_ID)}`;

async function loadConversations() {
  try {
    const resp = await fetch(`${API}/conversations?${userQuery()}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const next = {};
    for (const c of data.conversations) {
      // Keep already-loaded messages so switching back doesn't refetch
      next[c.id] = { ...c, messages: conversations[c.id]?.messages ?? null };
    }
    conversations = next;
  } catch (_) { /* backend unreachable — sidebar stays empty */ }
}

function fromServerMessage(m) {
  const msg = { id: m.id, role: m.role, content: m.message };
  if (m.role === "assistant" && m.metadata) msg.details = m.metadata;
  return msg;
}

async function openConversation(id) {
  currentId = id;
  const chat = conversations[id];
  if (chat && chat.messages === null) {
    chat.messages = [];
    renderAll();
    try {
      const resp = await fetch(`${API}/conversations/${id}/messages?${userQuery()}`);
      if (resp.ok) chat.messages = (await resp.json()).messages.map(fromServerMessage);
    } catch (_) { toast("Could not load this conversation"); }
  }
  renderAll();
}

function createConversation() {
  currentId = null;
  draft = { id: null, title: "New conversation", messages: [] };
}

function currentChat() {
  return currentId ? conversations[currentId] : draft;
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
    .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
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
      openConversation(c.id);
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
    saveBtn.addEventListener("click", async () => {
      const v = renameInput.value.trim();
      if (!v) return;
      const resp = await fetch(`${API}/conversations/${c.id}?${userQuery()}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: v }),
      }).catch(() => null);
      if (resp && resp.ok) c.title = v;
      else toast("Could not rename conversation");
      renderAll();
    });

    const delBtn = document.createElement("button");
    delBtn.textContent = "Delete";
    delBtn.className = "danger";
    delBtn.addEventListener("click", async () => {
      const resp = await fetch(`${API}/conversations/${c.id}?${userQuery()}`, { method: "DELETE" }).catch(() => null);
      if (!resp || !resp.ok) {
        toast("Could not delete conversation");
        return;
      }
      delete conversations[c.id];
      if (currentId === c.id) createConversation();
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

const ICONS = {
  chevron: `<svg class="chevron" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="m9 6 6 6-6 6"/></svg>`,
  check: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`,
  cross: `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>`,
  copy: `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="13" height="13" x="9" y="9" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  regenerate: `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>`,
  edit: `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`,
  send: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5m-7 7 7-7 7 7" /></svg>`,
  stop: `<svg viewBox="0 0 24 24" width="14" height="14"><rect x="5" y="5" width="14" height="14" rx="2.5" fill="currentColor"/></svg>`,
};

function formatMs(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function stepIcon(status) {
  if (status === "running") return `<span class="step-spinner" aria-label="Running"></span>`;
  if (status === "error") return `<span class="step-icon err">${ICONS.cross}</span>`;
  return `<span class="step-icon ok">${ICONS.check}</span>`;
}

/* Collapsible agent timeline: open while the answer streams, collapsed to a one-line summary after. */
function buildAgentSteps(msg) {
  const details = msg.details || {};
  const steps = details.steps || [];
  if (!steps.length && !details.intent) return null;

  const wrap = document.createElement("details");
  wrap.className = "agent-steps";
  wrap.open = msg.streaming || !!msg.stepsOpen;
  wrap.addEventListener("toggle", () => { if (!msg.streaming) msg.stepsOpen = wrap.open; });

  const summary = document.createElement("summary");
  if (msg.streaming) {
    const running = steps.find((s) => s.status === "running");
    const label = running ? running.label : steps.length ? "Writing response" : "Thinking";
    summary.innerHTML = `<span class="step-spinner"></span><span>${escapeHtml(label)}…</span>`;
  } else {
    const total = steps.reduce((t, s) => t + (s.duration_ms || 0), 0);
    const tool = details.tool_used ? ` · ${escapeHtml(details.tool_used.replace("_", " "))}` : "";
    summary.innerHTML = steps.length
      ? `${ICONS.chevron}<span>${steps.length} steps · ${formatMs(total)}${tool}</span>`
      : `${ICONS.chevron}<span>Agent details</span>`;
  }
  wrap.appendChild(summary);

  const list = document.createElement("ol");
  list.className = "step-list";
  for (const s of steps) {
    const li = document.createElement("li");
    li.className = `step step-${s.status}`;
    const head = document.createElement("button");
    head.type = "button";
    head.className = "step-head";
    head.innerHTML = `${stepIcon(s.status)}<span class="step-label">${escapeHtml(s.label)}</span>` +
      (s.duration_ms != null ? `<span class="step-time">${formatMs(s.duration_ms)}</span>` : "");
    li.appendChild(head);
    if (s.detail && s.status !== "running") {
      const pre = document.createElement("pre");
      pre.className = "step-detail";
      pre.hidden = true;
      pre.textContent = JSON.stringify(s.detail, null, 2);
      head.classList.add("expandable");
      head.addEventListener("click", () => { pre.hidden = !pre.hidden; });
      li.appendChild(pre);
    }
    list.appendChild(li);
  }
  wrap.appendChild(list);

  if (!msg.streaming && details.intent) {
    const meta = document.createElement("div");
    meta.className = "step-meta";
    const conf = typeof details.confidence === "number" ? `${Math.round(details.confidence * 100)}%` : "–";
    let html = `<span class="tag">Intent: <b>${escapeHtml(details.intent)}</b></span>` +
      `<span class="tag">Confidence: <b>${conf}</b></span>`;
    if (Array.isArray(details.sources) && details.sources.length) {
      html += `<div class="source-list"><b>Document sources:</b><ul>`;
      for (const s of details.sources) {
        html += `<li><code>${escapeHtml(s.document || "Document")}</code> — Page ${escapeHtml(String(s.page ?? 1))}</li>`;
      }
      html += `</ul></div>`;
    }
    meta.innerHTML = html;
    wrap.appendChild(meta);
  }
  return wrap;
}

function actionButton(icon, label, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "msg-action";
  b.innerHTML = icon;
  b.title = label;
  b.setAttribute("aria-label", label);
  b.addEventListener("click", onClick);
  return b;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard");
  } catch (_) {
    toast("Could not copy");
  }
}

function buildSuggestions(msg, isLast) {
  if (!isLast || msg.role !== "assistant" || msg.error || msg.streaming) return null;
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

function startEditing(idx) {
  const chat = currentChat();
  const msg = chat.messages[idx];
  const row = msg.el;
  if (!row || sending) return;

  const box = document.createElement("div");
  box.className = "edit-box";
  const ta = document.createElement("textarea");
  ta.value = msg.content;
  ta.rows = Math.min(8, msg.content.split("\n").length + 1);
  const buttons = document.createElement("div");
  buttons.className = "edit-buttons";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "ghost-btn";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => renderMessages());
  const save = document.createElement("button");
  save.type = "button";
  save.className = "primary-btn";
  save.textContent = "Send";
  save.addEventListener("click", () => {
    const v = ta.value.trim();
    if (v) sendMessage(v, { replaceIndex: idx });
  });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save.click(); }
    if (e.key === "Escape") { e.stopPropagation(); cancel.click(); }
  });
  buttons.append(cancel, save);
  box.append(ta, buttons);
  row.replaceWith(box);
  msg.el = box;
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}

function regenerate(assistantIdx) {
  const userIdx = assistantIdx - 1;
  const user = currentChat().messages[userIdx];
  if (user && user.role === "user") sendMessage(user.content, { replaceIndex: userIdx });
}

function buildMessageEl(msg, idx, chat) {
  const isLast = idx === chat.messages.length - 1;
  if (msg.role === "user") {
    const row = document.createElement("div");
    row.className = "msg-user-row";
    const bubble = document.createElement("div");
    bubble.className = "msg-user";
    bubble.textContent = msg.content;
    const actions = document.createElement("div");
    actions.className = "msg-actions";
    actions.append(
      actionButton(ICONS.copy, "Copy message", () => copyText(msg.content)),
      actionButton(ICONS.edit, "Edit message", () => startEditing(idx))
    );
    row.append(bubble, actions);
    return row;
  }

  const el = document.createElement("div");
  el.className = "msg-assistant";
  const steps = buildAgentSteps(msg);
  if (steps) el.appendChild(steps);

  const body = document.createElement("div");
  body.className = "msg-body";
  if (msg.content) body.innerHTML = renderMarkdown(msg.content);
  if (msg.streaming) {
    const caret = document.createElement("span");
    caret.className = "stream-caret";
    (body.lastElementChild || body).appendChild(caret);
  }
  el.appendChild(body);

  if (msg.details?.stopped) {
    const note = document.createElement("div");
    note.className = "stopped-note";
    note.textContent = "Stopped";
    el.appendChild(note);
  }
  if (msg.errorDetail) {
    const err = document.createElement("div");
    err.className = "error-note";
    err.innerHTML = `<b>Service notice</b>${escapeHtml(msg.errorDetail)}`;
    el.appendChild(err);
  }
  if (!msg.streaming) {
    const actions = document.createElement("div");
    actions.className = "msg-actions assistant";
    if (msg.content) actions.appendChild(actionButton(ICONS.copy, "Copy response", () => copyText(msg.content)));
    if (isLast && !sending) {
      actions.appendChild(actionButton(ICONS.regenerate, msg.error ? "Retry" : "Regenerate response", () => regenerate(idx)));
    }
    el.appendChild(actions);
  }
  const sugs = buildSuggestions(msg, isLast);
  if (sugs) el.appendChild(sugs);
  return el;
}

function isNearBottom() {
  return chatScroll.scrollHeight - chatScroll.scrollTop - chatScroll.clientHeight < 120;
}

function renderMessages() {
  const chat = currentChat();
  messagesEl.innerHTML = "";
  const hasMessages = chat && chat.messages.length > 0;
  heroEl.style.display = hasMessages ? "none" : "";
  topbarTitle.textContent = chat ? chat.title : "New conversation";
  if (!hasMessages) return;

  chat.messages.forEach((msg, idx) => {
    msg.el = buildMessageEl(msg, idx, chat);
    messagesEl.appendChild(msg.el);
  });
  scrollToBottom();
}

/* Re-render only the streaming message, at most once per frame. */
let pendingFrame = null;
function scheduleMessageUpdate(msg) {
  if (pendingFrame) return;
  pendingFrame = requestAnimationFrame(() => {
    pendingFrame = null;
    const chat = currentChat();
    const idx = chat.messages.indexOf(msg);
    if (idx < 0 || !msg.el) return;
    const stick = isNearBottom();
    const el = buildMessageEl(msg, idx, chat);
    msg.el.replaceWith(el);
    msg.el = el;
    if (stick) scrollToBottom();
  });
}

function renderAll() {
  renderConversationList();
  renderMessages();
}

/* ---------------------------------------------------------------- chat API */
/* POST to the SSE endpoint and dispatch each `event:` to handlers[event](data). */
async function streamChat(payload, signal, handlers) {
  const resp = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch (_) {}
    handlers.error({ detail: detail || `Request failed (${resp.status})` });
    return;
  }

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data && handlers[event]) handlers[event](JSON.parse(data));
    }
  }
}

let activeController = null;

function setStreamingUI(on) {
  sendBtn.classList.toggle("is-stop", on);
  sendBtn.innerHTML = on ? ICONS.stop : ICONS.send;
  sendBtn.setAttribute("aria-label", on ? "Stop generating" : "Send message");
  sendBtn.title = on ? "Stop generating (Esc)" : "Send message";
  sendBtn.disabled = on ? false : composerInput.value.trim() === "";
}

function stopGenerating() {
  if (activeController) activeController.abort();
}

async function reloadMessages(chat) {
  if (!chat.id || sending) return;
  try {
    const resp = await fetch(`${API}/conversations/${chat.id}/messages?${userQuery()}`);
    if (!resp.ok) return;
    chat.messages = (await resp.json()).messages.map(fromServerMessage);
    if (currentChat() === chat) renderMessages();
  } catch (_) { /* keep local copy */ }
}

/* Send a message, or with replaceIndex: edit/regenerate from that user message onward. */
async function sendMessage(text, opts = {}) {
  const clean = (text || "").trim();
  if (!clean || sending) return;
  const chat = currentChat();

  let replaceFromId = null;
  if (opts.replaceIndex != null) {
    replaceFromId = chat.messages[opts.replaceIndex]?.id ?? null;
    chat.messages.splice(opts.replaceIndex);
  }

  sending = true;
  activeController = new AbortController();
  setStreamingUI(true);

  const userMsg = { role: "user", content: clean };
  const reply = { role: "assistant", content: "", streaming: true, details: { steps: [] } };
  chat.messages.push(userMsg, reply);
  renderAll();

  try {
    await streamChat(
      { message: clean, user_id: USER_ID, conversation_id: chat.id, replace_from_message_id: replaceFromId },
      activeController.signal,
      {
        meta(d) {
          if (!chat.id) {
            chat.id = d.conversation_id;
            chat.title = d.title;
            conversations[chat.id] = chat;
            currentId = chat.id;
            topbarTitle.textContent = chat.title;
            renderConversationList();
          }
        },
        step(d) {
          const steps = reply.details.steps;
          const i = steps.findIndex((s) => s.id === d.id);
          if (i >= 0) steps[i] = d;
          else steps.push(d);
          scheduleMessageUpdate(reply);
        },
        token(d) {
          reply.content += d.text;
          scheduleMessageUpdate(reply);
        },
        done(d) {
          const { user_message_id, assistant_message_id, ...details } = d;
          Object.assign(reply.details, details);
          userMsg.id = user_message_id;
          reply.id = assistant_message_id;
        },
        error(d) {
          reply.error = true;
          reply.errorDetail = d.detail;
          if (!reply.content) reply.content = "Sorry, I couldn't complete that response.";
        },
      }
    );
  } catch (err) {
    if (err.name === "AbortError") {
      reply.details.stopped = true;
    } else {
      reply.error = true;
      if (!reply.content) reply.content = "I couldn't reach the ContextAI backend. Please check that it's running.";
      reply.errorDetail = String(err.message || err);
    }
  } finally {
    if (pendingFrame) { cancelAnimationFrame(pendingFrame); pendingFrame = null; }
    reply.streaming = false;
    sending = false;
    activeController = null;
    setStreamingUI(false);
    renderAll();
  }

  await loadConversations();
  renderConversationList();
  // A stopped answer is saved server-side once generation halts; fetch it to learn the message ids
  if (reply.details.stopped) setTimeout(() => reloadMessages(chat), 1500);
}

/* ---------------------------------------------------------------- composer */
function autogrow() {
  composerInput.style.height = "auto";
  composerInput.style.height = Math.min(composerInput.scrollHeight, 200) + "px";
}

composerInput.addEventListener("input", () => {
  autogrow();
  if (!sending) sendBtn.disabled = composerInput.value.trim() === "";
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && sending) stopGenerating();
});
composerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!sending) $("#composer").requestSubmit();
  }
});
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  if (sending) {
    stopGenerating();
    return;
  }
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
    const resp = await fetch(`${API}/documents?${userQuery()}`);
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
    const resp = await fetch(`${API}/documents/upload?${userQuery()}`, { method: "POST", body: fd });
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
      status.textContent = "Your conversations and memories have been cleared.";
      toast("Conversations and memories cleared");
      conversations = {};
      createConversation();
      renderAll();
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
      await fetch(`${API}/reminders/${r.id}/complete?${userQuery()}`, { method: "PATCH" });
      refreshReminders();
      checkDueReminders();
    });
    actions.appendChild(okBtn);
  }
  const delBtn = document.createElement("button");
  delBtn.textContent = "🗑";
  delBtn.title = "Delete";
  delBtn.addEventListener("click", async () => {
    await fetch(`${API}/reminders/${r.id}?${userQuery()}`, { method: "DELETE" });
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
createConversation();
loadConversations().then(renderConversationList);

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
