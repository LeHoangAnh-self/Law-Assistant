const documentView = document.querySelector("#documentView");

let rawContent = "";
let focusSnippet = "";
let parsedSections = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalize(value) {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

function metadataRows(documentData) {
  return [
    ["ID", documentData.id],
    ["Số/Ký hiệu", documentData.documentNumber],
    ["Loại văn bản", documentData.documentType],
    ["Tình trạng hiệu lực", documentData.validityStatus],
    ["Ngày ban hành", documentData.issuedDate],
    ["Ngày hiệu lực", documentData.effectiveDate],
    ["Ngày hết hiệu lực", documentData.expiredDate],
    ["Cơ quan ban hành", documentData.issuingAuthority],
    ["Người ký", [documentData.signerTitle, documentData.signerName].filter(Boolean).join(" ")],
    ["Phạm vi", documentData.scope],
    ["Lĩnh vực", documentData.field],
    ["Nguồn trong dữ liệu", documentData.source],
    ["External docid", documentData.externalDocid],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
}

function renderMetadata(documentData) {
  return metadataRows(documentData)
    .map(
      ([label, value]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderRelationships(relationships = []) {
  if (!relationships.length) {
    return '<p class="muted">No relationship records returned.</p>';
  }
  return relationships
    .map(
      (item) => `
        <div class="relationship-row">
          <strong>${escapeHtml(item.relationshipType || item.relationship_type || "Relationship")}</strong>
          <span>Document ${escapeHtml(item.relatedDocumentId || item.related_document_id || "")}</span>
        </div>
      `,
    )
    .join("");
}

function parseLegalSections(content) {
  const lines = String(content || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const sections = [];
  let current = { title: "Thông tin chung", body: [] };
  const headingPattern =
    /^(PHẦN\s+|CHƯƠNG\s+|MỤC\s+|TIỂU MỤC\s+|Điều\s+\d+[\.:]?|Điều\s+[IVXLCDM]+[\.:]?)/i;

  for (const line of lines) {
    if (headingPattern.test(line) && current.body.length) {
      sections.push(current);
      current = { title: line, body: [] };
    } else if (headingPattern.test(line)) {
      if (current.title !== "Thông tin chung" || current.body.length) {
        sections.push(current);
      }
      current = { title: line, body: [] };
    } else {
      current.body.push(line);
    }
  }
  if (current.title !== "Thông tin chung" || current.body.length) {
    sections.push(current);
  }
  return sections.length ? sections : [{ title: "Full text", body: [content] }];
}

function highlight(value, query) {
  let safe = escapeHtml(value);
  const terms = [query, focusSnippet]
    .map(normalize)
    .filter((term) => term.length >= 8)
    .map((term) => term.slice(0, 180));

  terms.forEach((term) => {
    const words = term.split(" ").filter(Boolean);
    const pattern =
      words.length > 8 ? words.slice(0, 8).map(escapeRegExp).join("\\s+") : escapeRegExp(term);
    safe = safe.replace(new RegExp(`(${pattern})`, "gi"), "<mark>$1</mark>");
  });
  return safe;
}

function renderContent(query = "") {
  const target = document.querySelector("#documentContent");
  const toc = document.querySelector("#documentToc");
  if (!target) return;

  if (!parsedSections.length) {
    target.innerHTML = '<p class="muted">No text content is available for this document.</p>';
    return;
  }

  if (toc) {
    toc.innerHTML = parsedSections
      .slice(0, 80)
      .map(
        (section, index) => `
          <button type="button" class="toc-link" data-target-section="${index}">
            ${escapeHtml(section.title)}
          </button>
        `,
      )
      .join("");
    toc.querySelectorAll("[data-target-section]").forEach((button) => {
      button.addEventListener("click", () => {
        document
          .querySelector(`[data-section="${button.dataset.targetSection}"]`)
          ?.scrollIntoView({ block: "start" });
      });
    });
  }

  target.innerHTML = parsedSections
    .map(
      (section, index) => `
        <section class="legal-section" data-section="${index}">
          <h3>${escapeHtml(section.title)}</h3>
          ${section.body
            .map(
              (paragraph, paragraphIndex) => `
                <p class="document-paragraph" data-paragraph="${paragraphIndex + 1}">
                  <span class="paragraph-number">${paragraphIndex + 1}</span>
                  <span>${highlight(paragraph, query).replaceAll("\n", "<br />")}</span>
                </p>
              `,
            )
            .join("")}
        </section>
      `,
    )
    .join("");

  const firstMark = target.querySelector("mark");
  if (firstMark) {
    firstMark.scrollIntoView({ block: "center" });
  }
}

function readFocusSnippet(id) {
  try {
    const stored = localStorage.getItem(`lawassistant:citation-focus:${id}`);
    if (!stored) return "";
    const parsed = JSON.parse(stored);
    return parsed.text || "";
  } catch {
    return "";
  }
}

async function loadDocument() {
  const id = window.location.pathname.split("/").filter(Boolean).pop();
  focusSnippet = readFocusSnippet(id);

  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(id)}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    }

    const documentData = data.document || {};
    rawContent = data.contentText || "";
    parsedSections = parseLegalSections(rawContent);
    document.title = documentData.title || `Document ${id}`;

    const sourceLink = documentData.sourceUrl
      ? `<a href="${escapeHtml(documentData.sourceUrl)}" target="_blank" rel="noreferrer">External original</a>`
      : '<span class="muted">No external URL</span>';

    documentView.innerHTML = `
      <header class="document-header">
        <p class="eyebrow">Local Law Service Document</p>
        <h1>${escapeHtml(documentData.title || `Document ${id}`)}</h1>
        <div class="document-actions">
          <a href="/">Back to chat</a>
          ${sourceLink}
        </div>
      </header>

      <section class="document-reader-grid">
        <aside class="document-sidebar">
          <section class="document-card">
            <h2>Document Details</h2>
            <div class="document-metadata">${renderMetadata(documentData)}</div>
          </section>
          <section class="document-card">
            <h2>Search Text</h2>
            <input id="documentSearch" type="search" placeholder="Find in document" />
            ${
              focusSnippet
                ? '<button type="button" id="focusCitationBtn">Show cited passage</button>'
                : '<p class="muted">Open from a citation to focus the retrieved passage.</p>'
            }
          </section>
          <section class="document-card">
            <h2>Contents</h2>
            <div class="document-toc" id="documentToc"></div>
          </section>
          <section class="document-card">
            <h2>Relationships</h2>
            ${renderRelationships(data.relationships || [])}
          </section>
        </aside>

        <section class="document-body-wrap">
          <div class="document-body-header">
            <h2>Full Text</h2>
            <span>${rawContent.length.toLocaleString()} characters</span>
          </div>
          <div class="document-body" id="documentContent"></div>
        </section>
      </section>
    `;

    renderContent(focusSnippet);
    document.querySelector("#documentSearch")?.addEventListener("input", (event) => {
      renderContent(event.target.value);
    });
    document.querySelector("#focusCitationBtn")?.addEventListener("click", () => {
      document.querySelector("#documentSearch").value = "";
      renderContent(focusSnippet);
    });
  } catch (error) {
    documentView.innerHTML = `<p class="error-text">${escapeHtml(error.message)}</p>`;
  }
}

loadDocument();
