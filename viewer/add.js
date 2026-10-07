// "Add maps" tab: drop files or a folder, and each map is copied into the atlas's library.
// New maps arrive with no tags and no footprint; labelling them is a separate, manual step.

(function () {
  const MAP_TYPES = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"];
  const zone = document.getElementById("drop-zone");
  const progress = document.getElementById("add-progress");
  const results = document.getElementById("add-results");
  const summary = document.getElementById("add-summary");
  const labelNew = document.getElementById("label-new");
  const filePicker = document.getElementById("pick-files");
  const folderPicker = document.getElementById("pick-folder");
  let busy = false;

  const isMap = (name) => MAP_TYPES.some((type) => name.toLowerCase().endsWith(type));
  const isHidden = (name) => name.startsWith(".");

  // Everything inside a dropped folder, however deep. Returns [{file, path}].
  async function filesFromEntry(entry, prefix = "") {
    if (entry.isFile) {
      const file = await new Promise((resolve, reject) => entry.file(resolve, reject));
      return [{ file, path: prefix + file.name }];
    }
    if (!entry.isDirectory || isHidden(entry.name)) return [];
    const reader = entry.createReader();
    const found = [];
    for (;;) {
      // readEntries hands back a batch at a time, and an empty batch when it is done
      const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      for (const child of batch) found.push(...(await filesFromEntry(child, `${prefix}${entry.name}/`)));
    }
    return found;
  }

  async function filesFromDrop(dataTransfer) {
    const entries = [...dataTransfer.items].map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
    if (!entries.length) return [...dataTransfer.files].map((file) => ({ file, path: file.name }));
    const found = [];
    for (const entry of entries) found.push(...(await filesFromEntry(entry)));
    return found;
  }

  function addResultLine(name, outcome, kind) {
    const line = document.createElement("li");
    const label = document.createElement("span");
    label.className = "result-name";
    label.textContent = name;
    const badge = document.createElement("span");
    badge.className = `result-outcome ${kind}`;
    badge.textContent = outcome;
    line.append(label, badge);
    results.append(line);
  }

  async function addFiles(found) {
    if (busy) return;
    const visible = found.filter(({ file }) => !isHidden(file.name));
    const maps = visible.filter(({ file }) => isMap(file.name));
    const notMaps = visible.length - maps.length;
    results.replaceChildren();
    labelNew.hidden = true;
    if (!maps.length) {
      summary.textContent = notMaps
        ? "Nothing to add: none of those are map files (PDF, JPG, PNG or TIFF)."
        : "Nothing to add.";
      return;
    }

    busy = true;
    zone.classList.add("busy");
    const counts = { added: 0, already: 0, failed: 0 };
    for (const [index, { file, path }] of maps.entries()) {
      progress.textContent = `Adding ${index + 1} of ${maps.length}: ${file.name}`;
      try {
        const query = `name=${encodeURIComponent(file.name)}&path=${encodeURIComponent(path)}`;
        const response = await fetch(`/api/add?${query}`, { method: "POST", body: file });
        const answer = await response.json();
        if (!response.ok) throw new Error(answer.error || response.statusText);
        if (answer.result === "added") {
          counts.added += 1;
          addResultLine(path, "Added", "added");
        } else if (answer.result === "already") {
          counts.already += 1;
          addResultLine(path, "Already in the library", "already");
        } else {
          addResultLine(path, "Skipped: not a map file", "skipped");
        }
      } catch (error) {
        counts.failed += 1;
        addResultLine(path, `Could not be added: ${error.message}`, "failed");
      }
    }

    progress.textContent = "Updating the atlas…";
    try {
      await window.atlasLabels.refresh();
      window.atlasGlobe?.reload();
    } catch (error) {
      counts.failed += 1;
    }
    progress.textContent = "";
    const parts = [`${counts.added} added`];
    if (counts.already) parts.push(`${counts.already} already in the library`);
    if (notMaps) parts.push(`${notMaps} skipped (not map files)`);
    if (counts.failed) parts.push(`${counts.failed} failed`);
    summary.textContent = `Done: ${parts.join(", ")}.`;
    labelNew.hidden = counts.added === 0;
    busy = false;
    zone.classList.remove("busy");
  }

  // ---- wiring
  for (const type of ["dragenter", "dragover"]) {
    zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add("over"); });
  }
  for (const type of ["dragleave", "drop"]) {
    zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove("over"); });
  }
  zone.addEventListener("drop", async (event) => addFiles(await filesFromDrop(event.dataTransfer)));
  // a file dropped anywhere else on the page should not replace the atlas with that file
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());

  document.getElementById("choose-files").addEventListener("click", () => filePicker.click());
  document.getElementById("choose-folder").addEventListener("click", () => folderPicker.click());
  for (const picker of [filePicker, folderPicker]) {
    picker.addEventListener("change", () => {
      addFiles([...picker.files].map((file) => ({ file, path: file.webkitRelativePath || file.name })));
      picker.value = ""; // so choosing the same thing again still counts as a change
    });
  }
  labelNew.addEventListener("click", () => {
    window.atlasLabels.showUnplaced();
    window.atlasTabs.show("labels");
  });
})();
