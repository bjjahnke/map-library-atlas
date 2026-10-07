// "Label maps" tab: one card per map. Tag its places, choose its footprint (the shape drawn
// on the globe), rename or park it, then Save.

(function () {
  const cards = document.getElementById("cards");
  const saveButton = document.getElementById("save");
  const saveStatus = document.getElementById("save-status");
  const search = document.getElementById("search");
  const empty = document.getElementById("empty");
  const placeFilter = document.getElementById("place-filter");

  let saved = new Map(); // id -> map as last saved
  let drafts = new Map(); // id -> the editable fields as they are on screen
  let regions = []; // [{key, name}]
  let filter = "all";

  const regionName = (key) => regions.find((r) => r.key === key)?.name;
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function draftOf(map) {
    return {
      title: map.custom_title, regions: [...map.regions], revisit: map.revisit, notes: map.notes,
      footprint: map.footprint, box: [...map.box],
    };
  }
  function isChanged(id) {
    const before = draftOf(saved.get(id));
    const now = drafts.get(id);
    return (
      before.title !== now.title.trim() ||
      before.notes !== now.notes.trim() ||
      before.revisit !== now.revisit ||
      before.regions.join(";") !== now.regions.join(";") ||
      before.footprint !== now.footprint ||
      before.box.join(";") !== now.box.map((v) => v.trim()).join(";")
    );
  }
  const changedIds = () => [...drafts.keys()].filter(isChanged);

  function refreshSaveBar() {
    const count = changedIds().length;
    saveButton.disabled = count === 0;
    if (count) saveStatus.textContent = count === 1 ? "1 unsaved change" : `${count} unsaved changes`;
    else if (!saveStatus.dataset.keep) saveStatus.textContent = "";
    delete saveStatus.dataset.keep;
  }

  function badgeFor(map) {
    if (map.status === "ok") {
      return ["ok", map.bbox_precision === "exact" ? "On the globe · exact box" : "On the globe"];
    }
    if (map.status === "error") return ["error", "Problem"];
    if (map.revisit) return ["todo", "Parked"];
    if (map.footprint === "none") return ["todo", "Tagged · no footprint yet"];
    return ["todo", map.footprint === "own" ? "Needs its footprint" : "Needs a place"];
  }

  function renderChips(container, id) {
    const draft = drafts.get(id);
    container.replaceChildren();
    if (!draft.regions.length) {
      container.append(el("span", "no-places", "No places yet"));
      return;
    }
    for (const key of draft.regions) {
      const name = regionName(key);
      const chip = el("span", name ? "chip" : "chip unknown", name || `${key} (not in the list)`);
      const remove = el("button", "", "×");
      remove.type = "button";
      remove.title = `Remove ${name || key}`;
      remove.setAttribute("aria-label", `Remove ${name || key}`);
      remove.addEventListener("click", () => {
        draft.regions = draft.regions.filter((k) => k !== key);
        renderChips(container, id);
        markCard(id);
      });
      chip.append(remove);
      container.append(chip);
    }
  }

  function markCard(id) {
    document.querySelector(`.card[data-id="${id}"]`)?.classList.toggle("changed", isChanged(id));
    refreshSaveBar();
  }

  function buildCard(map) {
    const id = map.id;
    const draft = drafts.get(id);
    const card = el("article", "card");
    card.dataset.id = id;

    // preview: click to open the map itself in a new tab
    const preview = el("a", "preview");
    preview.href = `/api/file/${id}`;
    preview.target = "_blank";
    preview.rel = "noopener";
    preview.title = "Open the map in a new tab";
    const image = el("img");
    image.loading = "lazy";
    image.alt = `Preview of ${map.file_name}`;
    image.src = `/api/thumb/${id}`;
    image.addEventListener("error", () => image.replaceWith(el("span", "no-preview", `${map.format} · no preview`)));
    const [badgeClass, badgeText] = badgeFor(map);
    preview.append(image, el("span", `badge ${badgeClass}`, badgeText));

    const body = el("div", "card-body");
    body.append(el("div", "file-name", map.file_name));

    // title
    const titleField = el("label");
    titleField.append(el("span", "field-label", "Title"));
    const title = el("input");
    title.type = "text";
    title.value = draft.title;
    title.placeholder = map.custom_title ? "" : map.title;
    title.addEventListener("input", () => { draft.title = title.value; markCard(id); });
    titleField.append(title);

    // places
    const placesField = el("div");
    placesField.append(el("span", "field-label", "Places this map is in (tags)"));
    const chips = el("div", "chips");
    renderChips(chips, id);
    const add = el("input");
    add.type = "text";
    add.placeholder = "Add a place… (start typing a state)";
    add.setAttribute("list", "region-names");
    add.setAttribute("aria-label", `Add a place to ${map.file_name}`);
    const tryAdd = () => {
      const typed = add.value.trim().toLowerCase();
      const match = regions.find((r) => r.name.toLowerCase() === typed || r.key === typed.replace(/\s+/g, "_"));
      if (!match) return false;
      if (!draft.regions.includes(match.key)) draft.regions.push(match.key);
      add.value = "";
      renderChips(chips, id);
      markCard(id);
      return true;
    };
    add.addEventListener("input", tryAdd); // picking from the list fires this with a full name
    add.addEventListener("keydown", (event) => { if (event.key === "Enter") tryAdd(); });
    placesField.append(chips, add);

    // footprint: the shape drawn on the globe, chosen separately from the tags
    const footprintField = el("div");
    footprintField.append(el("span", "field-label", "Footprint on the globe"));
    const footprint = el("select");
    footprint.setAttribute("aria-label", `Footprint for ${map.file_name}`);
    for (const [value, text] of [
      ["places", "A rectangle around its places"],
      ["own", "Its own rectangle (enter the edges)"],
      ["none", "None yet (tagged only)"],
    ]) {
      const option = el("option", "", text);
      option.value = value;
      footprint.append(option);
    }
    footprint.value = draft.footprint;
    const edges = el("div", "edges");
    ["West", "South", "East", "North"].forEach((name, index) => {
      const edge = el("label");
      edge.append(el("span", "edge-name", name));
      const input = el("input");
      input.type = "text";
      input.inputMode = "decimal";
      input.value = draft.box[index];
      input.placeholder = index % 2 ? "latitude" : "longitude";
      input.addEventListener("input", () => { draft.box[index] = input.value; markCard(id); });
      edge.append(input);
      edges.append(edge);
    });
    edges.hidden = draft.footprint !== "own";
    footprint.addEventListener("change", () => {
      draft.footprint = footprint.value;
      edges.hidden = draft.footprint !== "own";
      markCard(id);
    });
    footprintField.append(footprint, edges);

    // come back to this
    const revisitRow = el("label", "revisit-row");
    const revisit = el("input");
    revisit.type = "checkbox";
    revisit.checked = draft.revisit;
    revisit.addEventListener("change", () => { draft.revisit = revisit.checked; markCard(id); });
    revisitRow.append(revisit, document.createTextNode("Come back to this one"));

    const notes = el("input");
    notes.type = "text";
    notes.value = draft.notes;
    notes.placeholder = "Note to self (optional)";
    notes.setAttribute("aria-label", `Note for ${map.file_name}`);
    notes.addEventListener("input", () => { draft.notes = notes.value; markCard(id); });

    body.append(titleField, placesField, footprintField, revisitRow, notes);
    if (map.status === "error") body.append(el("div", "detail error", map.status_detail));
    card.append(preview, body);
    return card;
  }

  function matchesFilter(map) {
    if (filter === "todo" && map.status === "ok") return false;
    if (filter === "revisit" && !map.revisit) return false;
    const words = search.value.trim().toLowerCase();
    if (placeFilter.value === "(none)" && map.regions.length) return false;
    if (placeFilter.value && placeFilter.value !== "(none)" && !map.regions.includes(placeFilter.value)) return false;
    const places = map.regions.map((key) => regionName(key) || key).join(" ");
    return !words || `${map.file_name} ${map.title} ${places}`.toLowerCase().includes(words);
  }

  function applyFilter() {
    let shown = 0;
    for (const card of cards.children) {
      const visible = matchesFilter(saved.get(card.dataset.id));
      card.hidden = !visible;
      if (visible) shown += 1;
    }
    empty.hidden = shown > 0;
  }

  // The "show maps in one place" list: only places some map is tagged with, with counts.
  function fillPlaceFilter(maps) {
    const chosen = placeFilter.value;
    const counts = new Map();
    for (const map of maps) for (const key of map.regions) counts.set(key, (counts.get(key) || 0) + 1);
    const option = (value, text) => { const o = el("option", "", text); o.value = value; return o; };
    const used = [...counts.keys()].sort((a, b) => (regionName(a) || a).localeCompare(regionName(b) || b));
    const untagged = maps.filter((m) => !m.regions.length).length;
    placeFilter.replaceChildren(
      option("", "All places"),
      ...used.map((key) => option(key, `${regionName(key) || key} (${counts.get(key)})`)),
      option("(none)", `No places yet (${untagged})`)
    );
    placeFilter.value = [...placeFilter.options].some((o) => o.value === chosen) ? chosen : "";
  }

  function render(state) {
    regions = state.regions;
    document.getElementById("region-names").replaceChildren(
      ...regions.map((r) => { const option = el("option"); option.value = r.name; return option; })
    );
    // keep anything typed but not yet saved, so adding maps never throws away label edits
    const unsaved = new Map(changedIds().map((id) => [id, drafts.get(id)]));
    saved = new Map(state.maps.map((m) => [m.id, m]));
    drafts = new Map(state.maps.map((m) => [m.id, unsaved.get(m.id) || draftOf(m)]));
    cards.replaceChildren(...state.maps.map(buildCard));
    for (const id of unsaved.keys()) if (saved.has(id)) markCard(id);

    const onGlobe = state.maps.filter((m) => m.status === "ok").length;
    // the top bar count comes from here too, so it is right even before the globe has drawn
    document.getElementById("summary-text").textContent = onGlobe === 1 ? "1 map on the globe" : `${onGlobe} maps on the globe`;
    document.getElementById("count-all").textContent = state.maps.length;
    document.getElementById("count-todo").textContent = state.maps.length - onGlobe;
    document.getElementById("count-revisit").textContent = state.maps.filter((m) => m.revisit).length;
    fillPlaceFilter(state.maps);
    applyFilter();
    refreshSaveBar();
  }

  async function load() {
    try {
      const response = await fetch("/api/state", { cache: "no-store" });
      if (!response.ok) throw new Error(response.statusText);
      render(await response.json());
    } catch (error) {
      cards.replaceChildren(el("p", "detail error", "Could not load your maps. Is the atlas still running?"));
    }
  }

  async function save() {
    const changes = {};
    for (const id of changedIds()) {
      const draft = drafts.get(id);
      changes[id] = {
        title: draft.title.trim(), regions: draft.regions, revisit: draft.revisit, notes: draft.notes.trim(),
        footprint: draft.footprint, box: draft.box.map((value) => value.trim()),
      };
    }
    saveButton.disabled = true;
    saveStatus.textContent = "Saving…";
    try {
      const response = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ changes }),
      });
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || response.statusText);
      saveStatus.dataset.keep = "1";
      saveStatus.textContent = `Saved. ${state.on_globe} maps on the globe.`;
      drafts = new Map(); // everything on screen is now saved
      render(state);
      window.atlasGlobe?.reload();
    } catch (error) {
      saveStatus.textContent = `Could not save: ${error.message}`;
      saveButton.disabled = false;
    }
  }

  function setFilter(name) {
    filter = name;
    document.querySelectorAll(".filter").forEach((b) => b.classList.toggle("active", b.dataset.filter === name));
    applyFilter();
  }

  function showTab(name) {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === name);
      t.setAttribute("aria-selected", t.dataset.tab === name);
    });
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
    if (name === "globe") window.atlasGlobe?.resize();
  }

  // ---- wiring
  saveButton.addEventListener("click", save);
  search.addEventListener("input", applyFilter);
  placeFilter.addEventListener("change", applyFilter);
  for (const button of document.querySelectorAll(".filter")) {
    button.addEventListener("click", () => setFilter(button.dataset.filter));
  }
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
  }
  window.atlasTabs = { show: showTab };
  // used by the Add maps tab
  window.atlasLabels = {
    refresh: async () => {
      const response = await fetch("/api/rebuild", { method: "POST" });
      const state = await response.json();
      if (!response.ok) throw new Error(state.error || response.statusText);
      render(state);
    },
    showUnplaced: () => {
      search.value = "";
      placeFilter.value = "";
      setFilter("todo");
    },
  };
  window.addEventListener("beforeunload", (event) => {
    if (changedIds().length) event.preventDefault(); // warn before losing unsaved labels
  });

  load();
})();
