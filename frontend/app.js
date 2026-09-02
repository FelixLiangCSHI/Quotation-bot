const API_BASE_URL = "http://127.0.0.1:8000";
const STORAGE_KEY = "quotationBot.conversation.v1";
const SAMPLE_REQUEST =
  "I need a FMT digital X-ray system with Focus detector, wall stand, and table.";
const LEGACY_WELCOME_MESSAGE =
  'Send a requirement to generate a quote. After that, continue here with edits like "remove 8620148", "add Focus 43C detector", "删除 table", or "加上 wall stand".';
const LEGACY_MESSAGE_TRANSLATIONS = new Map([
  ["请帮我删除 8620148", "Please remove 8620148"],
  ["帮我加上 Focus 43C detector", "Please add Focus 43C detector"],
]);
const STANDARD_CONFIGS = new Map([
  ["compass", { label: "DRX-Compass", prompt: "I need a standard DRX-Compass FMT configuration." }],
  ["rise", { label: "DRX-Rise", prompt: "I need a standard DRX-Rise configuration." }],
  ["revolution", { label: "DRX-Revolution Plus", prompt: "I need a standard DRX-Revolution Plus configuration." }],
  ["evolution", { label: "DRX-Evolution Plus", prompt: "I need a standard DRX-Evolution Plus configuration." }],
]);
const DEFAULT_REGION = "china";
const REGION_LABELS = new Map([
  ["china", "China"],
  ["italy", "Italy"],
  ["us", "US"],
  ["other", "Other"],
]);
const ADD_COMMANDS = ["add", "include", "append", "加上", "添加", "增加", "加入"];
const REMOVE_COMMANDS = ["remove", "delete", "drop", "exclude", "删去", "删除", "删掉", "去掉", "移除", "不要", "取消"];

const elements = {
  apiState: document.querySelector("#apiState"),
  chatFeed: document.querySelector("#chatFeed"),
  messageInput: document.querySelector("#messageInput"),
  sampleButton: document.querySelector("#sampleButton"),
  attachmentInput: document.querySelector("#attachmentInput"),
  regionSelect: document.querySelector("#regionSelect"),
  standardConfigButtons: document.querySelectorAll("[data-standard-config]"),
  clearSessionButton: document.querySelector("#clearSessionButton"),
  sendButton: document.querySelector("#sendButton"),
  printProposalButton: document.querySelector("#printProposalButton"),
  answerPanel: document.querySelector("#answerPanel"),
  result: document.querySelector("#result"),
  mainModelTitle: document.querySelector("#mainModelTitle"),
  statusBadge: document.querySelector("#statusBadge"),
  accessoryCount: document.querySelector("#accessoryCount"),
  accessoryList: document.querySelector("#accessoryList"),
  historyList: document.querySelector("#historyList"),
  ruleSummary: document.querySelector("#ruleSummary"),
  factsList: document.querySelector("#factsList"),
  alternativeList: document.querySelector("#alternativeList"),
  issueList: document.querySelector("#issueList"),
  proposalPrint: document.querySelector("#proposalPrint"),
};

const state = {
  currentRecommendation: null,
  quoteItems: [],
  candidateItems: [],
  messages: [],
  history: [],
  baseRequestText: "",
  region: DEFAULT_REGION,
  isEdited: false,
};

restoreSession();
elements.regionSelect.value = state.region;
renderSession();
checkApiHealth();

elements.sampleButton.addEventListener("click", () => {
  elements.attachmentInput.click();
});

elements.attachmentInput.addEventListener("change", () => {
  const fileNames = Array.from(elements.attachmentInput.files || []).map((file) => file.name);
  if (!fileNames.length) {
    return;
  }
  addMessage("user", `Attached file(s): ${fileNames.join(", ")}`);
  addMessage("assistant", "Attachment upload is ready in the UI. File parsing is not connected yet.");
  elements.attachmentInput.value = "";
  persistSession();
  renderSession();
});

elements.regionSelect.addEventListener("change", () => {
  state.region = normalizeRegion(elements.regionSelect.value);
  persistSession();
});

for (const button of elements.standardConfigButtons) {
  button.addEventListener("click", () => {
    const config = STANDARD_CONFIGS.get(button.dataset.standardConfig);
    if (config) {
      generateStandardConfiguration(config);
    }
  });
}

async function generateStandardConfiguration(config) {
  setLoading(true);
  addMessage("user", `${config.label} - ${formatRegionLabel(state.region)}`);
  try {
    await generateRecommendation(config.prompt);
  } catch (error) {
    addMessage("assistant", `Request failed: ${error.message}`);
    showError(error.message);
  } finally {
    setLoading(false);
    persistSession();
    renderSession();
  }
}

elements.clearSessionButton.addEventListener("click", () => {
  resetSession();
  persistSession();
  renderSession();
  elements.messageInput.focus();
});

