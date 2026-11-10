const catalogs = /*CATALOGS*/ {};

/* ───────────────────────── Localization ───────────────────────── */

let activeLocale = "en";
function t(key, vars) {
  let text =
    catalogs[activeLocale]?.[key] ??
    catalogs[activeLocale.split("-")[0]]?.[key] ??
    catalogs.en?.[key] ??
    key;
  if (vars)
    text = text.replace(/\{(\w+)\}/g, (match, name) =>
      name in vars ? vars[name] : match,
    );
  return text;
}
function plural(count, one, other, vars = {}) {
  let rule = "other";
  try {
    rule = new Intl.PluralRules(activeLocale).select(count);
  } catch {
    rule = count === 1 ? "one" : "other";
  }
  return t(rule === "one" ? one : other, { count, ...vars });
}
function safeLocale(value) {
  try {
    return Intl.getCanonicalLocales(value || "en")[0] || "en";
  } catch {
    return "en";
  }
}

/* ───────────────────────── Utilities ───────────────────────── */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const reducedMotion = () =>
  !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
function animateIn(el) {
  if (!el?.animate || reducedMotion()) return;
  el.animate(
    [
      { opacity: 0, transform: "translateY(6px)" },
      { opacity: 1, transform: "none" },
    ],
    { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" },
  );
}

const ICONS = {
  mark: '<path d="M7.5 4.5c-2.2 2.6-2.7 6.4-1 9.6 1.3 2.4 3.4 3.9 5.5 4.4M16.5 4.5c2.2 2.6 2.7 6.4 1 9.6-1.3 2.4-3.4 3.9-5.5 4.4"/><path d="M9.5 8v8M12 7v10M14.5 8v8"/><circle cx="12" cy="3.6" r="1.1" fill="currentColor" stroke="none"/><circle cx="6.4" cy="4.2" r=".8" fill="currentColor" stroke="none"/><circle cx="17.6" cy="4.2" r=".8" fill="currentColor" stroke="none"/>',
  home: '<path d="M3.5 9 10 3.8 16.5 9v7a1 1 0 0 1-1 1H12v-5H8v5H4.5a1 1 0 0 1-1-1z"/>',
  tv: '<rect x="2.8" y="4.5" width="14.4" height="10" rx="2"/><path d="M7 17.5h6"/>',
  film: '<rect x="3.5" y="3.5" width="13" height="13" rx="2"/><path d="M7 3.5v13M13 3.5v13M3.5 7.5H7M3.5 12.5H7M13 7.5h3.5M13 12.5h3.5"/>',
  compass: '<circle cx="10" cy="10" r="7"/><path d="m12.8 7.2-1.6 4-4 1.6 1.6-4z"/>',
  history: '<path d="M3.8 10a6.2 6.2 0 1 0 1.8-4.4L3.8 7.4"/><path d="M3.8 3.8v3.6h3.6M10 6.8V10l2.3 1.5"/>',
  gear: '<path d="M4 6h7M15 6h1M4 10h2M10 10h6M4 14h8M16 14h0"/><circle cx="13" cy="6" r="1.8"/><circle cx="8" cy="10" r="1.8"/><circle cx="14" cy="14" r="1.8"/>',
  search: '<circle cx="9" cy="9" r="5.5"/><path d="m13 13 3.5 3.5"/>',
  menu: '<path d="M3.5 6h13M3.5 10h13M3.5 14h13"/>',
  check: '<path d="m5 10.5 3.2 3.2L15 6.5"/>',
  plus: '<path d="M10 4v12M4 10h12"/>',
  more: '<circle cx="5" cy="10" r="1.2" fill="currentColor"/><circle cx="10" cy="10" r="1.2" fill="currentColor"/><circle cx="15" cy="10" r="1.2" fill="currentColor"/>',
  back: '<path d="m11.5 4.5-5.5 5.5 5.5 5.5"/>',
  refresh: '<path d="M15.5 8A6 6 0 0 0 4.7 6.3M4.5 12a6 6 0 0 0 10.8 1.7"/><path d="M15.7 3.6V8h-4.4M4.3 16.4V12h4.4"/>',
  trash: '<path d="M4.5 6h11M8 6V4.5h4V6M6 6l.7 10h6.6L14 6"/>',
  calendar: '<rect x="3.5" y="4.5" width="13" height="12" rx="2"/><path d="M3.5 8.5h13M7 3v3M13 3v3"/>',
  x: '<path d="m5 5 10 10M15 5 5 15"/>',
  key: '<circle cx="7" cy="12.5" r="3"/><path d="M9.2 10.3 16 3.5M13.5 6l2 2M11.8 7.7l1.6 1.6"/>',
  alert: '<path d="M10 3.5 17 16H3z"/><path d="M10 8.5v3.5M10 14h.01"/>',
  clock: '<circle cx="10" cy="10" r="7"/><path d="M10 6.2V10l2.6 1.7"/>',
  open: '<path d="M11 4h5v5M16 4l-7 7M14 11.5V15a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h3.5"/>',
  sparkle: '<path d="M10 3c.4 3.5 1.9 5 5.5 5.5-3.6.5-5.1 2-5.5 5.5-.4-3.5-1.9-5-5.5-5.5C8.1 8 9.6 6.5 10 3z"/>',
};
function icon(name, className = "") {
  const box = name === "mark" ? "0 0 24 24" : "0 0 20 20";
  return `<svg class="i ${className}" viewBox="${box}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] || ""}</svg>`;
}

/* ───────────────────────── Nexus bridge ───────────────────────── */

let serial = 0;
const pending = new Map();
window.addEventListener("message", (event) => {
  if (event.source !== parent || event.data?.channel !== "empyrean-v1") return;
  const request = pending.get(event.data.id);
  if (!request) return;
  clearTimeout(request.timer);
  pending.delete(event.data.id);
  event.data.error ? request.reject(Error(event.data.error)) : request.resolve(event.data.result);
});
function bridge(action, data = {}) {
  return new Promise((resolve, reject) => {
    const id = String(++serial);
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(Error(t("Nexus did not respond. Try again in a moment.")));
    }, 20000);
    pending.set(id, { resolve, reject, timer });
    parent.postMessage({ channel: "empyrean-v1", id, action, ...data }, "*");
  });
}
const rawApi = (path, method = "GET", body) =>
  bridge("request", { path: "/api" + path, method, ...(body === undefined ? {} : { body }) });
const api = (path, method = "GET", body, snapshot) => personalRequest(path, method, body, snapshot);

/* ───────────────────────── State and formatting ───────────────────────── */

const state = {
  context: { applications: [], locale: "en" },
  app: null,
  route: { view: "home" },
  history: [],
  query: "",
  filter: { series: "all", movie: "all" },
  images: new Map(),
};
const SERIES_STATUS = ["watching", "planned", "on_hold", "completed", "dropped"];
const MOVIE_STATUS = ["planned", "watched"];
const statusLabel = (status, type) =>
  ({
    watching: t("Watching"),
    planned: type === "movie" ? t("Watchlist") : t("Plan to watch"),
    on_hold: t("On hold"),
    completed: t("Completed"),
    dropped: t("Dropped"),
    watched: t("Watched"),
  })[status] || status;
const todayIso = () => new Date().toISOString().slice(0, 10);
function fmtDate(iso, options = { day: "numeric", month: "short", year: "numeric" }) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat(activeLocale, { timeZone: "UTC", ...options }).format(new Date(Date.UTC(y, m - 1, d)));
}
function fmtWhen(instant) {
  return new Intl.DateTimeFormat(activeLocale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(instant));
}
function relativeDay(iso) {
  const days = Math.round((Date.parse(iso.slice(0, 10)) - Date.parse(todayIso())) / 86400000);
  try {
    return new Intl.RelativeTimeFormat(activeLocale, { numeric: "auto" }).format(days, "day");
  } catch {
    return fmtDate(iso);
  }
}
function whenLabel(iso) {
  const days = Math.round((Date.parse(iso.slice(0, 10)) - Date.parse(todayIso())) / 86400000);
  return Math.abs(days) <= 6 ? relativeDay(iso) : fmtDate(iso, { weekday: "short", day: "numeric", month: "short" });
}
const episodeCode = (e) => `S${e.season ?? e.season_number}E${e.number ?? e.episode_number}`;
const initial = (title) => [...(title || "?").trim()][0]?.toUpperCase() || "?";

