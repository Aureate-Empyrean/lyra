/* Lyra's personal-data concurrency. The shared P1 protocol remains unchanged. */
const personalConflicts = new Map();
const noteFlights = new Map();

function personalAttributes(item) {
  const kind =
    item.type === "episode" ? "series" : item.type || item.resource?.type;
  const id = item.resource_id || item.resource?.id || item.id;
  return kind && id && item.revision
    ? `data-personal-type="${esc(kind)}" data-personal-id="${esc(id)}" data-personal-revision="${esc(item.revision)}"`
    : "";
}
function elementSnapshot(element) {
  const node = element?.closest("[data-personal-id]");
  return node
    ? {
        kind: node.dataset.personalType,
        id: node.dataset.personalId,
        revision: node.dataset.personalRevision,
      }
    : null;
}
function personalSnapshot(path, body) {
  if (path === "/settings")
    return {
      kind: "settings",
      id: "global",
      revision: state.app?.settings.revision,
    };
  const title = path.match(/^\/(?:library\/)?(movie|series|movies)\/([^/?]+)/);
  if (title) {
    const kind = title[1] === "movies" ? "movie" : title[1];
    const node = $(
      `[data-personal-type="${kind}"][data-personal-id="${CSS.escape(title[2])}"]`,
    );
    return elementSnapshot(node) || { kind, id: title[2], revision: "0" };
  }
  const action = path.match(/^\/(?:episodes|seasons|history)\/([^/?]+)/);
  if (action) {
    const node = $(`[data-id="${CSS.escape(action[1])}"]`);
    return elementSnapshot(node) || elementSnapshot($("#view .hero"));
  }
  if (path === "/library") {
    if (state.route.view === "title" && !state.route.preview)
      return elementSnapshot($("#view .hero"));
    return {
      kind: body.kind === "movie" ? "movie" : "series",
      id: null,
      revision: "0",
    };
  }
  return null;
}
function guardedWrite(path, method) {
  return (
    method !== "GET" &&
    (path === "/settings" ||
      path === "/library" ||
      /^\/library\/(movie|series)\//.test(path) ||
      /^\/(movies|episodes|seasons)\/[^/]+\/(watch|watch-through)$/.test(
        path,
      ) ||
      (method === "DELETE" && /^\/history\//.test(path)))
  );
}
async function personalRequest(path, method, body, supplied) {
  if (!guardedWrite(path, method)) return rawApi(path, method, body);
  const snapshot = { ...(supplied || personalSnapshot(path, body) || {}) };
  const key = `${snapshot.kind}:${snapshot.id || "provider"}:${path}:${method}`;
  try {
    const result = await rawApi(
      `${path}${path.includes("?") ? "&" : "?"}expected_revision=${encodeURIComponent(snapshot.revision ?? "missing")}`,
      method,
      body,
    );
    if (snapshot.kind === "settings") state.app.settings = result;
    if (result.revision && result.id) {
      $$(`[data-personal-id="${CSS.escape(result.id)}"]`).forEach((node) => {
        if (node.dataset.personalRevision === snapshot.revision)
          node.dataset.personalRevision = result.revision;
      });
      const box = $(`[data-notes="${result.type}:${CSS.escape(result.id)}"]`);
      if (box?.dataset.revision === snapshot.revision) {
        box.dataset.revision = result.revision;
        const draft = retainedDrafts.get(`${result.type}:${result.id}`);
        if (draft?.revision === snapshot.revision)
          draft.revision = result.revision;
      }
      if (state.route.id === result.id) state.title = result;
    }
    return result;
  } catch (error) {
    if (error.message.includes("[LYRA_CONFLICT]")) {
      const draft = retainedDrafts.get(`${snapshot.kind}:${snapshot.id}`);
      const pendingBody =
        body?.notes !== undefined && draft
          ? { ...body, notes: draft.notes }
          : body;
      personalConflicts.set(key, {
        key,
        path,
        method,
        body: pendingBody,
        snapshot,
      });
      renderPersonalConflicts();
      checkpointNow().catch((failure) => toast(failure.message, "danger"));
      error.message = t("Changed elsewhere. Your pending change stays kept.");
    }
    throw error;
  }
}

function keepNoteDraft(box) {
  const [type, id] = box.dataset.notes.split(":");
  const key = `${type}:${id}`;
  if (state.title?.id === id && box.value === state.title.library?.notes)
    retainedDrafts.delete(key);
  else
    retainedDrafts.set(key, {
      key,
      type,
      id,
      notes: box.value,
      revision: box.dataset.revision,
      label: state.title?.title || t("Notes"),
      route: shownRoute,
    });
  for (const pending of personalConflicts.values()) {
    if (pending.body?.notes !== undefined && pending.snapshot.id === id) {
      pending.body = { ...pending.body, notes: box.value };
      pending.reviewed = null;
    }
  }
  renderDraftTray();
  renderPersonalConflicts();
  checkpointNow().catch((error) => toast(error.message, "danger"));
}
function restoreNoteDraft() {
  const box = $("[data-notes]");
  const draft = box && retainedDrafts.get(box.dataset.notes);
  if (draft) {
    box.value = draft.notes;
    box.dataset.revision = draft.revision || "legacy-draft";
  }
  renderPersonalConflicts();
}
async function savePersonalNotes(box) {
  const key = box.dataset.notes;
  if (noteFlights.has(key)) {
    const saved = await noteFlights.get(key);
    if (box.value === saved.library?.notes) return;
    box.dataset.revision = saved.revision;
  }
  if (
    state.title?.id === key.split(":")[1] &&
    box.value === state.title.library?.notes
  )
    return;
  const [kind, id] = key.split(":");
  if (
    [...personalConflicts.values()].some(
      (pending) =>
        pending.snapshot.id === id && pending.body?.notes !== undefined,
    )
  )
    throw Error(t("Review the latest record before retrying your notes."));
  const notes = box.value;
  const revision = box.dataset.revision;
  const flight = api(
    `/library/${kind}/${id}`,
    "PUT",
    { notes },
    { kind, id, revision },
  );
  noteFlights.set(key, flight);
  try {
    await flight;
    if (retainedDrafts.get(key)?.notes === notes) retainedDrafts.delete(key);
    renderDraftTray();
    await checkpointNow();
    if (box.isConnected) toast(t("Notes saved"));
  } finally {
    if (noteFlights.get(key) === flight) noteFlights.delete(key);
  }
}
document.addEventListener("input", (event) => {
  if (event.target.matches?.("[data-notes]")) keepNoteDraft(event.target);
});

function renderPersonalConflicts() {
  let tray = $("#personal-conflicts");
  if (!personalConflicts.size) return tray?.remove();
  if (!tray) {
    tray = document.createElement("aside");
    tray.id = "personal-conflicts";
    tray.className = "personal-conflicts ae-glass";
    tray.setAttribute("aria-label", t("Unsaved changes"));
  }
  const parent = dialog().open ? dialog() : document.body;
  if (tray.parentElement !== parent) parent.append(tray);
  tray.replaceChildren(
    ...[...personalConflicts.values()].map((pending) => {
      const row = document.createElement("section");
      row.innerHTML = `<h2>${esc(t("Changed elsewhere"))}</h2><p role="alert">${esc(t("Your change was not saved. Review the latest record before retrying. Your pending change stays kept."))}</p><div class="conflict-comparison"><div><strong>${esc(t("Your pending change"))}</strong><pre data-pending></pre></div><div><strong>${esc(t("Latest saved values"))}</strong><pre data-latest></pre></div></div><div class="actions"><button class="ae-btn" data-review>${esc(t("Review latest"))}</button><button class="ae-btn ae-btn--primary" data-retry disabled>${esc(t("Apply my change after review"))}</button><button class="ae-btn ae-btn--quiet" data-discard>${esc(t("Discard pending change"))}</button></div><p data-error role="status"></p>`;
      const action = pending.path.startsWith("/history/")
        ? t("Remove viewing history entry")
        : pending.path.includes("watch-through")
          ? t("Mark episodes watched up to the selected episode")
          : pending.path.includes("/watch")
            ? pending.method === "DELETE"
              ? t("Mark selected progress unwatched")
              : t("Mark selected progress watched")
            : pending.method === "DELETE"
              ? t("Remove title from library")
              : "";
      $("[data-pending]", row).textContent =
        action ||
        (pending.path === "/library"
          ? t("Add title to library")
          : readablePersonalFields(pending.body, pending.snapshot.kind));
      $("[data-review]", row).onclick = async () => {
        try {
          let snapshot = pending.snapshot;
          if (!snapshot.id) {
            const mapped = await rawApi(
              `/preview/${pending.body.kind}/${pending.body.tmdb_id}`,
            );
            if (!mapped.resource)
              throw Error(t("Open this title again before retrying."));
            snapshot = { kind: mapped.resource.type, id: mapped.resource.id };
          }
          const latest =
            snapshot.kind === "settings"
              ? (await api("/state")).settings
              : await api(
                  `/${snapshot.kind === "movie" ? "movies" : "series"}/${snapshot.id}`,
                );
          pending.reviewed = { ...snapshot, revision: latest.revision };
          $("[data-latest]", row).textContent =
            latest.library === undefined
              ? readablePersonalFields(latest)
              : !latest.library
                ? t("Not in your library")
                : readablePersonalFields(latest.library, snapshot.kind) +
                  (latest.progress
                    ? `\n${t("Episodes watched")}: ${latest.progress.watched}`
                    : `\n${t("Viewing history")}: ${latest.history.length}`);
          const removed =
            snapshot.kind !== "settings" &&
            !latest.library &&
            pending.path !== "/library";
          $("[data-retry]", row).disabled = removed;
          $("[data-error]", row).textContent = removed
            ? t(
                "This title was removed. Re-add it explicitly; your draft stays kept.",
              )
            : t(
                "Review the saved values and your pending change before applying it.",
              );
        } catch (error) {
          $("[data-error]", row).textContent = error.message;
        }
      };
      $("[data-retry]", row).onclick = async () => {
        if (!pending.reviewed) return;
        const snapshot = pending.reviewed;
        pending.reviewed = null;
        const submitted = pending.body;
        $("[data-retry]", row).disabled = true;
        try {
          const result = await api(
            pending.path,
            pending.method,
            submitted,
            snapshot,
          );
          if (
            personalConflicts.get(pending.key) === pending &&
            pending.body === submitted
          )
            personalConflicts.delete(pending.key);
          else if (
            personalConflicts.get(pending.key) === pending &&
            result.revision
          )
            pending.snapshot = { ...snapshot, revision: result.revision };
          if (
            submitted?.notes !== undefined &&
            retainedDrafts.get(`${snapshot.kind}:${snapshot.id}`)?.notes ===
              submitted.notes
          )
            retainedDrafts.delete(`${snapshot.kind}:${snapshot.id}`);
          await checkpointNow();
          renderDraftTray();
          renderPersonalConflicts();
          if (state.route.view === "title" && state.route.id === snapshot.id)
            await refreshTitle();
          else await render();
        } catch (error) {
          if (row.isConnected)
            $("[data-error]", row).textContent = error.message;
        }
      };
      $("[data-discard]", row).onclick = async () => {
        try {
          if (pending.body?.notes !== undefined) {
            const { kind, id } = pending.snapshot;
            const draft = retainedDrafts.get(`${kind}:${id}`)?.notes;
            const latest = await api(
              `/${kind === "movie" ? "movies" : "series"}/${id}`,
            );
            if (retainedDrafts.get(`${kind}:${id}`)?.notes !== draft)
              throw Error(
                t("Your draft changed while reloading. It stays kept."),
              );
            retainedDrafts.delete(`${kind}:${id}`);
            const box = $(`[data-notes="${kind}:${CSS.escape(id)}"]`);
            if (box) {
              box.value = latest.library?.notes || "";
              box.dataset.revision = latest.revision;
            }
            if (state.route.id === id) state.title = latest;
          }
          personalConflicts.delete(pending.key);
          await checkpointNow();
          renderDraftTray();
          renderPersonalConflicts();
        } catch (error) {
          if (row.isConnected)
            $("[data-error]", row).textContent = error.message;
        }
      };
      return row;
    }),
  );
}
function readablePersonalFields(values = {}, kind = "movie") {
  const labels = {
    notes: t("Notes"),
    status: t("Status"),
    rating: t("Your rating"),
    calendar: t("Calendar sharing"),
    region: t("Region"),
    language: t("Language"),
    calendar_episodes: t("Episode air dates"),
    calendar_premieres_only: t("Season premieres only"),
    calendar_movies: t("Movie releases"),
  };
  return Object.entries(values)
    .filter(([key]) => key in labels)
    .map(([key, value]) => {
      if (key === "status") value = statusLabel(value, kind);
      if (key === "calendar")
        value =
          {
            default: t("Follow sharing settings"),
            always: t("Always share dates with Chronos"),
            never: t("Never share dates"),
          }[value] || value;
      if (typeof value === "boolean") value = value ? t("Yes") : t("No");
      return `${labels[key]}: ${value ?? "—"}`;
    })
    .join("\n");
}
document.addEventListener("close", () => renderPersonalConflicts(), true);