elements.sendButton.addEventListener("click", () => {
  handleMessageSubmit();
});

elements.printProposalButton.addEventListener("click", () => {
  if (!state.quoteItems.length) {
    return;
  }
  renderProposal();
  downloadProposalPdf();
});

elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    handleMessageSubmit();
  }
});

async function checkApiHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    if (!response.ok) {
      throw new Error(`Health check failed with ${response.status}`);
    }
    elements.apiState.textContent = "API ready";
    elements.apiState.className = "api-state ok";
  } catch (error) {
    elements.apiState.textContent = "API offline";
    elements.apiState.className = "api-state error";
    showError("FastAPI is not reachable at http://127.0.0.1:8000.");
  }
}

async function handleMessageSubmit() {
  const message = elements.messageInput.value.trim();
  if (!message) {
    elements.messageInput.focus();
    return;
  }

  addMessage("user", message);
  elements.messageInput.value = "";
  setLoading(true);

  try {
    const command = state.currentRecommendation ? parseEditCommand(message) : null;
    if (command) {
      await applyEditCommand(command, message);
    } else {
      await generateRecommendation(message);
    }
  } catch (error) {
    addMessage("assistant", `Request failed: ${error.message}`);
    showError(error.message);
  } finally {
    setLoading(false);
    persistSession();
    renderSession();
  }
}

async function generateRecommendation(message) {
  const payload = await requestRecommendation(message);
  const recommendation = payload.recommendation;
  state.currentRecommendation = recommendation;
  state.quoteItems = buildQuoteItems(recommendation);
  state.candidateItems = collectCandidateItems(recommendation);
  state.baseRequestText = recommendation.request?.raw_text || message;
  state.isEdited = false;

  addMessage(
    "assistant",
    `Generated ${state.quoteItems.length} quote item(s). You can keep editing in this conversation, use row actions, or add one of the alternatives.`,
    buildRecommendationMeta(payload)
  );
  recordSnapshot(`Generated quote from: ${shortenText(message)}`);
}

async function applyEditCommand(command, originalMessage) {
  if (!state.quoteItems.length) {
    addMessage("assistant", "Generate a quote first, then I can apply add or remove edits to it.");
    return;
  }
  if (!command.query) {
    addMessage("assistant", `Tell me what to ${command.type}. For example: ${command.type} 8620148.`);
    return;
  }

  if (command.type === "remove") {
    removeItemsByQuery(command.query);
    return;
  }

  await addItemByQuery(command.query, originalMessage);
}

function removeItemsByQuery(query) {
  const matches = state.quoteItems.filter((item) => itemMatchesQuery(item, query));
  if (!matches.length) {
    addMessage("assistant", `I could not find "${query}" in the current quote.`);
    return;
  }

  const removedKeys = new Set(matches.map(getItemKey));
  state.quoteItems = state.quoteItems.filter((item) => !removedKeys.has(getItemKey(item)));
  state.isEdited = true;

  const removedNames = matches.map(formatItemName).join(", ");
  addMessage("assistant", `Removed ${removedNames}.`);
  recordSnapshot(`Removed ${removedNames}`);
}

async function addItemByQuery(query, originalMessage) {
  let candidate = findBestCandidate(query, state.candidateItems);
  if (!candidate) {
    const lookupText = `${state.baseRequestText || ""} ${query}`.trim();
    const payload = await requestRecommendation(lookupText || query);
    const newCandidates = collectCandidateItems(payload.recommendation);
    state.candidateItems = dedupeItems([...state.candidateItems, ...newCandidates]);
    candidate = findBestCandidate(query, newCandidates) || newCandidates.find((item) => !isItemInQuote(item));
  }

  if (!candidate) {
    addManualItem(query);
    return;
  }

  if (isItemInQuote(candidate)) {
    addMessage("assistant", `${formatItemName(candidate)} is already in the current quote.`);
    return;
  }

  const item = normalizeQuoteItem(candidate, "Option");
  item.reason = `Added from conversation edit: ${originalMessage}`;
  state.quoteItems = [...state.quoteItems, item];
  state.isEdited = true;

  addMessage("assistant", `Added ${formatItemName(item)}.`);
  recordSnapshot(`Added ${formatItemName(item)}`);
}

function addManualItem(query) {
  const item = normalizeQuoteItem(
    {
      product_id: "Review",
      short_description: query,
      quantity: 1,
      step_id: "Manual",
      reason: "Added by conversation; catalog confirmation is needed.",
      quote_key: `manual-${Date.now()}`,
    },
    "Manual"
  );
  state.quoteItems = [...state.quoteItems, item];
  state.isEdited = true;
  addMessage("assistant", `Added "${query}" as a manual review line because no catalog match was found.`);
  recordSnapshot(`Added manual review line: ${shortenText(query)}`);
}