function toast(message, tone = "", action) {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = `ae-toast ae-glass ${tone === "danger" ? "ae-toast--danger" : ""}`;
  el.innerHTML = `<span>${esc(message)}</span>${action ? `<button class="ae-btn ae-btn--sm" data-toast-act>${esc(action.label)}</button>` : ""}<button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-toast-close aria-label="${esc(t("Dismiss"))}">${icon("x")}</button>`;
  el.querySelector("[data-toast-close]").onclick = () => el.remove();
  if (action)
    el.querySelector("[data-toast-act]").onclick = () => {
      el.remove();
      action.run();
    };
  box.append(el);
  setTimeout(() => el.remove(), action ? 9000 : tone === "danger" ? 9000 : 4000);
}
async function attempt(work, success) {
  try {
    const result = await work();
    if (success) toast(success);
    return result;
  } catch (error) {
    toast(error.message || t("Something went wrong."), "danger");
    return undefined;
  }
}

/* Images arrive from Lyra as data URIs: the sandbox cannot load remote images. */
let imageTimer;
function hue(text) {
  let h = 0;
  for (const ch of text || "") h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
}
function art(key, title, className = "poster") {
  const cached = key && state.images.get(key);
  const image = cached ? `background-image:url('${cached}');` : "";
  return `<div class="art ${className}${cached ? " loaded" : ""}" ${key ? `data-img="${esc(key)}"` : ""} style="${image}--h:${hue(title)}" role="img" aria-label="${esc(title)}"><span class="art-fallback" aria-hidden="true"><span class="art-orbit"></span><span class="art-title">${esc(title)}</span></span></div>`;
}
function hydrateImages(allowRemote = false) {
  clearTimeout(imageTimer);
  const token = render.token;
  const intent = externalRequest;
  imageTimer = setTimeout(async () => {
    if (render.token !== token || externalRequest !== intent) return;
    const wanted = [...new Set($$("[data-img]:not(.loaded)").map((el) => el.dataset.img))].filter((k) => !state.images.has(k));
    for (let i = 0; i < wanted.length; i += 12) {
      const keys = wanted.slice(i, i + 12);
      if (render.token !== token || externalRequest !== intent) return;
      const result = await api("/images", "POST", { keys, cached_only: !allowRemote }).catch(() => null);
      if (!result || render.token !== token || externalRequest !== intent) return;
      for (const [key, uri] of Object.entries(result.images)) state.images.set(key, uri);
      applyImages();
    }
    applyImages();
  }, 30);
}
function applyImages() {
  $$("[data-img]:not(.loaded)").forEach((el) => {
    const uri = state.images.get(el.dataset.img);
    if (!uri) return;
    el.style.backgroundImage = `url('${uri}')`;
    el.classList.add("loaded");
  });
}

/* ───────────────────────── Shell and routing ───────────────────────── */

function renderShell() {
  $("#app").innerHTML = `
    <nav class="nav ae-surface" aria-label="${esc(t("Lyra"))}">
      <div class="brand"><span class="brand-mark">${icon("mark")}</span><span class="brand-name">Lyra</span></div>
      ${[
        ["home", "home", t("Up next")],
        ["series", "tv", t("Series")],
        ["movies", "film", t("Movies")],
        ["discover", "compass", t("Discover")],
        ["history", "history", t("History")],
      ]
        .map(([view, glyph, label]) => `<button class="nav-item" data-nav="${view}">${icon(glyph)}<span>${esc(label)}</span>${view === "series" || view === "movies" ? `<span class="count" data-count="${view}"></span>` : ""}</button>`)
        .join("")}
      <span class="grow"></span>
      <button class="nav-item" data-act="settings">${icon("gear")}<span>${esc(t("Settings"))}</span></button>
    </nav>
    <main class="main" id="main">
      <header class="topbar"><div class="topbar-inner ae-surface">
        <button class="ae-btn ae-btn--quiet ae-btn--icon menu-toggle" data-act="nav" aria-label="${esc(t("Menu"))}">${icon("menu")}</button>
        <button class="ae-btn ae-btn--quiet ae-btn--icon" data-act="back" id="back" hidden aria-label="${esc(t("Back"))}">${icon("back")}</button>
        <label class="search">${icon("search")}<span class="ae-visually-hidden">${esc(t("Search your library"))}</span><input class="ae-input" id="search" type="search" placeholder="${esc(t("Search your library"))}" autocomplete="off" maxlength="200"></label>
        <span class="spacer"></span>
      </div></header>
      <div id="view"></div>
    </main>`;
  $("#search").addEventListener("input", onSearch);
  $("#search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch(true);
  });
}
/** Inside a Nexus with the navigation contract every move is a browser history entry and is
 * shown when Nexus confirms it (frontend/navigation.js); otherwise it is shown directly. */
function navigate(route, { push = true, mode = "push" } = {}) {
  $("#app").classList.remove("nav-open");
  if (lyraNavigation.enabled) return commitRoute(route, mode);
  if (push) state.history.push(state.route);
  state.route = route;
  render();
  $("#main").scrollTop = 0;
}
/** The arrow on a title: up to the list it was opened from. Browser Back is the traversal. */
function back() {
  if (lyraNavigation.enabled) {
    const from = state.route.from;
    return navigate({ view: ["home", "series", "movies", "discover", "history"].includes(from) ? from : state.route.type === "movie" ? "movies" : "series" });
  }
  navigate(state.history.pop() || { view: "home" }, { push: false });
}
async function render() {
  const route = state.route;
  $$(".nav-item[data-nav]").forEach((b) => b.toggleAttribute("aria-current", b.dataset.nav === (route.view === "title" ? route.from : route.view)));
  $$(".nav-item[aria-current]").forEach((b) => b.setAttribute("aria-current", "page"));
  $("#back").hidden = route.view !== "title";
  $("[data-count=series]").textContent = state.app.library.series || "";
  $("[data-count=movies]").textContent = state.app.library.movies || "";
  const view = $("#view");
  view.innerHTML = `<div class="page">${skeleton()}</div>`;
  const token = Symbol();
  render.token = token;
  const notFound = () => {
    view.innerHTML = `<div class="page"><div class="ae-empty">${icon("alert")}<h3>${esc(t("This page could not be found"))}</h3><p>${esc(t("The address may be wrong, or the title may have been removed."))}</p><button class="ae-btn" data-nav="home">${esc(t("Up next"))}</button></div></div>`;
    return "not-found";
  };
  if (route.view === "not-found") return notFound();
  try {
    const html = await ({ home: homeView, series: () => libraryView("series"), movies: () => libraryView("movie"), discover: discoverView, history: historyView, title: titleView })[route.view]();
    if (render.token !== token) return;
    view.innerHTML = html;
    animateIn(view.firstElementChild);
    hydrateImages();
    afterRender[route.view]?.();
  } catch (error) {
    if (render.token !== token) return;
    if (/not found/i.test(error.message)) return notFound();
    view.innerHTML = `<div class="page"><div class="ae-banner ae-banner--danger">${icon("alert")}<div><strong>${esc(t("This page could not be loaded."))}</strong><br>${esc(error.message)}</div><button class="ae-btn ae-btn--sm" data-act="reload">${esc(t("Try again"))}</button></div></div>`;
  }
}
const afterRender = {};
function skeleton() {
  return `<div class="ae-skeleton" style="height:28px;width:220px;margin:16px 0 24px"></div><div class="grid">${Array.from({ length: 8 }, () => `<div><div class="ae-skeleton poster"></div><div class="ae-skeleton" style="height:12px;margin-top:10px;width:70%"></div></div>`).join("")}</div>`;
}
async function reloadState() {
  state.app = await api("/state");
}

/* ───────────────────────── Views ───────────────────────── */

function cardHtml(item) {
  const library = item.library;
  const progress = item.progress;
  const badge = library ? `<span class="badge ae-pill ${library.status === "watching" ? "ae-pill--accent" : ""}">${esc(statusLabel(library.status, item.type || (item.kind === "movie" ? "movie" : "series")))}</span>` : "";
  const target = item.id ? `data-open="${item.type}:${esc(item.id)}"` : item.resource ? `data-open="${item.resource.type}:${esc(item.resource.id)}"` : `data-preview="${item.kind}:${item.tmdb_id}"`;
  const sub = [item.year, item.kind ? (item.kind === "tv" ? t("Series") : t("Movie")) : null, progress && progress.total ? t("{watched} of {total}", { watched: progress.watched, total: progress.total }) : null].filter(Boolean).join(" · ");
  return `<button class="card" ${personalAttributes(item)} ${target}>${badge}${art(item.poster, item.title)}${progress && progress.total ? `<div class="bar"><span style="width:${Math.round((progress.watched / progress.total) * 100)}%"></span></div>` : ""}<span class="name" title="${esc(item.title)}">${esc(item.title)}</span><span class="sub">${esc(sub)}</span></button>`;
}
function onboarding() {
  return `<section class="onboard"><div><h2>${esc(t("Connect a metadata provider"))}</h2><p>${esc(t("Lyra uses TMDB to find films and series, their seasons, episodes and release dates. Add your own TMDB read access token; it stays on your server and is never shown again."))}</p></div><button class="ae-btn ae-btn--primary ae-btn--lg" data-act="settings">${icon("key")}<span>${esc(t("Add TMDB credential"))}</span></button></section>`;
}

