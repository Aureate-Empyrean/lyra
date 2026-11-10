/* Lyra adapter for the Nexus navigation contract (`empyrean-navigation-v1`, SDK in
   vendor/nexus-navigation.js, kept in sync by empyrean-nexus/scripts/sync-navigation.mjs).
   Nexus owns the browser URL and history; Lyra owns its routes. A route reference is the
   screen and the title's ID; search text, list filters and scroll are private per-entry view
   state, and unsaved notes are saved or kept as a draft. None of them enter the URL. Without
   a supporting host, Lyra keeps its old in-memory navigation. */

const LYRA_UUID = "[0-9a-f-]{36}";
const LyraRoutes = {
  parse(value) {
    const path = String(value || "/").split(/[?#]/, 1)[0].replace(/\/+$/, "") || "/";
    if (path === "/") return { view: "home" };
    if (["/series", "/movies", "/discover", "/history"].includes(path)) return { view: path.slice(1) };
    const title = path.match(new RegExp(`^/(movie|series)/(${LYRA_UUID})$`));
    if (title) return { view: "title", type: title[1], id: title[2] };
    const preview = path.match(/^\/preview\/(movie|tv)\/(\d{1,12})$/);
    if (preview) return { view: "title", preview: true, kind: preview[1], tmdb_id: Number(preview[2]) };
    return { view: "not-found", path };
  },
  serialize(route) {
    if (route.view === "not-found") return route.path;
    if (route.view === "title") return route.preview ? `/preview/${route.kind}/${route.tmdb_id}` : `/${route.type}/${route.id}`;
    return route.view === "home" ? "/" : `/${route.view}`;
  },
};

let shownRoute = null;
let pendingFrom = null;
let clearSearchOnApply = false;
const retainedDrafts = new Map();
let lastCheckpointDirty = false;

function checkpointNow() {
  if (!lyraNavigation.enabled) return Promise.resolve();
  const value = { version: 1, dirty: retainedDrafts.size > 0 || personalConflicts.size > 0, drafts: [...retainedDrafts.values()], conflicts: [...personalConflicts.values()].map(({ key, path, method, body, snapshot }) => ({ key, path, method, body, snapshot })) };
  if (!value.dirty && !lastCheckpointDirty) return Promise.resolve();
  return lyraNavigation.checkpoint(value).then(() => {
    lastCheckpointDirty = value.dirty;
  });
}
/** Notes save themselves when the field loses focus; a browser traversal does not blur it. */
async function flushNotes() {
  const box = $("[data-notes]");
  if (!box || state.title?.library?.notes === box.value) return;
  try { await savePersonalNotes(box); }
  catch { keepNoteDraft(box); }
}
function renderDraftTray() {
  let tray = $("#draft-tray");
  if (!retainedDrafts.size) return tray?.remove();
  if (!tray) {
    tray = document.createElement("div");
    tray.id = "draft-tray";
    tray.className = "draft-tray ae-glass";
    tray.setAttribute("role", "status");
    document.body.append(tray);
  }
  tray.replaceChildren(
    ...[...retainedDrafts.values()].map((draft) => {
      const row = document.createElement("div");
      row.className = "draft-tray-row";
      row.innerHTML = `<span class="grow">${esc(t("Unsaved notes are kept in this tab: {label}", { label: draft.label }))}</span><button class="ae-btn ae-btn--sm ae-btn--primary" data-draft="resume">${esc(t("Resume editing"))}</button><button class="ae-btn ae-btn--sm ae-btn--quiet" data-draft="discard">${esc(t("Discard"))}</button>`;
      $('[data-draft="resume"]', row).onclick = async () => {
        try {
          if (draft.route !== shownRoute) await queueNavigation(draft.route, "push");
          const box = $(`[data-notes="${CSS.escape(`${draft.type}:${draft.id}`)}"]`);
          if (!box) throw Error("gone");
          box.value = draft.notes;
          box.dataset.revision = draft.revision || "legacy-draft";
          box.focus();
          renderDraftTray();
          checkpointNow().catch(() => {});
        } catch {
          toast(t("This draft could not be reopened. It stays available here."), "danger");
        }
      };
      $('[data-draft="discard"]', row).onclick = () => {
        retainedDrafts.delete(draft.key);
        renderDraftTray();
        checkpointNow().catch(() => {});
      };
      return row;
    }),
  );
}

const lyraNavigation = EmpyreanNavigation.createClient({
  async apply(value, message) {
    if (message.checkpoint?.version === 1) {
      for (const draft of message.checkpoint.drafts || []) retainedDrafts.set(draft.key, draft);
      for (const pending of message.checkpoint.conflicts || []) {
        if (typeof pending.key === "string" && typeof pending.path === "string" && ["POST", "PUT", "DELETE"].includes(pending.method) && guardedWrite(pending.path, pending.method) && ["movie", "series", "settings"].includes(pending.snapshot?.kind) && typeof pending.snapshot.revision === "string" && (pending.body === undefined || (pending.body !== null && typeof pending.body === "object" && !Array.isArray(pending.body)))) personalConflicts.set(pending.key, pending);
      }
      lastCheckpointDirty = !!message.checkpoint.dirty;
    }
    renderDraftTray();
    renderPersonalConflicts();
    const next = LyraRoutes.parse(value);
    const reference = LyraRoutes.serialize(next);
    if (reference === shownRoute) return;
    const view = message.viewState;
    if (next.view === "title") next.from = pendingFrom || view?.from || (next.type === "movie" ? "movies" : "series");
    pendingFrom = null;
    if (view) {
      state.query = view.query || "";
      state.filter = { ...state.filter, ...view.filter };
      state.openSeason = view.openSeason || null;
    } else if (message.cause !== "commit" || clearSearchOnApply) {
      state.query = "";
    }
    clearSearchOnApply = false;
    if ($("#search")) $("#search").value = state.query;
    shownRoute = reference;
    state.route = next;
    $("#app").classList.remove("nav-open");
    const outcome = await render();
    if (!message.isCurrent()) {
      // Superseded while loading: nothing was shown, so the next restore must show it.
      if (shownRoute === reference) shownRoute = null;
      return;
    }
    $("#main").scrollTop = view?.scroll || 0;
    // A preview of something already in the library shows the library record instead.
    const canonical = LyraRoutes.serialize(state.route);
    if (canonical !== shownRoute) {
      shownRoute = canonical;
      queueNavigation(canonical, "replace").catch(() => {});
    }
    return outcome;
  },
  async beforeLeave() {
    await flushNotes();
    renderDraftTray();
    await checkpointNow();
  },
  captureView() {
    if (!state.route) return null;
    return { scroll: $("#main")?.scrollTop || 0, query: state.query, filter: state.filter, openSeason: state.openSeason || null, from: state.route.from || null };
  },
  onError(error) {
    toast(error.message, "danger");
  },
});

let navigationQueue = Promise.resolve();
function queueNavigation(reference, mode) {
  const next = navigationQueue.catch(() => {}).then(() => lyraNavigation.navigate(reference, mode));
  navigationQueue = next;
  return next;
}
function commitRoute(route, mode) {
  pendingFrom = route.from || null;
  return queueNavigation(LyraRoutes.serialize(route), mode).catch((error) => {
    if (!/superseded/i.test(error.message)) toast(error.message, "danger");
  });
}