function addCandidateFromButton(item) {
  if (isItemInQuote(item)) {
    addMessage("assistant", `${formatItemName(item)} is already in the current quote.`);
  } else {
    const quoteItem = normalizeQuoteItem(item, "Option");
    quoteItem.reason = "Added from alternatives.";
    state.quoteItems = [...state.quoteItems, quoteItem];
    state.isEdited = true;
    addMessage("assistant", `Added ${formatItemName(quoteItem)} from alternatives.`);
    recordSnapshot(`Added ${formatItemName(quoteItem)}`);
  }
  persistSession();
  renderSession();
}

function removeItemByKey(itemKey) {
  const item = state.quoteItems.find((quoteItem) => getItemKey(quoteItem) === itemKey);
  if (!item) {
    return;
  }
  state.quoteItems = state.quoteItems.filter((quoteItem) => getItemKey(quoteItem) !== itemKey);
  state.isEdited = true;
  addMessage("assistant", `Removed ${formatItemName(item)}.`);
  recordSnapshot(`Removed ${formatItemName(item)}`);
  persistSession();
  renderSession();
}

async function requestRecommendation(message) {
  const response = await fetch(`${API_BASE_URL}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, region: state.region }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with ${response.status}`);
  }
  return payload;
}

function setLoading(isLoading) {
  elements.sendButton.disabled = isLoading;
  for (const button of elements.standardConfigButtons) {
    button.disabled = isLoading;
  }
  elements.sendButton.innerHTML = isLoading ? "Working" : '<span aria-hidden="true">-&gt;</span> Send';
}

function parseEditCommand(message) {
  const trimmed = message.trim();
  const matches = [
    ...findCommandMatches(trimmed, REMOVE_COMMANDS, "remove"),
    ...findCommandMatches(trimmed, ADD_COMMANDS, "add"),
  ].sort((left, right) => left.index - right.index);
  const match = matches[0];
  if (!match) {
    return null;
  }
  return { type: match.type, query: extractCommandTarget(trimmed, match) };
}

function findCommandMatches(message, commands, type) {
  const lower = message.toLowerCase();
  return commands
    .map((command) => ({ command, index: lower.indexOf(command), type }))
    .filter((match) => match.index >= 0);
}

function extractCommandTarget(message, match) {
  const afterCommand = cleanCommandTarget(message.slice(match.index + match.command.length));
  if (afterCommand) {
    return afterCommand;
  }
  return cleanCommandTarget(message.slice(0, match.index));
}

