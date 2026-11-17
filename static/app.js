// The page's logic: call our JSON API with fetch() and fill in the HTML. No framework, no build step.

const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");
const searchStatus = document.querySelector("#search-status");
const resultsSection = document.querySelector("#results-section");
const resultsHeading = document.querySelector("#results-heading");
const resultsList = document.querySelector("#results");
const analyzeAllButton = document.querySelector("#analyze-all");
const verdict = document.querySelector("#verdict");
const sentimentBar = document.querySelector(".sentiment-bar");
const sentimentLegend = document.querySelector(".legend");
const savedList = document.querySelector("#saved");
const savedStatus = document.querySelector("#saved-status");
const showAllSavedButton = document.querySelector("#show-all-saved");
const sentimentFilter = document.querySelector("#sentiment-filter");
const topicFilter = document.querySelector("#topic-filter");
const briefingPanel = document.querySelector("#briefing-panel");
const briefButton = document.querySelector("#brief-button");
const briefingError = document.querySelector("#briefing-error");
const briefing = document.querySelector("#briefing");
const cardTemplate = document.querySelector("#card-template");
const savedTemplate = document.querySelector("#saved-template");

const SAVED_PREVIEW_COUNT = 5; // the saved list shows the newest 5 until "Show all" is clicked

let shownResults = []; // the current search: one { article, card } per result
let shownTopic = ""; // the search those results came from: saved as the topic of each analysis
let showAllSaved = false;
let topicCounts = new Map(); // topic → how many saved analyses it has (filled by loadTopics)
const briefings = new Map(); // topic → its last briefing, kept while the page is open

// Call our API and return the parsed JSON. On an error status, log the server's detail for
// developers and throw, so the caller can show the user a friendly message instead.
async function callApi(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    console.error(`${options.method ?? "GET"} ${path} failed with ${response.status}:`, body.detail);
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

// ---- Search ----

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault(); // stop the browser from reloading the page: we fetch the results ourselves
  const query = searchInput.value.trim();
  if (!query) return;
  searchStatus.textContent = `Searching for “${query}”…`;
  resultsSection.hidden = true;
  try {
    const results = await callApi(`/api/articles?q=${encodeURIComponent(query)}`);
    showResults(query, results);
  } catch {
    searchStatus.textContent = "The news search failed. Please try again in a minute.";
  }
});

function showResults(query, results) {
  shownTopic = query;
  shownResults = results.map(({ article, analysis }) => ({ article, card: createCard(article, analysis) }));
  resultsList.replaceChildren(...shownResults.map((result) => result.card));
  resultsHeading.textContent = `News on “${query}”`;
  searchStatus.textContent = results.length > 0 ? "" : `No recent articles found for “${query}”. Try a broader term.`;
  resultsSection.hidden = results.length === 0;
  updateVerdict();
}

// ---- Cards ----

// Copy the <template> card and fill it in. textContent (never innerHTML) shows titles and AI text
// as plain text, so a title that contains HTML can't run code in the page (XSS).
function createCard(article, analysis) {
  const card = cardTemplate.content.firstElementChild.cloneNode(true);
  const title = card.querySelector(".card-title");
  title.textContent = article.title;
  title.href = article.url; // safe: the API only accepts http(s) URLs
  card.querySelector(".card-meta").textContent = `${article.source} · ${formatDate(article.published_at)}`;
  card.querySelector(".card-description").textContent = article.description ?? "";
  const button = card.querySelector(".analyze");
  button.ariaLabel = `Analyze: ${article.title}`; // a screen reader hears which article, not ten times "Analyze"
  button.addEventListener("click", async () => {
    await analyzeCard(card, article);
    loadSaved();
  });
  if (analysis) showAnalysis(card, analysis);
  return card;
}

