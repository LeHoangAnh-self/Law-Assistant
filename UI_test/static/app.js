const messages = document.querySelector("#messages");
const citations = document.querySelector("#citations");
const citationCount = document.querySelector("#citationCount");
const healthBadge = document.querySelector("#healthBadge");
const askForm = document.querySelector("#askForm");
const questionInput = document.querySelector("#question");
const topKInput = document.querySelector("#topK");
const cutoffDateInput = document.querySelector("#cutoffDate");
const filterKeyInput = document.querySelector("#filterKey");
const filterValueInput = document.querySelector("#filterValue");
const apiKeyInput = document.querySelector("#apiKey");
const testModelInput = document.querySelector("#testModel");
const reasoningEffortInput = document.querySelector("#reasoningEffort");
const testKeyBtn = document.querySelector("#testKeyBtn");
const forgetKeyBtn = document.querySelector("#forgetKeyBtn");
const keyStatus = document.querySelector("#keyStatus");
const includeContextInput = document.querySelector("#includeContext");
const sendBtn = document.querySelector("#sendBtn");
const clearBtn = document.querySelector("#clearBtn");
const newChatBtn = document.querySelector("#newChatBtn");
const exportBtn = document.querySelector("#exportBtn");
const messageTemplate = document.querySelector("#messageTemplate");
let conversationId = crypto.randomUUID();
let latestHealth = null;
const chatLog = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function inlineFormat(value) {
  return escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

function markdownLite(value) {
  const lines = String(value ?? "").replace(/\r/g, "").split("\n");
  const html = [];
  let listType = null;

  function closeList() {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      closeList();
      html.push(`<h3>${inlineFormat(heading[1])}</h3>`);
      continue;
    }

    const numberedHeading = line.match(/^(\d+)\.\s+\*\*(.+?)\*\*$/);
    if (numberedHeading) {
      closeList();
      html.push(`<h3><span>${numberedHeading[1]}</span>${inlineFormat(numberedHeading[2])}</h3>`);
      continue;
    }

    const numbered = line.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) {
      if (listType !== "ol") {
        closeList();
        listType = "ol";
        html.push("<ol>");
      }
      html.push(`<li>${inlineFormat(numbered[2])}</li>`);
      continue;
    }

    const bullet = line.match(/^[-–]\s+(.+)$/);
    if (bullet) {
      if (listType !== "ul") {
        closeList();
        listType = "ul";
        html.push("<ul>");
      }
      html.push(`<li>${inlineFormat(bullet[1])}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${inlineFormat(line)}</p>`);
  }

  closeList();
  return html.join("");
}

function addMessage(role, html, meta = []) {
  const node = messageTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  const isUser = role === "user";
  node.querySelector(".avatar").textContent = isUser ? "You" : "AI";
  node.querySelector(".message-author").textContent = isUser ? "You" : "Law Assistant";
  node.querySelector(".message-time").textContent = new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
  const bubble = node.querySelector(".bubble");
  bubble.innerHTML = html;

  if (meta.length > 0) {
    const row = document.createElement("div");
    row.className = "meta-row";
    row.innerHTML = meta.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
    bubble.appendChild(row);
  }

  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function setStatus(node, message, type = "") {
  node.textContent = message;
  node.className = `setting-status ${type}`.trim();
}

function compact(value, limit = 120) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trim()}...`;
}

function citationTitle(reference, index) {
  return (
    reference.title ||
    reference.document_number ||
    reference.legal_path ||
    reference.chunk_id ||
    `Citation ${index + 1}`
  );
}

function citationLocation(reference) {
  return [
    reference.legal_path,
    reference.article_number ? `Article ${reference.article_number}` : null,
    reference.clause_number ? `Clause ${reference.clause_number}` : null,
    reference.point_number ? `Point ${reference.point_number}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function citationNumbers(answer = "") {
  return new Set(
    [...String(answer).matchAll(/\[(\d+)\]/g)]
      .map((match) => Number(match[1]))
      .filter((value) => Number.isFinite(value)),
  );
}