async function homeView() {
  const home = await api("/home");
  const parts = [];
  if (!state.app.tmdb.configured) parts.push(`<div class="section">${onboarding()}</div>`);
  if (home.watching.length) {
    const lead = home.watching[0];
    const leadNext = lead.next;
    const leadLine = leadNext ? `${episodeCode(leadNext)} · ${leadNext.name || t("Episode {n}", { n: leadNext.episode_number })}` : t("All caught up");
    const leadWhen = !leadNext ? "" : leadNext.state === "available" ? t("Ready to watch") : leadNext.state === "upcoming" ? t("Airs {when}", { when: whenLabel(leadNext.air_date) }) : t("Air date not announced");
    parts.push(`<section class="spotlight" ${personalAttributes(lead)} style="--h:${hue(lead.title)}">${art(lead.backdrop || lead.poster, lead.title, "spotlight-art")}<div class="spotlight-body"><span class="ae-eyebrow">${esc(t("Continue watching"))}</span><h1 data-open="series:${esc(lead.id)}">${esc(lead.title)}</h1><p class="spotlight-ep">${esc(leadLine)}</p><p class="spotlight-meta">${esc(leadWhen)}${lead.progress.total ? ` · ${esc(t("{watched} of {total} episodes", { watched: lead.progress.watched, total: lead.progress.total }))}` : ""}</p><div class="ae-progress spotlight-progress"><span style="width:${lead.progress.total ? Math.round((lead.progress.watched / lead.progress.total) * 100) : 0}%"></span></div><div class="spotlight-actions">${leadNext && leadNext.state === "available" ? `<button class="ae-btn ae-btn--primary ae-btn--lg" data-act="watch-episode" data-id="${esc(leadNext.id)}" data-series="${esc(lead.id)}">${icon("check")}<span>${esc(t("Mark {code} watched", { code: episodeCode(leadNext) }))}</span></button>` : ""}<button class="ae-btn ae-btn--lg" data-open="series:${esc(lead.id)}">${esc(t("Open series"))}</button></div></div><div class="spotlight-poster" data-open="series:${esc(lead.id)}">${art(lead.poster, lead.title)}</div></section>`);
  }
  if (home.watching.length > 1) {
    parts.push(`<section class="section"><div class="section-head"><h2>${esc(t("Also watching"))}</h2></div><div class="continue">${home.watching
      .slice(1)
      .map((s) => {
        const next = s.next;
        const p = s.progress;
        let line = t("All caught up");
        let action = "";
        if (next && next.state === "available") {
          line = `${episodeCode(next)} · ${next.name || t("Episode {n}", { n: next.episode_number })}`;
          action = `<button class="ae-btn ae-btn--sm ae-btn--primary" data-act="watch-episode" data-id="${esc(next.id)}" data-series="${esc(s.id)}">${icon("check")}<span>${esc(t("Watched"))}</span></button>`;
        } else if (next && next.state === "upcoming") line = t("{code} airs {when}", { code: episodeCode(next), when: whenLabel(next.air_date) });
        else if (next) line = t("{code} · date not announced", { code: episodeCode(next) });
        return `<article class="episode-card" ${personalAttributes(s)}><div data-open="series:${esc(s.id)}">${art(s.poster, s.title)}</div><div class="body"><span class="title" data-open="series:${esc(s.id)}">${esc(s.title)}</span><span class="ep">${esc(line)}</span><div class="actions"><div class="ae-progress" title="${esc(t("{watched} of {total} episodes", { watched: p.watched, total: p.total }))}"><span style="width:${p.total ? Math.round((p.watched / p.total) * 100) : 0}%"></span></div>${action}</div></div></article>`;
      })
      .join("")}</div></section>`);
  }
  if (home.upcoming.length) {
    parts.push(`<section class="section"><div class="section-head"><h2>${esc(t("Coming up"))}</h2><span class="ae-meta">${esc(t("From your library · next 60 days"))}</span></div><div class="list">${home.upcoming
      .map((u) => `<button class="list-row timeline-row" data-open="${u.type === "movie" ? "movie" : "series"}:${esc(u.type === "movie" ? u.id : u.series_id)}"><span class="date-badge"><b>${Number(u.date.slice(8, 10))}</b><span>${esc(fmtDate(u.date, { month: "short" }))}</span></span>${art(u.poster, u.title)}<span><span class="t">${esc(u.title)}</span><span class="m">${esc(u.type === "movie" ? releaseLabel(u.label) : `${u.label}${u.name ? " · " + u.name : ""}`)}</span></span><span class="end">${u.certainty !== "confirmed" ? `<span class="ae-pill ae-pill--warn">${esc(u.certainty === "estimated" ? t("Estimated") : t("May change"))}</span>` : ""}<span>${esc(whenLabel(u.date))}</span></span></button>`)
      .join("")}</div></section>`);
  }
  if (home.recent.length) {
    parts.push(`<section class="section"><div class="section-head"><h2>${esc(t("Recently watched"))}</h2><button class="ae-btn ae-btn--quiet ae-btn--sm" data-nav="history">${esc(t("All history"))}</button></div><div class="list">${home.recent.slice(0, 6).map(historyRow).join("")}</div></section>`);
  }
  if (!home.watching.length && !home.upcoming.length && !home.recent.length)
    parts.push(`<div class="ae-empty">${icon("sparkle")}<h3>${esc(t("Your library is empty"))}</h3><p>${esc(t("Search for a film or series to add it to your watchlist, or start tracking episodes."))}</p><button class="ae-btn ae-btn--primary" data-nav="discover">${icon("compass")}<span>${esc(t("Discover"))}</span></button></div>`);
  return `<div class="page">${parts.join("")}</div>`;
}
function releaseLabel(kind) {
  return { theatrical: t("In cinemas"), digital: t("Digital release"), physical: t("Disc release"), release: t("Release date") }[kind] || kind;
}
function historyRow(e) {
  const label = e.type === "episode" ? `${e.label}${e.name ? " · " + e.name : ""}` : t("Movie");
  return `<div class="list-row" ${personalAttributes(e)} data-open="${e.type === "movie" ? "movie" : "series"}:${esc(e.resource_id)}" role="button" tabindex="0">${art(e.poster, e.title)}<span><span class="t">${esc(e.title)}</span><span class="m">${esc(label)}</span></span><span class="end"><span>${esc(fmtWhen(e.watched_at))}</span><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="delete-history" data-id="${esc(e.id)}" aria-label="${esc(t("Remove from history"))}">${icon("x")}</button></span></div>`;
}

async function libraryView(type) {
  const { items } = await api(`/library?type=${type}`);
  const statuses = type === "series" ? SERIES_STATUS : MOVIE_STATUS;
  const filter = state.filter[type];
  const shown = filter === "all" ? items : items.filter((i) => i.library?.status === filter);
  const counts = Object.fromEntries(statuses.map((s) => [s, items.filter((i) => i.library?.status === s).length]));
  return `<div class="page"><h1 class="page-title">${esc(type === "series" ? t("Series") : t("Movies"))}</h1>
    <div class="toolbar"><div class="ae-seg" role="group" aria-label="${esc(t("Filter"))}"><button data-filter="all" data-type="${type}" aria-pressed="${filter === "all"}">${esc(t("All"))} <span class="ae-meta">${items.length}</span></button>${statuses.map((s) => `<button data-filter="${s}" data-type="${type}" aria-pressed="${filter === s}">${esc(statusLabel(s, type))}${counts[s] ? ` <span class="ae-meta">${counts[s]}</span>` : ""}</button>`).join("")}</div></div>
    ${shown.length ? `<div class="grid">${shown.map(cardHtml).join("")}</div>` : `<div class="ae-empty">${icon(type === "series" ? "tv" : "film")}<h3>${esc(items.length ? t("Nothing here") : type === "series" ? t("No series yet") : t("No movies yet"))}</h3><p>${esc(items.length ? t("No titles have this status.") : t("Use search to find something to watch."))}</p>${items.length ? "" : `<button class="ae-btn ae-btn--primary" data-nav="discover">${esc(t("Discover"))}</button>`}</div>`}
  </div>`;
}

