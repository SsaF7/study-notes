"use strict";

const get = (id) => document.getElementById(id);
const query = get("query");
const subject = get("subject");
const status = get("status");
const results = get("results");
const collator = new Intl.Collator("ru");
let catalog;
let indexPromise;
let renderVersion = 0;

function normalize(value) {
  return value.toLowerCase().replaceAll("ё", "е");
}

async function readJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${path}`);
  return response.json();
}

function libraryParams() {
  const params = new URLSearchParams();
  if (query.value.trim()) params.set("q", query.value.trim());
  if (subject.value) params.set("subject", subject.value);
  return params;
}

function href(params) {
  return params.size ? `?${params}` : "./";
}

function noteHref(slug, anchor) {
  const params = libraryParams();
  params.set("note", slug);
  if (anchor) params.set("section", anchor);
  return href(params);
}

function findNote(note, sections, terms) {
  const title = normalize(note.title);
  let best = terms.every((term) => title.includes(term))
    ? { score: 5 * terms.length, section: null }
    : null;
  for (const section of sections) {
    const heading = normalize(section.heading);
    const body = normalize(section.text);
    let score = 0;
    for (const term of terms) {
      const weight = (title.includes(term) ? 5 : 0) +
        (heading.includes(term) ? 3 : 0) + (body.includes(term) ? 1 : 0);
      if (!weight) {
        score = 0;
        break;
      }
      score += weight;
    }
    if (score && (!best || score > best.score)) best = { score, section };
  }
  return best && { ...note, ...best, preview: best.section ?? sections.find((section) => section.text) };
}

function excerpt(section, terms) {
  const body = normalize(section.text);
  const matches = terms.map((term) => body.indexOf(term)).filter((position) => position >= 0);
  const start = matches.length ? Math.max(0, Math.min(...matches) - 35) : 0;
  const end = Math.min(section.text.length, start + 155);
  const text = section.text.slice(start, end).trim();
  return [section.heading, text && `${start ? "…" : ""}${text}${end < section.text.length ? "…" : ""}`]
    .filter(Boolean).join(" · ");
}

function span(className, text) {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = text;
  return element;
}

function resultRow(note, terms) {
  const row = document.createElement("li");
  row.className = "result";
  const link = document.createElement("a");
  link.href = noteHref(note.slug, note.section?.anchor);
  const details = document.createElement("div");
  details.append(span("result-title", note.title), span("subject", note.subject));
  if (note.preview) details.append(span("excerpt", excerpt(note.preview, terms)));
  const arrow = span("arrow", "›");
  arrow.setAttribute("aria-hidden", "true");
  link.append(details, arrow);
  row.append(link);
  return row;
}

async function renderCatalog(updateURL = true) {
  const version = ++renderVersion;
  if (updateURL) history.replaceState(null, "", href(libraryParams()));
  const terms = [...new Set(normalize(query.value).match(/[\p{L}\p{N}]+/gu) ?? [])];
  let notes = catalog.filter((note) => !subject.value || note.subject === subject.value);
  if (terms.length) {
    results.replaceChildren();
    status.textContent = "Ищем по конспектам…";
    indexPromise ??= readJSON("search.json").catch((error) => {
      indexPromise = undefined;
      throw error;
    });
    try {
      const index = await indexPromise;
      if (version !== renderVersion) return;
      notes = notes.map((note) => findNote(note, index[note.slug] ?? [], terms))
        .filter(Boolean).sort((a, b) => b.score - a.score);
    } catch {
      if (version === renderVersion) status.textContent = "Поиск недоступен. Обнови страницу и попробуй снова.";
      return;
    }
  }
  status.textContent = notes.length ? `Найдено: ${notes.length}` : "Ничего не найдено";
  results.replaceChildren(...notes.map((note) => resultRow(note, terms)));
}

function showReader(note, anchor) {
  const position = catalog.indexOf(note);
  document.body.classList.add("reader-mode");
  get("library").hidden = true;
  get("reader").hidden = false;
  get("back-link").href = href(libraryParams());
  get("reader-title").textContent = note.title;
  document.title = `${note.title} | Конспекты`;
  for (const [id, neighbor] of [["previous", catalog[position - 1]], ["next", catalog[position + 1]]]) {
    if (!neighbor) continue;
    const link = get(id);
    link.href = noteHref(neighbor.slug);
    link.title = neighbor.title;
    link.hidden = false;
  }
  const frame = get("note-frame");
  frame.title = note.title;
  frame.src = `notes/${encodeURIComponent(note.slug)}/index.html${anchor ? "#" + encodeURIComponent(anchor) : ""}`;
}

async function init() {
  catalog = await readJSON("catalog.json");
  catalog.sort((a, b) => collator.compare(a.subject, b.subject) || collator.compare(a.title, b.title));
  for (const name of new Set(catalog.map((note) => note.subject))) subject.add(new Option(name, name));
  const params = new URLSearchParams(location.search);
  query.value = params.get("q") ?? "";
  const selected = params.get("subject");
  if (Array.from(subject.options).some((option) => option.value === selected)) subject.value = selected;
  const slug = params.get("note");
  const note = catalog.find((entry) => entry.slug === slug);
  if (note) {
    showReader(note, params.get("section"));
    return;
  }
  const form = get("filters");
  form.addEventListener("input", () => renderCatalog());
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    renderCatalog();
  });
  await renderCatalog(false);
  if (slug) status.textContent = "Конспект не найден. Выбери другой из каталога.";
}

init().catch(() => {
  status.textContent = "Каталог не загрузился. Обнови страницу и попробуй снова.";
});