// Fill in the AI's verdict, reason, summary and evidence. Used by the result cards and the saved rows.
function fillAnalysis(element, analysis) {
  element.dataset.sentiment = analysis.sentiment; // the CSS colours the label by it; the bar counts it
  const score = analysis.sentiment_score;
  element.querySelector(".badge").textContent =
    `${capitalize(analysis.sentiment)} for ${analysis.subject} (${score > 0 ? "+" : ""}${score.toFixed(1)})`;
  element.querySelector(".analysis-reason").textContent = analysis.reason;
  element.querySelector(".analysis-summary").textContent = analysis.summary;
  const provenance = element.querySelector(".provenance");
  provenance.dataset.source = analysis.text_source; // the CSS gives "snippet" a caution colour
  provenance.textContent = analysis.text_source === "full_text"
    ? "Based on the full article"
    : "Based on the headline and snippet only: the full article couldn't be downloaded";
}

function showAnalysis(card, analysis) {
  fillAnalysis(card, analysis);
  card.querySelector(".card-description").hidden = true;
  card.querySelector(".analysis").hidden = false;
  card.querySelector(".analyze").hidden = true;
}

async function analyzeCard(card, article) {
  const button = card.querySelector(".analyze");
  const error = card.querySelector(".card-error");
  button.disabled = true; // also stops a double click from analysing the same article twice
  button.textContent = "Analyzing… usually 3–10 s";
  card.ariaBusy = "true"; // the CSS shows a moving line on busy cards
  error.hidden = true;
  try {
    const analysis = await callApi(`/api/analyses?topic=${encodeURIComponent(shownTopic)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(article),
    });
    showAnalysis(card, analysis);
  } catch {
    error.textContent = "Couldn't analyse this article. Please try again.";
    error.hidden = false;
    button.textContent = "Try again";
  }
  card.ariaBusy = "false";
  button.disabled = false;
  updateVerdict();
}

// ---- Analyze all + verdict ----

analyzeAllButton.addEventListener("click", async () => {
  analyzeAllButton.disabled = true;
  const pending = shownResults.filter(({ card }) => !card.dataset.sentiment && !card.querySelector(".analyze").disabled);
  updateVerdict(); // the disabled button now counts down: "Analyzing… 8 left"
  await Promise.all(pending.map(({ article, card }) => analyzeCard(card, article))); // all at once, in parallel
  analyzeAllButton.disabled = false;
  updateVerdict();
  loadSaved();
});

// Count the results per sentiment, then update the headline, the bar (grey = not analysed yet),
// the legend and the Analyze all button.
function updateVerdict() {
  const counts = { positive: 0, neutral: 0, negative: 0 };
  for (const { card } of shownResults) {
    if (card.dataset.sentiment) counts[card.dataset.sentiment] += 1;
  }
  const analysed = counts.positive + counts.neutral + counts.negative;
  const remaining = shownResults.length - analysed;
  for (const [part, count] of Object.entries({ ...counts, pending: remaining })) {
    sentimentBar.querySelector(`.${part}`).style.flexGrow = count; // each part grows with its count
    sentimentLegend.querySelector(`.${part} .count`).textContent = count;
  }
  verdict.textContent = `${verdictHeadline(counts, analysed)} · ${analysed} of ${shownResults.length} analysed`;
  analyzeAllButton.textContent = analyzeAllButton.disabled ? `Analyzing… ${remaining} left` : `Analyze all (${remaining})`;
  analyzeAllButton.hidden = remaining === 0;
}

// "Mostly negative" if one sentiment has more than half of the analysed results, otherwise "Mixed".
function verdictHeadline(counts, analysed) {
  if (analysed === 0) return "No verdict yet";
  const [sentiment, count] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return count > analysed / 2 ? `Mostly ${sentiment}` : "Mixed";
}

// ---- Saved analyses ----

async function loadSaved() {
  loadTopics(); // a new analysis may have added a topic
  const filters = new URLSearchParams(); // builds "sentiment=negative&topic=nvidia", escaping each value
  if (sentimentFilter.value) filters.set("sentiment", sentimentFilter.value);
  if (topicFilter.value) filters.set("topic", topicFilter.value);
  try {
    const analyses = await callApi(`/api/analyses?${filters}`);
    const shown = showAllSaved ? analyses : analyses.slice(0, SAVED_PREVIEW_COUNT);
    savedList.replaceChildren(...shown.map(createSavedRow));
    showAllSavedButton.textContent = `Show all ${analyses.length}`;
    showAllSavedButton.hidden = shown.length === analyses.length;
    savedStatus.textContent = analyses.length > 0 ? ""
      : filters.size > 0 ? "No saved analyses match these filters."
      : "No analyses yet. Search for a company or topic and click Analyze.";
  } catch {
    savedStatus.textContent = "Couldn't load the saved analyses. Please reload the page.";
  }
}

// One saved analysis as a compact row: label, title and date; clicking it opens the reason and summary.
function createSavedRow(analysis) {
  const row = savedTemplate.content.firstElementChild.cloneNode(true);
  row.querySelector(".saved-title").textContent = analysis.title;
  row.querySelector(".saved-date").textContent = formatDate(analysis.published_at);
  row.querySelector(".saved-source").textContent = analysis.source;
  row.querySelector(".saved-link").href = analysis.url; // safe: the API only accepts http(s) URLs
  fillAnalysis(row, analysis);
  return row;
}

// Fill the topic dropdown with every search that has saved analyses ("nvidia (7)"), keeping the current choice.
async function loadTopics() {
  try {
    const topics = await callApi("/api/topics");
    topicCounts = new Map(topics.map(({ topic, count }) => [topic, count]));
    const chosen = topicFilter.value;
    const options = topics.map(({ topic, count }) => new Option(`${topic} (${count})`, topic)); // Option(text, value)
    topicFilter.replaceChildren(new Option("all topics", ""), ...options);
    topicFilter.value = topicCounts.has(chosen) ? chosen : "";
    updateBriefingPanel(); // a new analysis may have raised the chosen topic's count
  } catch {
    // keep the dropdown as it is; the saved list shows its own error message
  }
}

sentimentFilter.addEventListener("change", loadSaved);
topicFilter.addEventListener("change", loadSaved);
showAllSavedButton.addEventListener("click", () => {
  showAllSaved = true;
  loadSaved();
});

// ---- Topic briefing ----

// Show the panel while one topic is chosen, with that topic's last briefing if there is one. The button is
// off while that briefing already covers every saved analysis of the topic: briefing it again would cost an
// AI call and say the same. A new analysis of the topic raises its count and turns the button back on.
function updateBriefingPanel() {
  const topic = topicFilter.value;
  const last = briefings.get(topic);
  briefingPanel.hidden = !topic;
  if (last) showBriefing(last);
  else briefing.hidden = true;
  if (briefingPanel.ariaBusy === "true") return; // the click handler is using the button
  const upToDate = last !== undefined && last.analysis_count === topicCounts.get(topic);
  briefButton.disabled = upToDate;
  briefButton.textContent = upToDate ? `Briefed on all ${last.analysis_count} analyses` : `Brief me on “${topic}”`;
}

briefButton.addEventListener("click", async () => {
  const topic = topicFilter.value;
  briefButton.disabled = true;
  briefButton.textContent = "Writing the briefing";
  briefingPanel.ariaBusy = "true"; // the CSS sweeps a line under the button and adds filling dots
  briefingError.hidden = true;
  try {
    const result = await callApi("/api/briefings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    briefings.set(topic, result);
  } catch {
    briefingError.textContent = "Couldn't write the briefing. Please try again.";
    briefingError.hidden = false;
  }
  briefingPanel.ariaBusy = "false";
  updateBriefingPanel(); // shows the new briefing; the button stays off until the topic gets a new analysis
});

function showBriefing(result) {
  briefing.dataset.sentiment = result.verdict; // the CSS colours the badge by it, "mixed" included
  briefing.querySelector(".badge").textContent = `${capitalize(result.verdict)} overall`;
  briefing.querySelector(".briefing-headline").textContent = result.headline;
  briefing.querySelector(".briefing-text").textContent = result.briefing;
  briefing.querySelector(".note").textContent =
    `Based on all ${result.analysis_count} saved analyses of “${result.topic}”, whatever the Show filter says.`;
  briefing.hidden = false;
}

topicFilter.addEventListener("change", () => {
  briefingError.hidden = true; // an error was about the previous topic
  updateBriefingPanel();
});

// ---- Small helpers ----

function formatDate(isoText) {
  return new Date(isoText).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function capitalize(text) {
  return text[0].toUpperCase() + text.slice(1);
}

loadSaved(); // show the saved analyses as soon as the page opens