async function discoverView() {
  if (state.query.trim().length >= 2) return searchView();
  if (!state.app.tmdb.configured) return `<div class="page"><h1 class="page-title">${esc(t("Discover"))}</h1>${onboarding()}</div>`;
  return `<div class="page"><h1 class="page-title">${esc(t("Discover"))}</h1>${externalSection("tmdb-discover")}</div>`;
}
function discoveryHtml(data) {
  const titles = { trending: t("Trending this week"), upcoming: t("Coming to cinemas"), on_the_air: t("Series airing now") };
  return data.sections.map((s) => `<section class="section"><div class="section-head"><h2>${esc(titles[s.key])}</h2></div>${s.error ? `<div class="ae-banner ae-banner--warn">${icon("alert")}<div>${esc(s.error)}</div></div>` : `<div class="rail">${s.items.map(cardHtml).join("")}</div>`}</section>`).join("");
}
function externalSection(action) {
  const labels = { "tmdb-search": t("Search TMDB"), "tmdb-discover": t("Browse TMDB recommendations"), "tmdb-preview": t("Load details from TMDB") };
  const hint = action === "tmdb-search" ? t("Your library search stays local. Only Search TMDB sends these words to TMDB.") : t("TMDB is an external service. Loading sends language, region or the selected title ID to TMDB.");
  return `<section class="section" id="external-section"><div class="section-head"><h2>${esc(t("From TMDB"))}</h2><span class="ae-meta">${esc(t("External discovery"))}</span></div><p class="ae-meta">${esc(hint)}</p>${state.app.tmdb.configured ? `<button class="ae-btn" data-act="${action}">${esc(labels[action])}</button>` : onboarding()}<div id="external-results" class="external-results" aria-live="polite"></div><p class="attribution">${esc(state.app.attribution)}</p></section>`;
}
// Intent is never persisted in navigation state. Each new render requires a new action.
let externalRequest = 0;
function invalidateExternal() {
  externalRequest++;
  clearTimeout(imageTimer);
  const results = $("#external-results");
  if (results) results.replaceChildren();
  $$("[data-act^='tmdb-']").forEach((button) => { button.disabled = button.dataset.act === "tmdb-search"; });
}
async function loadExternal(action, button) {
  if (button.disabled) return;
  const token = render.token;
  const route = state.route;
  const query = state.query.trim();
  const request = ++externalRequest;
  const results = $("#external-results");
  if (!results) return;
  const current = () => request === externalRequest && render.token === token && state.route === route && state.query.trim() === query && results.isConnected;
  button.disabled = true;
  results.textContent = t("Loading from TMDB…");
  try {
    const data = action === "tmdb-search" ? await api("/search/external", "POST", { query }) : action === "tmdb-discover" ? await api("/discover") : await api(`/preview/${route.kind}/${route.tmdb_id}`);
    if (!current()) return;
    if (data.resource) return navigate({ view: "title", type: data.resource.type, id: data.resource.id, from: route.from }, { mode: "replace" });
    if (data.remote_error) throw Error(data.remote_error === "not_configured" ? t("Add TMDB credential") : data.remote_error);
    results.innerHTML = action === "tmdb-search" ? (data.remote.length ? `<div class="grid">${data.remote.map(cardHtml).join("")}</div>` : `<p class="ae-meta">${esc(t("TMDB found nothing for “{query}”.", { query }))}</p>`) : action === "tmdb-discover" ? discoveryHtml(data) : previewHtml(data.preview);
    hydrateImages(true);
  } catch (error) {
    if (current()) results.innerHTML = `<p class="ae-error-text" role="alert">${esc(error.message || t("Something went wrong."))}</p>`;
  } finally {
    if (current()) button.disabled = false;
  }
}
let searchTimer;
function onSearch(event) {
  invalidateExternal();
  state.query = event.target.value;
  lyraNavigation.viewChanged();
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(false), 350);
}
function runSearch(force) {
  if (state.query.trim().length < 2 && !force) {
    if (state.route.view === "discover") render();
    return;
  }
  if (state.route.view === "discover") render();
  else navigate({ view: "discover" });
}
async function searchView() {
  const query = state.query.trim();
  const data = await api("/search?q=" + encodeURIComponent(query));
  return `<div class="page"><h1 class="page-title">${esc(t("Results for “{query}”", { query }))}</h1>
    <section class="section"><div class="section-head"><h2>${esc(t("In your library"))}</h2></div>${data.local.length ? `<div class="grid">${data.local.map(cardHtml).join("")}</div>` : `<p class="ae-meta">${esc(t("Nothing in your library matches."))}</p>`}</section>
    ${externalSection("tmdb-search")}</div>`;
}

