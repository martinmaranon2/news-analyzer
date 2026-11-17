// The page's logic: call our JSON API with fetch() and fill in the HTML. No framework, no build step.

const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#search-input");
const searchStatus = document.querySelector("#search-status");
const resultsSection = document.querySelector("#results-section");
const resultsList = document.querySelector("#results");
const analyzeAllButton = document.querySelector("#analyze-all");
const sentimentBar = document.querySelector(".sentiment-bar");
const sentimentSummary = document.querySelector("#sentiment-summary");
const savedList = document.querySelector("#saved");
const savedStatus = document.querySelector("#saved-status");
const sentimentFilter = document.querySelector("#sentiment-filter");
const cardTemplate = document.querySelector("#card-template");

let shownResults = []; // the current search: one { article, card } per result

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
  shownResults = results.map(({ article, analysis }) => ({ article, card: createCard(article, analysis) }));
  resultsList.replaceChildren(...shownResults.map((result) => result.card));
  searchStatus.textContent = results.length > 0 ? "" : `No recent articles found for “${query}”. Try a broader term.`;
  resultsSection.hidden = results.length === 0;
  updateSentimentBar();
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
  card.querySelector(".analyze").addEventListener("click", async () => {
    await analyzeCard(card, article);
    loadSaved();
  });
  if (analysis) showAnalysis(card, analysis);
  return card;
}

function showAnalysis(card, analysis) {
  card.dataset.sentiment = analysis.sentiment; // the CSS colours the card by it; the bar counts it
  const score = analysis.sentiment_score;
  card.querySelector(".badge").textContent =
    `${capitalize(analysis.sentiment)} for ${analysis.subject} (${score > 0 ? "+" : ""}${score.toFixed(1)})`;
  card.querySelector(".analysis-reason").textContent = analysis.reason;
  card.querySelector(".analysis-summary").textContent = analysis.summary;
  card.querySelector(".analysis-source").textContent = analysis.text_source === "full_text"
    ? "Based on the full article."
    : "Based on the headline and snippet only: the full article couldn't be downloaded.";
  card.querySelector(".card-description").hidden = true;
  card.querySelector(".analysis").hidden = false;
  card.querySelector(".analyze").hidden = true;
}

async function analyzeCard(card, article) {
  const button = card.querySelector(".analyze");
  const error = card.querySelector(".card-error");
  button.disabled = true; // also stops a double click from analysing the same article twice
  button.textContent = "Analyzing…";
  error.hidden = true;
  try {
    const analysis = await callApi("/api/analyses", {
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
  button.disabled = false;
  updateSentimentBar();
}

// ---- Analyze all + sentiment bar ----

analyzeAllButton.addEventListener("click", async () => {
  analyzeAllButton.disabled = true;
  const pending = shownResults.filter(({ card }) => !card.dataset.sentiment && !card.querySelector(".analyze").disabled);
  await Promise.all(pending.map(({ article, card }) => analyzeCard(card, article))); // all at once, in parallel
  analyzeAllButton.disabled = false;
  loadSaved();
});

// Count the results per sentiment; each part of the bar grows with its count (grey = not analysed yet).
function updateSentimentBar() {
  const counts = { positive: 0, neutral: 0, negative: 0 };
  for (const { card } of shownResults) {
    if (card.dataset.sentiment) counts[card.dataset.sentiment] += 1;
  }
  const analysed = counts.positive + counts.neutral + counts.negative;
  for (const [part, count] of Object.entries({ ...counts, pending: shownResults.length - analysed })) {
    sentimentBar.querySelector(`.${part}`).style.flexGrow = count;
  }
  sentimentSummary.textContent = `${analysed} of ${shownResults.length} analysed · ` +
    `${counts.positive} positive · ${counts.neutral} neutral · ${counts.negative} negative`;
  analyzeAllButton.hidden = analysed === shownResults.length;
}

// ---- Saved analyses ----

async function loadSaved() {
  const sentiment = sentimentFilter.value;
  const path = sentiment ? `/api/analyses?sentiment=${sentiment}` : "/api/analyses";
  try {
    const analyses = await callApi(path);
    savedList.replaceChildren(...analyses.map((analysis) => createCard(analysis, analysis)));
    savedStatus.textContent = analyses.length > 0 ? ""
      : sentiment ? `No ${sentiment} analyses yet.`
      : "No analyses yet. Search for a company or topic and click Analyze.";
  } catch {
    savedStatus.textContent = "Couldn't load the saved analyses. Please reload the page.";
  }
}

sentimentFilter.addEventListener("change", loadSaved);

// ---- Small helpers ----

function formatDate(isoText) {
  return new Date(isoText).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function capitalize(text) {
  return text[0].toUpperCase() + text.slice(1);
}

loadSaved(); // show the saved analyses as soon as the page opens