function cleanCommandTarget(value) {
  return value
    .replace(/^[:：,，\s]+/, "")
    .replace(/^(please|pls|kindly|can you|could you|help me|i want to|i need to)\s+/i, "")
    .replace(/^(请|帮我|麻烦|我要|我想|再|然后|并且|以及|把|将|给我|需要|想要|这个|一个|一项)+/, "")
    .replace(/^(item|option|product|cat|cat#|catalog)\s+/i, "")
    .replace(/\s+(from|in|to)\s+(the\s+)?(quote|list|quotation)$/i, "")
    .replace(/(报价|报价单|清单|里面|中|里)$/u, "")
    .trim();
}

function buildQuoteItems(recommendation) {
  const items = [];
  if (recommendation?.main_model) {
    items.push(normalizeQuoteItem(recommendation.main_model, "Main Model"));
  }
  for (const item of recommendation?.accessories || []) {
    items.push(normalizeQuoteItem(item, "Option"));
  }
  return dedupeItems(items);
}

function collectCandidateItems(recommendation) {
  const items = [
    ...buildQuoteItems(recommendation),
    ...(recommendation?.alternatives || []).map((item) => normalizeQuoteItem(item, "Alternative")),
  ];
  return dedupeItems(items);
}

function normalizeQuoteItem(item, role) {
  return {
    product_id: item.product_id || "-",
    short_description: item.short_description || "Unnamed option",
    quantity: item.quantity || 1,
    step_id: item.step_id || "-",
    option_group: item.option_group || null,
    reason: item.reason || "",
    source: item.source || {},
    quote_role: role || item.quote_role || "Option",
    quote_key: item.quote_key || item.product_id || `${role || "item"}-${item.short_description || Date.now()}`,
  };
}

function dedupeItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.product_id && item.product_id !== "-" ? item.product_id : getItemKey(item);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function findBestCandidate(query, items) {
  const matches = items.filter((item) => itemMatchesQuery(item, query));
  return matches.find((item) => !isItemInQuote(item)) || matches[0] || null;
}

function itemMatchesQuery(item, query) {
  const normalizedQuery = expandQuery(query);
  const normalizedText = normalizeSearchText(
    [item.product_id, item.short_description, item.step_id, item.option_group].filter(Boolean).join(" ")
  );
  const queryText = normalizeSearchText(normalizedQuery);
  const terms = queryText.split(/\s+/).filter(Boolean);
  if (!terms.length) {
    return false;
  }
  return terms.every((term) => normalizedText.includes(term)) || normalizedText.includes(queryText);
}

function expandQuery(query) {
  return query
    .replace(/墙架/g, "wallstand wall stand")
    .replace(/探测器/g, "detector focus")
    .replace(/平床|摄影床/g, "table")
    .replace(/主机|主型号/g, "main model system");
}

function normalizeSearchText(value) {
  return String(value).toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ").trim();
}

function isItemInQuote(item) {
  return state.quoteItems.some((quoteItem) => {
    if (item.product_id && quoteItem.product_id === item.product_id) {
      return true;
    }
    return getItemKey(quoteItem) === getItemKey(item);
  });
}

function getItemKey(item) {
  return item.quote_key || item.product_id || item.short_description;
}

function recordSnapshot(action) {
  state.history.push({
    id: `snapshot-${Date.now()}-${state.history.length}`,
    at: new Date().toISOString(),
    action,
    itemCount: state.quoteItems.length,
    quoteItems: cloneItems(state.quoteItems),
  });
}

function restoreSnapshot(snapshotId) {
  const snapshot = state.history.find((entry) => entry.id === snapshotId);
  if (!snapshot) {
    return;
  }
  state.quoteItems = cloneItems(snapshot.quoteItems);
  state.isEdited = true;
  addMessage("assistant", `Restored snapshot: ${snapshot.action}.`);
  recordSnapshot(`Restored snapshot from ${formatTime(snapshot.at)}`);
  persistSession();
  renderSession();
}

function addMessage(role, text, meta) {
  state.messages.push({ role, text, meta: meta || null, at: new Date().toISOString() });
}

function buildRecommendationMeta(payload) {
  const recommendation = payload.recommendation || {};
  const request = recommendation.request || {};
  const validation = recommendation.validation || {};
  return {
    fields: {
      region: request.region || null,
      system_family: request.system_family || null,
      acquisition_type: request.acquisition_type || null,
      product_ids: request.product_ids || [],
      keywords: (request.keywords || []).slice(0, 6),
    },
    validation: {
      status: validation.status || "unknown",
      missing_fields: validation.missing_fields || [],
      issues: (validation.issues || []).map((issue) => ({
        severity: issue.severity || "issue",
        code: issue.code || "rule",
        message: issue.message || "",
      })),
    },
    explanation: payload.answer || "",
  };
}

function renderSession() {
  renderChat();
  renderQuoteState();
  renderHistory();
}

function renderChat() {
  elements.chatFeed.innerHTML = "";
  for (const message of state.messages) {
    const node = document.createElement("article");
    node.className = `chat-message ${message.role}`;
    node.appendChild(createElement("span", message.role === "user" ? "You" : "Agent 01", "chat-role"));
    node.appendChild(createElement("p", message.text));
    if (message.role === "assistant" && message.meta) {
      node.appendChild(createAgentCard(message.meta));
    }
    elements.chatFeed.appendChild(node);
  }
  elements.chatFeed.scrollTop = elements.chatFeed.scrollHeight;
}

function createAgentCard(meta) {
  const card = document.createElement("div");
  card.className = "agent-card";

  const fields = meta.fields || {};
  const validation = meta.validation || {};

  const header = document.createElement("div");
  header.className = "agent-card-header";
  header.appendChild(createElement("span", "Rule check", "agent-card-title"));
  header.appendChild(
    createElement("span", validation.status || "unknown", `verdict-badge verdict-${validation.status || "unknown"}`)
  );
  card.appendChild(header);

  const chipRow = document.createElement("div");
  chipRow.className = "field-chips";
  const chipEntries = [
    ["Region", fields.region],
    ["System", fields.system_family],
    ["Acquisition", fields.acquisition_type],
    ["Products", (fields.product_ids || []).join(", ")],
    ["Keywords", (fields.keywords || []).join(", ")],
  ];
  for (const [label, value] of chipEntries) {
    if (!value) continue;
    const chip = document.createElement("span");
    chip.className = "field-chip";
    chip.appendChild(createElement("strong", `${label}`));
    chip.appendChild(document.createTextNode(` ${value}`));
    chipRow.appendChild(chip);
  }
  if (chipRow.childElementCount) {
    card.appendChild(createElement("p", "Extracted fields", "agent-card-label"));
    card.appendChild(chipRow);
  }

  if ((validation.missing_fields || []).length) {
    card.appendChild(
      createElement("p", `Missing fields: ${validation.missing_fields.join(", ")}`, "agent-card-missing")
    );
  }

  const issues = validation.issues || [];
  if (issues.length) {
    const issueList = document.createElement("ul");
    issueList.className = "agent-card-issues";
    for (const issue of issues.slice(0, 6)) {
      issueList.appendChild(
        createElement("li", `${(issue.severity || "issue").toUpperCase()} [${issue.code}] ${issue.message}`)
      );
    }
    card.appendChild(issueList);
  }

  if (meta.explanation) {
    const details = document.createElement("details");
    details.className = "agent-card-explanation";
    details.appendChild(createElement("summary", "Explanation"));
    details.appendChild(createElement("p", meta.explanation));
    card.appendChild(details);
  }

  return card;
}

function renderQuoteState() {
  if (!state.currentRecommendation && !state.quoteItems.length) {
    elements.answerPanel.hidden = true;
    elements.result.hidden = true;
    elements.mainModelTitle.textContent = "";
    elements.accessoryCount.textContent = "0";
    elements.accessoryList.innerHTML = "";
    elements.printProposalButton.disabled = true;
    elements.proposalPrint.innerHTML = "";
    renderRuleSummary(null);
    renderFacts({});
    renderAlternatives([]);
    renderIssues([], []);
    return;
  }

  const recommendation = state.currentRecommendation || {};
  const validation = recommendation.validation || {};
  const mainModel = state.quoteItems.find((item) => item.quote_role === "Main Model");

  elements.answerPanel.hidden = false;
  elements.result.hidden = false;
  elements.mainModelTitle.textContent = mainModel ? formatItemName(mainModel) : "No main model in current quote";
  elements.printProposalButton.disabled = state.quoteItems.length === 0;
  renderStatus(state.isEdited ? "edited" : validation.status || "unknown");
  renderQuoteItems(state.quoteItems);
  renderProposal();
  renderRuleSummary(validation);
  renderFacts(recommendation.request || {});
  renderAlternatives(recommendation.alternatives || []);
  renderIssues(validation.issues || [], recommendation.notices || []);
}

function renderStatus(status) {
  elements.statusBadge.textContent = status;
  elements.statusBadge.className = `status-badge ${status}`;
}

function renderQuoteItems(quoteItems) {
  elements.accessoryCount.textContent = String(quoteItems.length);
  elements.accessoryList.innerHTML = "";
  if (!quoteItems.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "quote-empty";
    cell.textContent = "No quote items in the current version.";
    row.appendChild(cell);
    elements.accessoryList.appendChild(row);
    return;
  }
  for (const item of quoteItems) {
    elements.accessoryList.appendChild(createQuoteRow(item));
  }
}

function renderRuleSummary(validation) {
  elements.ruleSummary.innerHTML = "";
  if (!validation) {
    elements.ruleSummary.appendChild(createElement("strong", "No result yet"));
    elements.ruleSummary.appendChild(createElement("span", "Waiting for a recommendation."));
    return;
  }

  const issues = validation.issues || [];
  const missing = validation.missing_fields || [];
  elements.ruleSummary.appendChild(createElement("strong", state.isEdited ? "edited" : validation.status || "unknown"));
  const detail = state.isEdited
    ? "This quote has conversation edits. Generate again to run a fresh rule check."
    : issues.length
      ? `${issues.length} issue(s) returned.`
      : missing.length
        ? `Missing fields: ${missing.join(", ")}.`
        : "No blocking issue was returned.";
  elements.ruleSummary.appendChild(createElement("span", detail));
}

function renderFacts(request) {
  const facts = [
    ["Region", request.region || "-"],
    ["System", request.system_family || "-"],
    ["Acquisition", request.acquisition_type || "-"],
    ["Keywords", (request.keywords || []).join(", ") || "-"],
  ];
  elements.factsList.innerHTML = facts
    .map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
}

function renderAlternatives(alternatives) {
  elements.alternativeList.innerHTML = "";
  if (!alternatives.length) {
    elements.alternativeList.appendChild(createMutedText("No alternatives returned."));
    return;
  }
  for (const item of alternatives.slice(0, 4)) {
    elements.alternativeList.appendChild(createAlternativeItem(item));
  }
}

function renderIssues(issues, notices) {
  elements.issueList.innerHTML = "";
  const entries = [
    ...issues.map((issue) => ({
      title: `${issue.severity || "issue"}: ${issue.code || "rule"}`,
      body: issue.message || "No message returned.",
    })),
    ...notices.map((notice) => ({ title: "notice", body: notice })),
  ];
  if (!entries.length) {
    elements.issueList.appendChild(createMutedText("No issues or notices returned."));
    return;
  }
  for (const entry of entries) {
    const node = document.createElement("div");
    node.className = "compact-item";
    node.appendChild(createElement("strong", entry.title));
    node.appendChild(createElement("span", entry.body));
    elements.issueList.appendChild(node);
  }
}

function renderHistory() {
  elements.historyList.innerHTML = "";
  if (!state.history.length) {
    elements.historyList.appendChild(createMutedText("No quote history yet."));
    return;
  }
  for (const entry of [...state.history].reverse()) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-entry";
    button.addEventListener("click", () => restoreSnapshot(entry.id));
    button.appendChild(createElement("strong", entry.action));
    button.appendChild(createElement("span", `${formatTime(entry.at)} - ${entry.itemCount} item(s)`));
    elements.historyList.appendChild(button);
  }
}

function createQuoteRow(item) {
  const row = document.createElement("tr");
  row.appendChild(createTableCell(formatQuantity(item.quantity), "qty"));
  row.appendChild(createTableCell(item.product_id || "-", "cat"));
  const description = createTableCell("", "description");
  description.appendChild(createElement("strong", item.short_description || "Unnamed option"));
  description.appendChild(createElement("span", item.quote_role || "Option", "row-note"));
  row.appendChild(description);
  row.appendChild(createTableCell(item.step_id || "-", "step"));

  const actionCell = createTableCell("", "actions");
  const removeButton = createElement("button", "Remove", "table-action");
  removeButton.type = "button";
  removeButton.addEventListener("click", () => removeItemByKey(getItemKey(item)));
  actionCell.appendChild(removeButton);
  row.appendChild(actionCell);
  return row;
}

function createAlternativeItem(item) {
  const node = document.createElement("div");
  node.className = "compact-item candidate-item";
  node.appendChild(createElement("strong", formatItemName(item)));
  node.appendChild(createElement("span", item.reason || "Alternative match."));

  const addButton = createElement("button", isItemInQuote(item) ? "Added" : "Add", "mini-action");
  addButton.type = "button";
  addButton.disabled = isItemInQuote(item);
  addButton.addEventListener("click", () => addCandidateFromButton(item));
  node.appendChild(addButton);
  return node;
}

function formatQuantity(quantity) {
  const numericQuantity = Number(quantity);
  if (Number.isFinite(numericQuantity) && numericQuantity > 0) {
    return String(numericQuantity);
  }
  return "1";
}

function formatItemName(item) {
  return `${item.short_description || "Unnamed option"} (${item.product_id || "-"})`;
}

function createTableCell(text, className) {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) {
    cell.className = className;
  }
  return cell;
}