async function historyView() {
  const { entries } = await api("/history?limit=200");
  if (!entries.length) return `<div class="page"><h1 class="page-title">${esc(t("History"))}</h1><div class="ae-empty">${icon("history")}<h3>${esc(t("Nothing watched yet"))}</h3><p>${esc(t("Films and episodes you mark as watched appear here. History stays on your server."))}</p></div></div>`;
  const groups = new Map();
  for (const e of entries) {
    const key = e.watched_at.slice(0, 10);
    groups.set(key, [...(groups.get(key) || []), e]);
  }
  return `<div class="page"><h1 class="page-title">${esc(t("History"))}</h1>${[...groups].map(([day, list]) => `<h2 class="ae-eyebrow day-head">${esc(fmtDate(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" }))}</h2><div class="list">${list.map(historyRow).join("")}</div>`).join("")}</div>`;
}

/* ───────────────────────── Title page ───────────────────────── */

async function titleView() {
  const route = state.route;
  if (route.preview) {
    return `<div class="page"><h1 class="page-title">${esc(t("Title preview"))}</h1>${externalSection("tmdb-preview")}</div>`;
  }
  const data = await api(route.type === "movie" ? `/movies/${route.id}` : `/series/${route.id}`);
  state.title = data;
  return route.type === "movie" ? movieHtml(data) : seriesHtml(data);
}
function heroHtml(data, actions, meta) {
  const backdrop = data.backdrop || data.poster;
  return `<section class="hero" ${personalAttributes(data)} style="--h:${hue(data.title)}">${backdrop ? `<div class="backdrop ${data.backdrop ? "" : "from-poster"}" data-img="${esc(backdrop)}" data-backdrop></div>` : ""}<div class="hero-inner">${art(data.poster, data.title)}<div class="hero-text">
    <h1>${esc(data.title)}</h1><div class="meta">${meta.filter(Boolean).map((m) => `<span class="meta-chip">${m}</span>`).join("")}</div>
    ${data.tagline ? `<p class="tagline">${esc(data.tagline)}</p>` : ""}${data.overview ? `<p class="overview">${esc(data.overview)}</p>` : ""}
    <div class="actions">${actions}</div></div></div></section>`;
}
function providerStatus(status) {
  return { "Returning Series": t("Returning series"), Ended: t("Ended"), Canceled: t("Cancelled"), "In Production": t("In production"), Planned: t("Planned"), Released: t("Released"), "Post Production": t("Post-production") }[status] || status;
}
function previewHtml(p) {
  const isMovie = p.kind === "movie";
  const actions = isMovie
    ? `<button class="ae-btn ae-btn--primary" data-act="add" data-kind="movie" data-tmdb="${p.tmdb_id}" data-status="planned">${icon("plus")}<span>${esc(t("Add to watchlist"))}</span></button><button class="ae-btn" data-act="add" data-kind="movie" data-tmdb="${p.tmdb_id}" data-status="watched">${icon("check")}<span>${esc(t("I've watched it"))}</span></button>`
    : `<button class="ae-btn ae-btn--primary" data-act="add" data-kind="tv" data-tmdb="${p.tmdb_id}" data-status="watching">${icon("plus")}<span>${esc(t("Start watching"))}</span></button><button class="ae-btn" data-act="add" data-kind="tv" data-tmdb="${p.tmdb_id}" data-status="planned">${esc(t("Plan to watch"))}</button>`;
  const meta = [esc(p.year), isMovie ? (p.runtime ? esc(t("{minutes} min", { minutes: p.runtime })) : "") : p.seasons ? esc(plural(p.seasons, "{count} season", "{count} seasons")) : "", esc(p.genres.slice(0, 3).join(", ")), p.provider_status ? esc(providerStatus(p.provider_status)) : ""];
  return `${heroHtml(p, actions, meta)}<div class="title-body"><div>${p.cast.length ? `<section><h2 class="ae-eyebrow">${esc(t("Cast"))}</h2><p>${esc(p.cast.join(", "))}</p></section>` : ""}<p class="ae-meta">${esc(t("Not in your library yet. Adding it creates a Lyra record; TMDB stays only the source of its metadata."))}</p><p class="attribution">${esc(state.app.attribution)}</p></div></div>`;
}
function ratingHtml(library, type, id) {
  const value = library?.rating || 0;
  return `<div class="inline" style="display:flex;align-items:center"><div class="rating" role="radiogroup" aria-label="${esc(t("Your rating"))}">${Array.from({ length: 10 }, (_, i) => `<button class="${i < value ? "on" : ""}" data-act="rate" data-type="${type}" data-id="${esc(id)}" data-value="${i + 1 === value ? 0 : i + 1}" role="radio" aria-checked="${i + 1 === value}" aria-label="${esc(t("{n} of 10", { n: i + 1 }))}">${i + 1}</button>`).join("")}</div><span class="rating-value">${value ? esc(t("{n}/10", { n: value })) : esc(t("Not rated"))}</span></div>`;
}
function statusSelect(data) {
  const options = data.type === "movie" ? MOVIE_STATUS : SERIES_STATUS;
  if (!data.library) return `<button class="ae-btn ae-btn--primary" data-act="track" data-type="${data.type}" data-id="${esc(data.id)}">${icon("plus")}<span>${esc(data.type === "movie" ? t("Add to watchlist") : t("Track series"))}</span></button>`;
  return `<label class="ae-visually-hidden" for="status">${esc(t("Status"))}</label><select class="ae-select" id="status" data-act="status" data-type="${data.type}" data-id="${esc(data.id)}" style="width:auto">${options.map((s) => `<option value="${s}" ${data.library.status === s ? "selected" : ""}>${esc(statusLabel(s, data.type))}</option>`).join("")}</select>`;
}
function sidePanels(data) {
  const ext = data.external || {};
  const crew = (data.credits?.crew || []).slice(0, 4);
  return `<aside class="aside">
    ${data.library ? `<section class="panel"><h3>${esc(t("Your rating"))}</h3>${ratingHtml(data.library, data.type, data.id)}</section>` : ""}
    ${data.library ? `<section class="panel"><h3>${esc(t("Notes"))}</h3><textarea class="ae-textarea notes" data-notes="${data.type}:${esc(data.id)}" data-revision="${esc(data.revision)}" maxlength="10000" placeholder="${esc(t("Only you see these."))}">${esc(data.library.notes)}</textarea></section>` : ""}
    ${data.library ? `<section class="panel"><h3>${esc(t("Calendar"))}</h3><select class="ae-select" data-act="calendar" data-type="${data.type}" data-id="${esc(data.id)}"><option value="default" ${data.library.calendar === "default" ? "selected" : ""}>${esc(t("Follow sharing settings"))}</option><option value="always" ${data.library.calendar === "always" ? "selected" : ""}>${esc(t("Always share dates with Chronos"))}</option><option value="never" ${data.library.calendar === "never" ? "selected" : ""}>${esc(t("Never share dates"))}</option></select><div id="planned" class="ae-meta" style="margin-top:10px"></div></section>` : ""}
    <section class="panel" id="linked-panel" hidden><h3>${esc(t("Linked from other modules"))}</h3><div id="linked-from"></div><p class="ae-meta">${esc(t("These items belong to their modules."))}</p></section>
    <section class="panel"><h3>${esc(t("Details"))}</h3><dl class="facts">${crew.map((c) => `<div><dt>${esc(c.job)}</dt><dd>${esc(c.name)}</dd></div>`).join("")}${data.networks?.length ? `<div><dt>${esc(t("Network"))}</dt><dd>${esc(data.networks.join(", "))}</dd></div>` : ""}${data.original_title && data.original_title !== data.title ? `<div><dt>${esc(t("Original title"))}</dt><dd>${esc(data.original_title)}</dd></div>` : ""}<div><dt>TMDB</dt><dd class="ae-mono">${esc(ext.tmdb || "—")}</dd></div>${ext.imdb ? `<div><dt>IMDb</dt><dd class="ae-mono">${esc(ext.imdb)}</dd></div>` : ""}<div><dt>${esc(t("Updated"))}</dt><dd>${data.refreshing ? esc(t("Refreshing…")) : data.refreshed_at ? esc(fmtWhen(data.refreshed_at)) : "—"}</dd></div></dl></section>
  </aside>`;
}
function titleMenuButton(data) {
  return `<button class="ae-btn ae-btn--quiet ae-btn--icon" data-act="title-menu" aria-haspopup="menu" aria-label="${esc(t("More actions"))}">${icon("more")}</button>`;
}
function movieHtml(m) {
  const actions = `${statusSelect(m)}<button class="ae-btn ${m.library ? "" : ""}" data-act="watch-movie" data-id="${esc(m.id)}">${icon("check")}<span>${esc(m.history.length ? t("Watched again") : t("Mark watched"))}</span></button>${titleMenuButton(m)}`;
  const meta = [esc(m.year), m.runtime ? esc(t("{minutes} min", { minutes: m.runtime })) : "", esc(m.genres.slice(0, 3).join(", ")), m.provider_status && m.provider_status !== "Released" ? esc(providerStatus(m.provider_status)) : ""];
  const releases = m.releases.length
    ? `<div class="list">${m.releases.map((r) => `<div class="list-row" style="grid-template-columns:minmax(0,1fr) auto;cursor:default"><span><span class="t">${esc(releaseLabel(r.kind))}</span><span class="m">${esc(r.kind === "release" ? t("No date for {region} yet; this is TMDB's primary release date.", { region: m.region }) : t("Region {region}", { region: m.region }))}</span></span><span class="end">${r.certainty === "tentative" ? `<span class="ae-pill ae-pill--warn">${esc(t("May change"))}</span>` : r.certainty === "estimated" ? `<span class="ae-pill ae-pill--warn">${esc(t("Estimated"))}</span>` : ""}<span>${esc(fmtDate(r.date))}</span></span></div>`).join("")}</div>`
    : `<p class="ae-meta">${esc(t("No release date is known yet."))}</p>`;
  const history = m.history.length ? `<div class="list">${m.history.map((h) => `<div class="list-row" style="grid-template-columns:minmax(0,1fr) auto;cursor:default"><span class="t">${esc(fmtWhen(h.watched_at))}</span><span class="end"><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="delete-history" data-id="${esc(h.id)}" aria-label="${esc(t("Remove from history"))}">${icon("x")}</button></span></div>`).join("")}</div>` : `<p class="ae-meta">${esc(t("Not watched yet."))}</p>`;
  const cast = m.credits?.cast?.length ? `<section class="section"><div class="section-head"><h2>${esc(t("Cast"))}</h2></div><ul class="cast">${m.credits.cast.map((c) => `<li>${esc(c.name)}${c.character ? ` <span>${esc(c.character)}</span>` : ""}</li>`).join("")}</ul></section>` : "";
  return `${heroHtml(m, actions, meta)}<div class="title-body"><div>
    <section class="section"><div class="section-head"><h2>${esc(t("Releases"))}</h2></div>${releases}</section>
    <section class="section"><div class="section-head"><h2>${esc(t("Viewing history"))}</h2></div>${history}</section>
    ${cast}<p class="attribution">${esc(state.app.attribution)}</p></div>${sidePanels(m)}</div>`;
}
function seriesHtml(s) {
  const p = s.progress;
  const meta = [esc(s.year), s.networks[0] ? esc(s.networks[0]) : "", esc(s.genres.slice(0, 3).join(", ")), s.provider_status ? esc(providerStatus(s.provider_status)) : "", p.total ? esc(t("{watched} of {total} episodes watched", { watched: p.watched, total: p.total })) : ""];
  const actions = `${statusSelect(s)}${titleMenuButton(s)}`;
  const next = s.next;
  let nextHtml = "";
  if (next) {
    const when = next.state === "available" ? t("Aired {date}", { date: fmtDate(next.air_date) }) : next.state === "upcoming" ? t("Airs {when}", { when: whenLabel(next.air_date) }) : t("Air date not announced");
    nextHtml = `<section class="next"><div><span class="ae-eyebrow label">${esc(next.state === "available" ? t("Up next") : t("Next episode"))}</span><div class="name">${esc(episodeCode(next))} · ${esc(next.name || t("Episode {n}", { n: next.episode_number }))}</div><span class="ae-meta">${esc(when)}${next.state === "upcoming" ? ` · ${esc(t("date may change"))}` : ""}</span></div>${next.state === "available" ? `<button class="ae-btn ae-btn--primary" data-act="watch-episode" data-id="${esc(next.id)}">${icon("check")}<span>${esc(t("Mark watched"))}</span></button>` : ""}</section>`;
  } else if (p.total && p.watched >= p.total) {
    nextHtml = `<section class="next"><div><span class="ae-eyebrow label">${esc(t("All caught up"))}</span><div class="name">${esc(s.provider_status === "Ended" || s.provider_status === "Canceled" ? t("You have seen every episode.") : t("You have seen every announced episode."))}</div></div></section>`;
  }
  const seasons = s.seasons
    .map((season, index) => {
      const open = state.openSeason ? state.openSeason === season.id : next ? season.number === next.season_number : index === 0;
      const name = season.number === 0 ? t("Specials") : season.name || t("Season {n}", { n: season.number });
      const pct = season.episodes.length ? Math.round((season.watched / season.episodes.length) * 100) : 0;
      return `<details class="season" data-season="${esc(season.id)}" ${open ? "open" : ""}><summary><span><span class="s-name">${esc(name)}</span><span class="s-meta">${esc([season.air_date ? fmtDate(season.air_date, { year: "numeric", month: "short" }) : t("Not announced"), plural(season.episodes.length, "{count} episode", "{count} episodes")].join(" · "))}</span></span><div class="ae-progress"><span style="width:${pct}%"></span></div><span class="s-count">${season.watched}/${season.episodes.length}</span></summary>
        <div class="episodes">${season.episodes
          .map(
            (e) => `<div class="episode ${e.watched ? "watched" : ""} ${e.state}"><input type="checkbox" class="ae-check" data-act="toggle-episode" data-id="${esc(e.id)}" ${e.watched ? "checked" : ""} ${e.state !== "aired" && !e.watched ? "disabled" : ""} aria-label="${esc(t("Watched {code}", { code: episodeCode(e) }))}"><span class="num">${e.number}</span><span><span class="e-name">${esc(e.name || t("Episode {n}", { n: e.number }))}</span><span class="e-meta">${esc(e.watched && e.watched_at ? t("Watched {when}", { when: fmtWhen(e.watched_at) }) : e.runtime ? t("{minutes} min", { minutes: e.runtime }) : "")}</span></span><span class="date">${e.state === "upcoming" ? `<span class="ae-pill ae-pill--accent">${esc(whenLabel(e.air_date))}</span>` : e.air_date ? esc(fmtDate(e.air_date)) : esc(t("TBA"))}</span><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="episode-menu" data-id="${esc(e.id)}" aria-haspopup="menu" aria-label="${esc(t("More actions"))}">${icon("more")}</button></div>`,
          )
          .join("")}
          ${season.aired ? `<div style="padding:8px"><button class="ae-btn ae-btn--quiet ae-btn--sm" data-act="${season.watched >= season.aired ? "unwatch-season" : "watch-season"}" data-id="${esc(season.id)}">${icon("check")}<span>${esc(season.watched >= season.aired ? t("Mark season unwatched") : t("Mark aired episodes watched"))}</span></button></div>` : ""}</div></details>`;
    })
    .join("");
  const cast = s.credits?.cast?.length ? `<section class="section"><div class="section-head"><h2>${esc(t("Cast"))}</h2></div><ul class="cast">${s.credits.cast.map((c) => `<li>${esc(c.name)}${c.character ? ` <span>${esc(c.character)}</span>` : ""}</li>`).join("")}</ul></section>` : "";
  return `${heroHtml(s, actions, meta)}<div class="title-body"><div>${nextHtml}
    <section class="section"><div class="section-head"><h2>${esc(t("Seasons"))}</h2>${s.refreshing ? `<span class="ae-meta">${esc(t("Loading all seasons…"))}</span>` : ""}</div>${seasons ? `<div class="seasons ae-surface">${seasons}</div>` : `<p class="ae-meta">${esc(t("TMDB lists no seasons yet."))}</p>`}</section>
    ${cast}<p class="attribution">${esc(state.app.attribution)}</p></div>${sidePanels(s)}</div>`;
}
const LINKED_KIND = { "chronos:event": "Event in Chronos" };
async function loadLinkedFrom(data) {
  const result = await api(`/${data.type}/${data.id}/linked-from`).catch(() => null);
  const box = $("#linked-from");
  if (!box || !result || result.availability !== "available" || !result.items.length) return;
  box.innerHTML = result.items.map((x) => {
    const gone = x.availability !== "available";
    const note = x.availability === "deleted" ? t("deleted there") : ["forbidden", "not_found", "not_resolvable"].includes(x.availability) ? t("not available") : gone ? t("not available right now") : "";
    const open = !gone && state.context.applications.some((a) => a.id === x.module) ? `<button class="ae-btn ae-btn--quiet ae-btn--icon" data-open-module="${esc(x.module)}" data-path="${esc(x.open_path || "")}" aria-label="${esc(t("Open"))}">${icon("open")}</button>` : "";
    return `<div class="linked-row${gone ? " is-gone" : ""}"><div><strong>${esc(gone ? t("Something linked here") : x.label)}</strong><div class="ae-meta">${esc([t(LINKED_KIND[`${x.module}:${x.type}`] || "Linked from another module"), note].filter(Boolean).join(" · "))}</div></div>${open}</div>`;
  }).join("");
  $("#linked-panel").hidden = false;
}
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-open-module]");
  if (el) bridge("navigate", { module: el.dataset.openModule, ...(el.dataset.path ? { path: el.dataset.path } : {}) }).catch((e) => toast(e.message, "danger"));
});
afterRender.title = async () => {
  restoreNoteDraft();
  const data = state.title;
  if (!data || state.route.preview) return;
  loadLinkedFrom(data);
  if (data.refreshing) setTimeout(() => state.route.view === "title" && state.route.id === data.id && refreshTitle(), 2500);
  const box = $("#planned");
  if (!box) return;
  const planned = await api(`/${data.type}/${data.id}/planned`).catch(() => null);
  if (!box.isConnected || !planned) return;
  const events = planned.events.filter((e) => e.availability === "available");
  box.innerHTML = !planned.available
    ? esc(t("Chronos links could not be checked right now."))
    : events.length
      ? `<strong style="color:var(--text-2)">${esc(t("Planned in Chronos"))}</strong>${events.map((e) => `<div>${icon("calendar")} ${esc(e.label)}${e.start ? ` · ${esc(e.all_day ? fmtDate(e.start) : fmtWhen(e.start))}` : ""}</div>`).join("")}`
      : esc(t("Not planned in Chronos. Release dates you share appear there automatically."));
};
async function refreshTitle() {
  const route = state.route;
  const data = await api(route.type === "movie" ? `/movies/${route.id}` : `/series/${route.id}`).catch(() => null);
  if (!data || state.route !== route) return;
  state.title = data;
  const main = $("#main");
  const scroll = main.scrollTop;
  $("#view").innerHTML = route.type === "movie" ? movieHtml(data) : seriesHtml(data);
  main.scrollTop = scroll;
  hydrateImages();
  afterRender.title();
}