function supportLabel(reference, index, citedNumbers) {
  if (citedNumbers.has(index + 1)) {
    return "Cited in answer";
  }
  if (Number(reference.score || 0) < 3) {
    return "Weak retrieval";
  }
  return "Retrieved only";
}

function renderCitations(references = [], answer = "") {
  citationCount.textContent = references.length;
  citations.innerHTML = "";
  const citedNumbers = citationNumbers(answer);

  if (references.length === 0) {
    citations.innerHTML = '<p class="muted">No citations returned.</p>';
    return;
  }

  references.forEach((reference, index) => {
    const title = citationTitle(reference, index);
    const location = citationLocation(reference);
    const label = supportLabel(reference, index, citedNumbers);
    const meta = [
      label,
      `Document ${reference.document_id}`,
      reference.document_number,
      reference.document_type,
      reference.validity_status,
      reference.issued_date ? `Issued ${reference.issued_date}` : null,
      reference.effective_date ? `Effective ${reference.effective_date}` : null,
      reference.score !== undefined ? `Score ${Number(reference.score).toFixed(3)}` : null,
    ].filter(Boolean);

    const localDocumentUrl = `/documents/${encodeURIComponent(reference.document_id)}`;

    const node = document.createElement("article");
    node.className = "citation";
    node.dataset.support = label;
    const openId = `open-doc-${index}`;
    node.innerHTML = `
      <div class="citation-head">
        <div class="citation-title">[${index + 1}] ${escapeHtml(title)}</div>
        <span class="support-badge">${escapeHtml(label)}</span>
      </div>
      <div class="citation-meta">${meta.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("")}</div>
      ${location ? `<div class="citation-location">${escapeHtml(location)}</div>` : ""}
      <div class="citation-label">Retrieved passage</div>
      <div class="citation-text">${escapeHtml(reference.text || "")}</div>
      <div class="citation-actions">
        <a class="source-link" id="${openId}" href="${localDocumentUrl}" target="_blank" rel="noreferrer">Open local document</a>
        <button type="button" class="text-button" data-copy-citation="${index}">Copy citation</button>
      </div>
    `;
    citations.appendChild(node);
    node.querySelector(`#${openId}`).addEventListener("click", () => {
      localStorage.setItem(
        `lawassistant:citation-focus:${reference.document_id}`,
        JSON.stringify({
          text: reference.text || "",
          title,
          chunk_id: reference.chunk_id,
          saved_at: new Date().toISOString(),
        }),
      );
    });
    node.querySelector("[data-copy-citation]").addEventListener("click", async () => {
      await navigator.clipboard.writeText(
        `[${index + 1}] ${title}\n${reference.document_number || ""}\n${reference.text || ""}`,
      );
    });
  });
}