function createMutedText(text) {
  return createElement("p", text, "muted");
}

function createElement(tagName, text, className) {
  const node = document.createElement(tagName);
  node.textContent = text;
  if (className) {
    node.className = className;
  }
  return node;
}

function showError(message) {
  elements.answerPanel.hidden = false;
  elements.result.hidden = false;
  elements.mainModelTitle.textContent = "Request failed";
  elements.statusBadge.textContent = "error";
  elements.statusBadge.className = "status-badge invalid";
  elements.accessoryList.innerHTML = "";
  elements.accessoryCount.textContent = "0";
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = 5;
  cell.className = "quote-empty error-text";
  cell.textContent = message;
  row.appendChild(cell);
  elements.accessoryList.appendChild(row);
}

function restoreSession() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && typeof saved === "object") {
      state.currentRecommendation = saved.currentRecommendation || null;
      state.quoteItems = Array.isArray(saved.quoteItems) ? saved.quoteItems : [];
      state.candidateItems = Array.isArray(saved.candidateItems) ? saved.candidateItems : [];
      state.messages = Array.isArray(saved.messages)
        ? saved.messages
            .filter((message) => message.text !== LEGACY_WELCOME_MESSAGE)
            .map((message) => ({
              ...message,
              text: LEGACY_MESSAGE_TRANSLATIONS.get(message.text) || message.text,
            }))
        : [];
      state.history = Array.isArray(saved.history) ? saved.history : [];
      state.baseRequestText = saved.baseRequestText || "";
      state.region = normalizeRegion(saved.region);
      state.isEdited = Boolean(saved.isEdited);
    }
  } catch (error) {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function persistSession() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      currentRecommendation: state.currentRecommendation,
      quoteItems: state.quoteItems,
      candidateItems: state.candidateItems,
      messages: state.messages,
      history: state.history,
      baseRequestText: state.baseRequestText,
      region: state.region,
      isEdited: state.isEdited,
    })
  );
}