/* ───────────────────────── Menus and dialogs ───────────────────────── */

function openMenu(anchor, items) {
  closeMenu();
  const menu = document.createElement("div");
  menu.className = "ae-menu ae-glass";
  menu.setAttribute("role", "menu");
  menu.innerHTML = items.map((item, i) => (item === "-" ? '<div class="ae-menu-sep" role="separator"></div>' : `<button class="ae-menu-item ${item.danger ? "ae-menu-item--danger" : ""}" role="menuitem" data-index="${i}">${item.icon ? icon(item.icon) : ""}<span>${esc(item.label)}</span></button>`)).join("");
  document.body.append(menu);
  const box = anchor.getBoundingClientRect();
  menu.style.left = Math.max(8, Math.min(box.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 8)) + "px";
  menu.style.top = (box.bottom + 6 + menu.offsetHeight > innerHeight - 8 ? box.top - menu.offsetHeight - 6 : box.bottom + 6) + "px";
  menu.anchor = anchor;
  anchor.setAttribute("aria-expanded", "true");
  menu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-index]");
    if (!button) return;
    closeMenu();
    items[Number(button.dataset.index)].run();
  });
  menu.addEventListener("keydown", (event) => {
    const buttons = $$(".ae-menu-item", menu);
    const index = buttons.indexOf(document.activeElement);
    if (event.key === "ArrowDown") buttons[(index + 1) % buttons.length].focus();
    else if (event.key === "ArrowUp") buttons[(index - 1 + buttons.length) % buttons.length].focus();
    else return;
    event.preventDefault();
  });
  $(".ae-menu-item", menu)?.focus();
}
function closeMenu() {
  const menu = $(".ae-menu");
  if (!menu) return false;
  menu.anchor?.setAttribute("aria-expanded", "false");
  menu.anchor?.focus?.();
  menu.remove();
  return true;
}
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".ae-menu") && !event.target.closest("[aria-haspopup]")) closeMenu();
});
const dialog = () => $("#dialog");
function openDialog(html, wide = false) {
  const d = dialog();
  d.className = `ae-dialog ae-glass ${wide ? "ae-dialog--wide" : ""}`;
  d.innerHTML = html;
  if (!d.open) d.showModal();
  ($("[autofocus]", d) || $("input,select,textarea,button", d))?.focus();
  return d;
}
const closeDialog = () => dialog().open && dialog().close();
function confirmAction(title, text, label, run) {
  openDialog(`<div class="ae-dialog-head"><h2>${esc(title)}</h2></div><div class="ae-dialog-body"><p style="margin:0;color:var(--text-2)">${esc(text)}</p></div><div class="ae-dialog-foot"><button class="ae-btn" data-act="dialog-cancel">${esc(t("Cancel"))}</button><button class="ae-btn ae-btn--danger" id="confirm">${esc(label)}</button></div>`);
  $("#confirm").onclick = async (e) => {
    e.currentTarget.classList.add("is-busy");
    await run();
    closeDialog();
  };
}