function buildPayload() {
  const filters = {};
  const filterKey = filterKeyInput.value.trim();
  const filterValue = filterValueInput.value.trim();
  if (filterKey && filterValue) {
    filters[filterKey] = filterValue;
  }

  const payload = {
    question: questionInput.value.trim(),
    top_k: Number(topKInput.value || 6),
    conversation_id: conversationId,
    include_context: includeContextInput.checked,
  };

  if (Object.keys(filters).length > 0) {
    payload.filters = filters;
  }

  if (cutoffDateInput.value) {
    payload.retrieval_cutoff_date = cutoffDateInput.value;
  }

  return payload;
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Health check failed");
    }
    latestHealth = data;
    healthBadge.textContent = `RAG connected: ${data.rag_api_base_url}`;
    healthBadge.className = "health ok";
  } catch (error) {
    healthBadge.textContent = error.message;
    healthBadge.className = "health error";
  }
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildPayload();
  if (!payload.question) {
    questionInput.focus();
    return;
  }

  addMessage("user", markdownLite(payload.question));
  chatLog.push({
    role: "user",
    content: payload.question,
    created_at: new Date().toISOString(),
  });
  const pending = addMessage("assistant", '<p class="muted">Retrieving sources and asking the model...</p>');
  sendBtn.disabled = true;

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    }

    pending.querySelector(".bubble").innerHTML = markdownLite(data.answer);
    conversationId = data.conversation_id || conversationId;
    const meta = [
      `Class: ${data.classification}`,
      `Retrieval: ${compact(data.retrieval_query || data.rewritten_query, 120)}`,
      `${data.references?.length || 0} citations`,
      data.used_context ? "Context used" : "Standalone",
    ];
    const row = document.createElement("div");
    row.className = "meta-row";
    row.innerHTML = meta.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("");
    pending.querySelector(".bubble").appendChild(row);
    renderCitations(data.references || [], data.answer || "");
    chatLog.push({
      role: "assistant",
      answer: data.answer,
      original_question: data.original_question || payload.question,
      contextual_question: data.contextual_question,
      conversation_context: data.conversation_context,
      retrieval_query: data.retrieval_query,
      rewritten_query: data.rewritten_query,
      classification: data.classification,
      used_context: Boolean(data.used_context),
      references: data.references || [],
      created_at: new Date().toISOString(),
    });
  } catch (error) {
    pending.querySelector(".bubble").innerHTML = `<p class="error-text">${escapeHtml(error.message)}</p>`;
    chatLog.push({
      role: "error",
      content: error.message,
      original_question: payload.question,
      created_at: new Date().toISOString(),
    });
  } finally {
    sendBtn.disabled = false;
    questionInput.value = "";
    questionInput.focus();
  }
});

function resetVisibleChat() {
  messages.innerHTML = "";
  addMessage(
    "assistant",
    "<p>Ask a Vietnamese legal question. Follow-up questions will use this chat's recent context when enabled.</p>",
  );
  renderCitations([]);
  questionInput.value = "";
  questionInput.focus();
}

clearBtn.addEventListener("click", () => {
  resetVisibleChat();
});

newChatBtn.addEventListener("click", async () => {
  if (conversationId) {
    await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" }).catch(
      () => {},
    );
  }
  conversationId = crypto.randomUUID();
  chatLog.length = 0;
  resetVisibleChat();
});

testKeyBtn.addEventListener("click", async () => {
  const apiKey = apiKeyInput.value.trim();
  const model = testModelInput.value.trim() || "gpt-5.5";
  const reasoningEffort = reasoningEffortInput.value || "medium";
  if (!apiKey) {
    setStatus(keyStatus, "Enter an API key first.", "error");
    apiKeyInput.focus();
    return;
  }

  testKeyBtn.disabled = true;
  setStatus(keyStatus, "Testing OpenAI connection...", "");
  try {
    const response = await fetch("/api/openai/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, model, reasoning_effort: reasoningEffort }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      throw new Error(detail);
    }
    sessionStorage.setItem("lawassistant:openai-key-present", "true");
    setStatus(keyStatus, `Connected. Model responded: ${data.response || "OK"}`, "ok");
  } catch (error) {
    setStatus(keyStatus, error.message, "error");
  } finally {
    testKeyBtn.disabled = false;
  }
});

forgetKeyBtn.addEventListener("click", () => {
  apiKeyInput.value = "";
  sessionStorage.removeItem("lawassistant:openai-key-present");
  setStatus(keyStatus, "Key cleared from this page.", "");
});

exportBtn.addEventListener("click", () => {
  const payload = {
    exported_at: new Date().toISOString(),
    conversation_id: conversationId,
    ui_version: "UI_test",
    rag_health: latestHealth,
    settings: {
      top_k: Number(topKInput.value || 6),
      retrieval_cutoff_date: cutoffDateInput.value || null,
      filter_key: filterKeyInput.value.trim() || null,
      filter_value: filterValueInput.value.trim() || null,
      include_context: includeContextInput.checked,
      test_model: testModelInput.value.trim() || null,
      reasoning_effort: reasoningEffortInput.value || null,
      api_key_present_in_ui: Boolean(apiKeyInput.value.trim()),
    },
    messages: chatLog,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `rag-chat-log-${new Date().toISOString().replaceAll(":", "-")}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});

checkHealth();