function resetSession() {
  state.currentRecommendation = null;
  state.quoteItems = [];
  state.candidateItems = [];
  state.messages = [];
  state.history = [];
  state.baseRequestText = "";
  state.region = normalizeRegion(elements.regionSelect.value);
  state.isEdited = false;
}

function cloneItems(items) {
  return items.map((item) => ({ ...item, source: { ...(item.source || {}) } }));
}

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function shortenText(value) {
  const text = String(value).trim();
  return text.length > 72 ? `${text.slice(0, 69)}...` : text;
}

function normalizeRegion(region) {
  const normalized = String(region || "").trim().toLowerCase();
  return REGION_LABELS.has(normalized) ? normalized : DEFAULT_REGION;
}

function formatRegionLabel(region) {
  return REGION_LABELS.get(normalizeRegion(region)) || REGION_LABELS.get(DEFAULT_REGION);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderProposal() {
  elements.proposalPrint.innerHTML = "";
  if (!state.quoteItems.length) {
    return;
  }

  const recommendation = state.currentRecommendation || {};
  const request = recommendation.request || {};
  const generatedAt = new Date();
  const titleBlock = document.createElement("header");
  titleBlock.className = "proposal-header";
  titleBlock.appendChild(createElement("p", "BMI Quote", "proposal-kicker"));
  titleBlock.appendChild(createElement("h1", "Quotation Proposal"));
  titleBlock.appendChild(createElement("p", "Product configuration summary", "proposal-subtitle"));

  const meta = document.createElement("dl");
  meta.className = "proposal-meta";
  appendProposalMeta(meta, "Date", generatedAt.toLocaleDateString());
  appendProposalMeta(meta, "System", request.system_family || "-");
  appendProposalMeta(meta, "Region", (request.region || "-").toUpperCase());
  appendProposalMeta(meta, "Status", state.isEdited ? "Edited" : recommendation.validation?.status || "-");

  const table = document.createElement("table");
  table.className = "proposal-table";
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const label of ["Line", "Product ID", "Qty", "Name"]) {
    headerRow.appendChild(createElement("th", label));
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  state.quoteItems.forEach((item, index) => {
    const row = document.createElement("tr");
    row.appendChild(createElement("td", String(index + 1)));
    row.appendChild(createElement("td", item.product_id || "-"));
    row.appendChild(createElement("td", formatQuantity(item.quantity)));
    row.appendChild(createElement("td", item.short_description || "Unnamed option"));
    tbody.appendChild(row);
  });
  table.appendChild(tbody);

  const footer = document.createElement("footer");
  footer.className = "proposal-footer";
  footer.textContent = "Generated by Quotation Bot.";

  elements.proposalPrint.appendChild(titleBlock);
  elements.proposalPrint.appendChild(meta);
  elements.proposalPrint.appendChild(table);
  elements.proposalPrint.appendChild(footer);
}

function appendProposalMeta(meta, label, value) {
  const wrapper = document.createElement("div");
  wrapper.appendChild(createElement("dt", label));
  wrapper.appendChild(createElement("dd", value));
  meta.appendChild(wrapper);
}

function downloadProposalPdf() {
  const pdfContent = createProposalPdf();
  const blob = new Blob([pdfContent], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = createProposalFileName();
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function createProposalFileName() {
  const recommendation = state.currentRecommendation || {};
  const request = recommendation.request || {};
  const system = sanitizeFileName(request.system_family || "quotation");
  const dateStamp = new Date().toISOString().slice(0, 10).replaceAll("-", "");
  return `Quotation_Proposal_${system}_${dateStamp}.pdf`;
}

function sanitizeFileName(value) {
  return String(value).replace(/[^a-z0-9_-]+/gi, "_").replace(/^_+|_+$/g, "") || "quotation";
}

function createProposalPdf() {
  const pageWidth = 612;
  const pageHeight = 792;
  const margin = 42;
  const bottomMargin = 56;
  const columns = { line: 46, product: 86, qty: 172, name: 218 };
  const objects = [];
  const pageStreams = [];
  let commands = [];
  let cursorY = pageHeight - margin;

  function beginPage(isFirstPage) {
    commands = [];
    cursorY = pageHeight - margin;
    if (isFirstPage) {
      addText("BMI Quote", margin, cursorY, 10, "0.14 0.36 0.56");
      cursorY -= 24;
      addText("Quotation Proposal", margin, cursorY, 22, "0.09 0.13 0.18");
      cursorY -= 18;
      addText("Product configuration summary", margin, cursorY, 11, "0.29 0.33 0.39");
      cursorY -= 18;
      addLine(margin, cursorY, pageWidth - margin, cursorY, "0.12 0.16 0.22", 1.4);
      cursorY -= 28;
      addProposalMetaText();
      cursorY -= 34;
    } else {
      addText("Quotation Proposal (continued)", margin, cursorY, 15, "0.09 0.13 0.18");
      cursorY -= 26;
    }
    addPdfTableHeader();
  }

  function finishPage() {
    addLine(margin, 42, pageWidth - margin, 42, "0.61 0.64 0.69", 0.6);
    addText("Generated by Quotation Bot.", margin, 28, 8, "0.29 0.33 0.39");
    pageStreams.push(commands.join("\n"));
  }

  function addProposalMetaText() {
    const recommendation = state.currentRecommendation || {};
    const request = recommendation.request || {};
    const meta = [
      ["Date", new Date().toLocaleDateString()],
      ["System", request.system_family || "-"],
      ["Region", (request.region || "-").toUpperCase()],
      ["Status", state.isEdited ? "Edited" : recommendation.validation?.status || "-"],
    ];
    const metaWidth = (pageWidth - margin * 2) / meta.length;
    meta.forEach(([label, value], index) => {
      const x = margin + index * metaWidth;
      addFilledRect(x, cursorY - 2, metaWidth, 18, "0.93 0.95 0.97");
      addRect(x, cursorY - 20, metaWidth, 38, "0.61 0.64 0.69", 0.5);
      addText(label.toUpperCase(), x + 6, cursorY + 4, 7, "0.22 0.25 0.32");
      addText(value, x + 6, cursorY - 12, 9, "0.09 0.13 0.18");
    });
  }

  function addPdfTableHeader() {
    addFilledRect(margin, cursorY - 15, pageWidth - margin * 2, 20, "0.09 0.20 0.30");
    addText("Line", columns.line, cursorY - 9, 8, "1 1 1");
    addText("Product ID", columns.product, cursorY - 9, 8, "1 1 1");
    addText("Qty", columns.qty, cursorY - 9, 8, "1 1 1");
    addText("Name", columns.name, cursorY - 9, 8, "1 1 1");
    cursorY -= 28;
  }

  function addQuoteRow(item, index) {
    const wrappedName = wrapPdfText(item.short_description || "Unnamed option", 68);
    const rowHeight = Math.max(18, wrappedName.length * 11 + 8);
    if (cursorY - rowHeight < bottomMargin) {
      finishPage();
      beginPage(false);
    }
    addLine(margin, cursorY + 5, pageWidth - margin, cursorY + 5, "0.82 0.85 0.89", 0.4);
    addText(String(index + 1), columns.line + 8, cursorY - 7, 8.5, "0.09 0.13 0.18");
    addText(item.product_id || "-", columns.product, cursorY - 7, 8.5, "0.09 0.13 0.18");
    addText(formatQuantity(item.quantity), columns.qty + 6, cursorY - 7, 8.5, "0.09 0.13 0.18");
    wrappedName.forEach((line, lineIndex) => {
      addText(line, columns.name, cursorY - 7 - lineIndex * 11, 8.5, "0.09 0.13 0.18");
    });
    cursorY -= rowHeight;
  }

  function addText(text, x, y, size, color) {
    commands.push(`${color} rg BT /F1 ${size} Tf ${x} ${y} Td (${escapePdfText(text)}) Tj ET`);
  }

  function addLine(x1, y1, x2, y2, color, width) {
    commands.push(`${color} RG ${width} w ${x1} ${y1} m ${x2} ${y2} l S`);
  }

  function addRect(x, y, width, height, color, strokeWidth) {
    commands.push(`${color} RG ${strokeWidth} w ${x} ${y} ${width} ${height} re S`);
  }

  function addFilledRect(x, y, width, height, color) {
    commands.push(`${color} rg ${x} ${y} ${width} ${height} re f`);
  }

  beginPage(true);
  state.quoteItems.forEach(addQuoteRow);
  finishPage();

  objects[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";
  const pageRefs = [];
  pageStreams.forEach((stream, index) => {
    const pageObjectNumber = 4 + index * 2;
    const streamObjectNumber = pageObjectNumber + 1;
    pageRefs.push(`${pageObjectNumber} 0 R`);
    objects[pageObjectNumber] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${streamObjectNumber} 0 R >>`;
    objects[streamObjectNumber] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
  });
  objects[2] = `<< /Type /Pages /Kids [${pageRefs.join(" ")}] /Count ${pageRefs.length} >>`;

  return assemblePdf(objects);
}

function wrapPdfText(value, maxLength) {
  const words = sanitizePdfText(value).split(/\s+/).filter(Boolean);
  const lines = [];
  let currentLine = "";
  for (const word of words) {
    if (word.length > maxLength) {
      if (currentLine) {
        lines.push(currentLine);
        currentLine = "";
      }
      for (let index = 0; index < word.length; index += maxLength) {
        lines.push(word.slice(index, index + maxLength));
      }
      continue;
    }
    const candidate = currentLine ? `${currentLine} ${word}` : word;
    if (candidate.length > maxLength) {
      lines.push(currentLine);
      currentLine = word;
    } else {
      currentLine = candidate;
    }
  }
  if (currentLine) {
    lines.push(currentLine);
  }
  return lines.length ? lines : ["-"];
}

function assemblePdf(objects) {
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (let index = 1; index < objects.length; index += 1) {
    offsets[index] = pdf.length;
    pdf += `${index} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n`;
  for (let index = 1; index < objects.length; index += 1) {
    pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return pdf;
}

function escapePdfText(value) {
  return sanitizePdfText(value).replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}

function sanitizePdfText(value) {
  return String(value).replace(/[^\x20-\x7E]/g, "?");
}