const REGIONS = ["US", "GB", "SK", "CZ", "DE", "AT", "FR", "ES", "IT", "NL", "PL", "HU", "SE", "NO", "DK", "FI", "IE", "PT", "CH", "BE", "CA", "AU", "NZ", "BR", "MX", "JP", "KR", "IN"];
function regionName(code) {
  try {
    return new Intl.DisplayNames([activeLocale], { type: "region" }).of(code) || code;
  } catch {
    return code;
  }
}
function settingsDialog() {
  const s = state.app.settings;
  const tmdb = state.app.tmdb;
  const episodes = [
    ["watching", t("Series I'm watching"), t("Recommended. Keeps the calendar about what you follow.")],
    ["tracked", t("Every series in my library"), t("Except dropped series.")],
    ["selected", t("Only series I choose"), t("Set “Always share dates” on a series.")],
    ["none", t("No episodes"), ""],
  ];
  openDialog(
    `<div class="ae-dialog-head"><h2>${esc(t("Settings"))}</h2><button class="ae-btn ae-btn--quiet ae-btn--icon ae-btn--sm" data-act="dialog-cancel" aria-label="${esc(t("Close"))}">${icon("x")}</button></div>
    <div class="ae-dialog-body">
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("Metadata provider"))}</span>
        <div class="setting"><div><strong>TMDB</strong><span>${esc(tmdb.configured ? t("Connected with a {kind}. The credential is stored on your server and cannot be shown again.", { kind: tmdb.kind === "bearer" ? t("read access token") : t("API key") }) : t("Not connected. Create a free API read access token in your TMDB account settings."))}</span></div>${tmdb.configured ? `<button class="ae-btn ae-btn--sm" id="remove-credential">${esc(t("Remove"))}</button>` : ""}</div>
        <div class="ae-field" style="margin-top:12px"><label for="credential">${esc(tmdb.configured ? t("Replace credential") : t("API read access token or API key"))}</label><div style="display:flex;gap:8px"><input class="ae-input" id="credential" type="password" autocomplete="off" spellcheck="false" placeholder="eyJhbGciOi…"><button class="ae-btn ae-btn--primary" id="save-credential">${esc(t("Verify and save"))}</button></div><span class="ae-hint">${esc(t("Lyra checks it with TMDB before saving. It is never sent to your browser, logs or backups."))}</span><p class="ae-error-text" id="credential-error" hidden></p></div>
        <div style="margin-top:8px"><button class="ae-btn ae-btn--quiet ae-btn--sm" id="tmdb-link">${icon("open")}<span>${esc(t("Open TMDB API settings"))}</span></button></div>
      </section>
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("Region and language"))}</span>
        <div class="setting"><div><strong>${esc(t("Release region"))}</strong><span>${esc(t("Cinema and digital release dates are shown for this country."))}</span></div><select class="ae-select" id="region" style="width:220px">${[...new Set([s.region, ...REGIONS])].map((r) => `<option value="${r}" ${r === s.region ? "selected" : ""}>${esc(regionName(r))}</option>`).join("")}</select></div>
        <div class="setting"><div><strong>${esc(t("Metadata language"))}</strong><span>${esc(t("Titles and overviews from TMDB, where translated."))}</span></div><select class="ae-select" id="language" style="width:220px">${[...new Set([s.language, "en-US", "sk-SK", "cs-CZ", "de-DE", "fr-FR", "es-ES"])].map((l) => `<option value="${l}" ${l === s.language ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      </section>
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("Sharing with Chronos"))}</span>
        <p class="ae-meta" style="margin:8px 0 0">${esc(t("Lyra decides which release dates Chronos may show. Chronos keeps only a copy that follows these choices."))}</p>
        <div class="radio-list" role="radiogroup" aria-label="${esc(t("Episode air dates"))}">${episodes.map(([v, label, hint]) => `<label><input type="radio" name="episodes" value="${v}" ${s.calendar_episodes === v ? "checked" : ""}><div><strong>${esc(label)}</strong>${hint ? `<span>${esc(hint)}</span>` : ""}</div></label>`).join("")}</div>
        <div class="setting"><div><strong>${esc(t("Season premieres only"))}</strong><span>${esc(t("Share only the first episode of each season."))}</span></div><input type="checkbox" role="switch" class="ae-switch" id="premieres" ${s.calendar_premieres_only ? "checked" : ""} aria-label="${esc(t("Season premieres only"))}"></div>
        <div class="setting"><div><strong>${esc(t("Movie releases from my watchlist"))}</strong><span>${esc(t("Cinema and digital dates of films you plan to watch."))}</span></div><input type="checkbox" role="switch" class="ae-switch" id="movies" ${s.calendar_movies === "watchlist" ? "checked" : ""} aria-label="${esc(t("Movie releases from my watchlist"))}"></div>
      </section>
      <section class="settings-group"><span class="ae-eyebrow">${esc(t("About"))}</span><p class="ae-meta" style="margin:8px 0 0">${esc(t("Lyra {version}. Films and series are tracked now; music, books, audiobooks and playback come later.", { version: state.app.version }))}<br>${esc(state.app.attribution)}</p></section>
    </div>
    <div class="ae-dialog-foot"><button class="ae-btn ae-btn--primary" data-act="dialog-cancel">${esc(t("Done"))}</button></div>`,
    true,
  );
  const root = dialog();
  const save = async (body) => {
    const settings = await attempt(() => api("/settings", "PUT", body));
    if (settings) state.app.settings = settings;
  };
  $("#save-credential", root).onclick = async (e) => {
    const value = $("#credential", root).value.trim();
    const error = $("#credential-error", root);
    if (!value) return;
    e.currentTarget.classList.add("is-busy");
    try {
      await api("/credential", "PUT", { value });
      $("#credential", root).value = "";
      await reloadState();
      toast(t("TMDB connected"));
      closeDialog();
      render();
    } catch (failure) {
      $("#save-credential", root).classList.remove("is-busy");
      error.textContent = failure.message;
      error.hidden = false;
    }
  };
  $("#remove-credential", root)?.addEventListener("click", () =>
    confirmAction(t("Remove the TMDB credential?"), t("Your library stays searchable. External discovery and metadata updates stop until you add a credential again."), t("Remove"), async () => {
      await attempt(() => api("/credential", "DELETE"));
      await reloadState();
      render();
    }),
  );
  $("#tmdb-link", root).onclick = () => bridge("external", { url: "https://www.themoviedb.org/settings/api" }).then((r) => r?.trusted && !r.opened && toast(t("Site trusted. Click the link again to open it."))).catch((e) => toast(e.message, "danger"));
  $("#region", root).onchange = (e) => save({ region: e.target.value });
  $("#language", root).onchange = (e) => save({ language: e.target.value });
  $$("[name=episodes]", root).forEach((r) => (r.onchange = () => save({ calendar_episodes: r.value })));
  $("#premieres", root).onchange = (e) => save({ calendar_premieres_only: e.target.checked });
  $("#movies", root).onchange = (e) => save({ calendar_movies: e.target.checked ? "watchlist" : "none" });
}

/* ───────────────────────── Actions ───────────────────────── */

async function afterSeriesChange(result) {
  if (!result) return;
  state.title = result;
  await reloadState();
  if (state.route.view === "title") refreshTitle();
  else render();
  if (result.suggest_completed)
    toast(t("You have seen every episode of {title}.", { title: result.title }), "", {
      label: t("Mark completed"),
      run: async () => {
        await attempt(() => api(`/library/series/${result.id}`, "PUT", { status: "completed" }, { kind: "series", id: result.id, revision: result.revision }));
        refreshTitle();
      },
    });
}
function titleMenu(anchor) {
  const data = state.title;
  const items = [{ label: t("Refresh from TMDB"), icon: "refresh", run: async () => { if (await attempt(() => api(`/${data.type}/${data.id}/refresh`, "POST"), t("Refreshing…"))) setTimeout(refreshTitle, 1500); } }];
  if (data.library)
    items.push("-", {
      label: t("Remove from library"),
      icon: "trash",
      danger: true,
      run: () =>
        confirmAction(t("Remove {title} from your library?", { title: data.title }), t("Your rating, notes and status are removed. Viewing history is kept unless you also clear it from History."), t("Remove"), async () => {
          const removed = await attempt(() => api(`/library/${data.type}/${data.id}`, "DELETE", undefined, { kind: data.type, id: data.id, revision: data.revision }), t("Removed from library"));
          if (!removed) return;
          await reloadState();
          back();
        }),
    });
  openMenu(anchor, items);
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    if (nav.dataset.nav !== "discover") {
      // Via Nexus the search is cleared once this entry's view state has been recorded with it.
      if (lyraNavigation.enabled) clearSearchOnApply = true;
      else {
        state.query = "";
        $("#search").value = "";
      }
    }
    return navigate({ view: nav.dataset.nav });
  }
  if (event.target.closest("[data-act=delete-history]")) {
    const id = event.target.closest("[data-act]").dataset.id;
    await attempt(() => api(`/history/${id}`, "DELETE"), t("Removed from history"));
    return state.route.view === "title" ? refreshTitle() : render();
  }
  const opener = event.target.closest("[data-open]");
  if (opener && !event.target.closest("[data-act]")) {
    const [type, id] = opener.dataset.open.split(":");
    return navigate({ view: "title", type, id, from: state.route.view === "title" ? state.route.from : state.route.view });
  }
  const preview = event.target.closest("[data-preview]");
  if (preview) {
    const [kind, tmdb] = preview.dataset.preview.split(":");
    return navigate({ view: "title", preview: true, kind, tmdb_id: Number(tmdb), from: state.route.view });
  }
  const filter = event.target.closest("[data-filter]");
  if (filter) {
    state.filter[filter.dataset.type] = filter.dataset.filter;
    lyraNavigation.viewChanged();
    return render();
  }
  const target = event.target.closest("[data-act]");
  if (!target) return;
  const { act, id } = target.dataset;
  if (["tmdb-search", "tmdb-discover", "tmdb-preview"].includes(act)) return loadExternal(act, target);
  if (act === "nav") return $("#app").classList.toggle("nav-open");
  if (act === "back") return back();
  if (act === "settings") return settingsDialog();
  if (act === "dialog-cancel") return closeDialog();
  if (act === "reload") return render();
  if (act === "title-menu") return titleMenu(target);
  if (act === "add") {
    target.classList.add("is-busy");
    const result = await attempt(() => api("/library", "POST", { kind: target.dataset.kind, tmdb_id: Number(target.dataset.tmdb), status: target.dataset.status }));
    if (!result) return target.classList.remove("is-busy");
    await reloadState();
    toast(t("Added {title}", { title: result.title }));
    if (lyraNavigation.enabled) return navigate({ view: "title", type: result.type, id: result.id, from: state.route.from }, { mode: "replace" });
    state.route = { view: "title", type: result.type, id: result.id, from: state.route.from };
    return render();
  }
  if (act === "track") {
    const tmdbId = state.title.external.tmdb;
    const result = await attempt(() => api("/library", "POST", { kind: target.dataset.type === "movie" ? "movie" : "tv", tmdb_id: Number(tmdbId), status: "planned" }));
    if (result) {
      await reloadState();
      refreshTitle();
    }
    return;
  }
  if (act === "watch-movie") {
    const result = await attempt(() => api(`/movies/${id}/watch`, "POST", {}), t("Marked as watched"));
    if (result) {
      await reloadState();
      refreshTitle();
    }
    return;
  }
  if (act === "watch-episode") {
    target.classList.add("is-busy");
    const result = await attempt(() => api(`/episodes/${id}/watch`, "POST", {}));
    const watched = result?.seasons.flatMap((s) => s.episodes).find((e) => e.id === id);
    if (watched) toast(t("Marked {code} as watched", { code: episodeCode(watched) }));
    return afterSeriesChange(result);
  }
  if (act === "watch-season" || act === "unwatch-season") {
    state.openSeason = id;
    return afterSeriesChange(await attempt(() => api(`/seasons/${id}/watch`, act === "watch-season" ? "POST" : "DELETE")));
  }
  if (act === "episode-menu") {
    const snapshot = elementSnapshot($("#view .hero"));
    const episode = state.title.seasons.flatMap((s) => s.episodes).find((e) => e.id === id);
    const season = state.title.seasons.find((s) => s.episodes.includes(episode));
    state.openSeason = season?.id;
    return openMenu(target, [
      { label: t("Watched up to here"), icon: "check", run: async () => afterSeriesChange(await attempt(() => api(`/episodes/${id}/watch-through`, "POST", undefined, snapshot))) },
      { label: episode.watched ? t("Watched it again") : t("Mark watched"), icon: "history", run: async () => afterSeriesChange(await attempt(() => api(`/episodes/${id}/watch`, "POST", {}, snapshot))) },
      ...(episode.watched ? [{ label: t("Mark unwatched"), icon: "x", run: async () => afterSeriesChange(await attempt(() => api(`/episodes/${id}/watch`, "DELETE", undefined, snapshot))) }] : []),
    ]);
  }
  if (act === "rate") {
    const result = await attempt(() => api(`/library/${target.dataset.type}/${id}`, "PUT", { rating: Number(target.dataset.value) }));
    if (result) refreshTitle();
  }
});
document.addEventListener("change", async (event) => {
  const target = event.target.closest("[data-act]");
  if (!target) return;
  const { act, id, type } = target.dataset;
  if (act === "toggle-episode") {
    const season = target.closest("[data-season]");
    state.openSeason = season?.dataset.season;
    return afterSeriesChange(await attempt(() => api(`/episodes/${id}/watch`, target.checked ? "POST" : "DELETE", target.checked ? {} : undefined)));
  }
  if (act === "status") {
    const result = await attempt(() => api(`/library/${type}/${id}`, "PUT", { status: target.value }), t("Status updated"));
    if (result) {
      await reloadState();
      refreshTitle();
    }
  }
  if (act === "calendar") await attempt(() => api(`/library/${type}/${id}`, "PUT", { calendar: target.value }), t("Calendar sharing updated"));
});
document.addEventListener(
  "blur",
  async (event) => {
    const notes = event.target.closest?.("[data-notes]");
    if (!notes) return;
    try { await savePersonalNotes(notes); }
    catch (error) { toast(error.message, "danger"); }
  },
  true,
);
document.addEventListener("toggle", (event) => {
  if (event.target.matches?.("details.season") && event.target.open) state.openSeason = event.target.dataset.season;
}, true);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (closeMenu()) return;
    if (dialog().open) return;
    if ($("#app").classList.contains("nav-open")) return $("#app").classList.remove("nav-open");
    if (state.route.view === "title") return back();
  }
  if (event.key === "Enter" && event.target.matches?.(".list-row[role=button]")) event.target.click();
  if (event.key === "/" && !event.target.closest("input,textarea,select") && !dialog().open) {
    event.preventDefault();
    $("#search").focus();
  }
});

/* ───────────────────────── Start ───────────────────────── */

async function start() {
  try {
    state.context = await bridge("context");
  } catch {
    /* standalone preview */
  }
  activeLocale = safeLocale(state.context.locale);
  document.documentElement.lang = activeLocale;
  try {
    await reloadState();
    if (!state.app.settings.defaults_set) {
      const region = (new Intl.Locale(navigator.language || activeLocale).maximize().region || "US").toUpperCase();
      const language = /^[a-z]{2}-[A-Z]{2}$/.test(activeLocale) ? activeLocale : activeLocale === "sk" ? "sk-SK" : "en-US";
      state.app.settings = await api("/settings", "PUT", { region: /^[A-Z]{2}$/.test(region) ? region : "US", language }).catch(() => state.app.settings);
    }
  } catch (error) {
    $("#app").innerHTML = `<div class="ae-empty">${icon("alert")}<h3>${esc(t("Lyra could not start"))}</h3><p>${esc(error.message)}</p></div>`;
    return;
  }
  renderShell();
  // Inside a Nexus that supports it, the browser URL and Back/Forward follow Lyra's screens.
  if (state.context.navigation?.versions?.includes(1)) {
    try {
      if (await lyraNavigation.start(state.context)) {
        if (shownRoute) await queueNavigation(shownRoute, "replace").catch(() => {});
        return;
      }
    } catch {
      /* the host did not answer the handshake: keep the in-memory navigation below */
    }
  }
  // A link to one title, from another module (open_path of the resolver).
  const deep = location.pathname.match(/\/(movie|series)\/([0-9a-f-]{36})$/);
  if (deep) state.route = { view: "title", type: deep[1], id: deep[2], from: "library" };
  render();
}
start();
